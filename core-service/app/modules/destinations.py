"""Konteks Katalog Destinasi."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from .. import events
from ..config import CATEGORIES
from ..db import get_conn
from ..security import User, optional_user, require_roles
from .common import can_see_unpublished, haversine_km, page_of

router = APIRouter(tags=["katalog-destinasi"])
CAT_PATTERN = "^(" + "|".join(CATEGORIES) + ")$"


class DestinationIn(BaseModel):
    name: str = Field(min_length=3, max_length=120)
    category: str = Field(pattern=CAT_PATTERN, description="alam | budaya-sejarah | kuliner-lokal | desa-wisata | kerajinan")
    description: str = Field(min_length=20, max_length=4000)
    latitude: float = Field(ge=-11.5, le=6.5)
    longitude: float = Field(ge=94.0, le=141.5)
    address: Optional[str] = Field(default=None, max_length=250)
    opening_hours: Optional[str] = Field(default=None, max_length=120)
    photo_url: Optional[str] = Field(default=None, max_length=500, pattern="^https?://")
    wikipedia_title: Optional[str] = Field(default=None, max_length=150)


class StatusIn(BaseModel):
    status: str = Field(pattern="^(terbit|ditolak)$")
    reason: Optional[str] = Field(default=None, max_length=300)


def dest_out(r) -> dict:
    d = dict(r)
    d["hidden_gem"] = bool(d["hidden_gem"])
    d.pop("submitted_by", None)
    d.pop("reject_reason", None) if d["status"] != "ditolak" else None
    return d


@router.get("/destinations", summary="Cari destinasi")
def search_destinations(
    q: Optional[str] = Query(default=None, max_length=80, description="Kata kunci nama, alamat, atau deskripsi"),
    category: Optional[str] = Query(default=None, pattern=CAT_PATTERN),
    hidden: Optional[bool] = Query(default=None, description="true = hanya wisata tersembunyi"),
    lat: Optional[float] = Query(default=None, ge=-90, le=90),
    lon: Optional[float] = Query(default=None, ge=-180, le=180),
    radius_km: Optional[float] = Query(default=None, gt=0, le=500),
    status: Optional[str] = Query(default=None, pattern="^(menunggu|terbit|ditolak)$", description="Hanya berlaku untuk admin"),
    mine: bool = Query(default=False, description="true = kiriman saya (perlu login)"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=10, ge=1, le=50),
    user: Optional[User] = Depends(optional_user),
    conn=Depends(get_conn),
):
    if (lat is None) != (lon is None):
        raise HTTPException(422, "lat dan lon harus diisi bersamaan")
    if radius_km is not None and lat is None:
        raise HTTPException(422, "radius_km memerlukan lat dan lon")
    where, args = [], []
    if mine:
        if not user:
            raise HTTPException(401, "Login diperlukan untuk mine=true")
        where.append("submitted_by=?")
        args.append(user.id)
    elif status and user and user.role == "admin":
        where.append("status=?")
        args.append(status)
    else:
        where.append("status='terbit'")
    if q:
        like = f"%{q.strip()}%"
        where.append("(name LIKE ? OR address LIKE ? OR description LIKE ?)")
        args += [like, like, like]
    if category:
        where.append("category=?")
        args.append(category)
    if hidden is not None:
        where.append("hidden_gem=?")
        args.append(1 if hidden else 0)
    rows = [dict(r) for r in conn.execute(
        f"SELECT * FROM destinations WHERE {' AND '.join(where)} ORDER BY created_at DESC, id DESC", args)]
    items = []
    for r in rows:
        if lat is not None:
            r["jarak_km"] = round(haversine_km(lat, lon, r["latitude"], r["longitude"]), 2)
            if radius_km is not None and r["jarak_km"] > radius_km:
                continue
        items.append(r)
    if lat is not None:
        items.sort(key=lambda r: r["jarak_km"])
    return page_of([dest_out(r) for r in items], page, size)


@router.get("/destinations/{destination_id}", summary="Detail destinasi")
def get_destination(destination_id: int, user: Optional[User] = Depends(optional_user), conn=Depends(get_conn)):
    row = conn.execute("SELECT * FROM destinations WHERE id=?", (destination_id,)).fetchone()
    if not row or (row["status"] != "terbit" and not can_see_unpublished(user, row["submitted_by"])):
        raise HTTPException(404, "Destinasi tidak ditemukan")
    return dest_out(row)


@router.post("/destinations", status_code=201, summary="Kirim destinasi baru (kontributor)")
def create_destination(body: DestinationIn, user: User = Depends(require_roles("kontributor", "admin")),
                       conn=Depends(get_conn)):
    status = "terbit" if user.role == "admin" else "menunggu"
    cur = conn.execute(
        """INSERT INTO destinations(name,category,description,latitude,longitude,address,opening_hours,
           photo_url,wikipedia_title,status,submitted_by) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (body.name.strip(), body.category, body.description.strip(), body.latitude, body.longitude, body.address,
         body.opening_hours, body.photo_url, body.wikipedia_title, status, user.id))
    new_id = cur.lastrowid
    if status == "terbit":
        events.publish("DestinasiTerbit", conn, destination_id=new_id)
    conn.commit()
    return dest_out(conn.execute("SELECT * FROM destinations WHERE id=?", (new_id,)).fetchone())


@router.patch("/destinations/{destination_id}/status", summary="Terbitkan atau tolak destinasi (admin)")
def set_destination_status(destination_id: int, body: StatusIn, _: User = Depends(require_roles("admin")),
                           conn=Depends(get_conn)):
    row = conn.execute("SELECT * FROM destinations WHERE id=?", (destination_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Destinasi tidak ditemukan")
    if row["status"] != "menunggu":
        raise HTTPException(409, f"Destinasi sudah berstatus {row['status']}")
    if body.status == "ditolak" and not body.reason:
        raise HTTPException(422, "Alasan penolakan wajib diisi")
    conn.execute("UPDATE destinations SET status=?, reject_reason=?, updated_at=datetime('now') WHERE id=?",
                 (body.status, body.reason, destination_id))
    if body.status == "terbit":
        events.publish("DestinasiTerbit", conn, destination_id=destination_id)
    conn.commit()
    return dest_out(conn.execute("SELECT * FROM destinations WHERE id=?", (destination_id,)).fetchone())
