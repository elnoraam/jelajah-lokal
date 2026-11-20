"""Konteks Katalog Destinasi."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from .. import events
from ..config import CATEGORIES, CATEGORY_API, CATEGORY_INTERNAL, STATUS_API, STATUS_INTERNAL
from ..db import get_conn
from ..security import User, optional_user, require_roles
from .common import can_see_unpublished, haversine_km, ok, slice_of, to_iso_z

router = APIRouter(tags=["katalog-destinasi"])
CAT_PATTERN = "^(" + "|".join(CATEGORY_API.values()) + ")$"


class DestinationIn(BaseModel):
    name: str = Field(min_length=3, max_length=120)
    category: str = Field(pattern=CAT_PATTERN, description="nature | culture_history | local_culinary | tourism_village | craft")
    description: str = Field(min_length=20, max_length=4000)
    lat: float = Field(ge=-11.5, le=6.5)
    lon: float = Field(ge=94.0, le=141.5)
    address: Optional[str] = Field(default=None, max_length=250)
    opening_hours: Optional[str] = Field(default=None, max_length=120)
    photo_url: Optional[str] = Field(default=None, max_length=500, pattern="^https?://")
    wikipedia_title: Optional[str] = Field(default=None, max_length=150)


class StatusIn(BaseModel):
    status: str = Field(pattern="^(published|rejected)$")
    reason: Optional[str] = Field(default=None, max_length=300)


def dest_out(r) -> dict:
    d = dict(r)
    d["id"] = str(d["id"])
    d["category"] = CATEGORY_API[d["category"]]
    d["status"] = STATUS_API[d["status"]]
    d["hidden_gem"] = bool(d["hidden_gem"])
    d["lat"], d["lon"] = d.pop("latitude"), d.pop("longitude")
    d["created_at"], d["updated_at"] = to_iso_z(d["created_at"]), to_iso_z(d["updated_at"])
    d.pop("submitted_by", None)
    d.pop("reject_reason", None) if d["status"] != "rejected" else None
    return d


@router.get("/destinations", summary="Cari destinasi")
def search_destinations(
    q: Optional[str] = Query(default=None, max_length=80, description="Kata kunci nama, alamat, atau deskripsi"),
    category: Optional[str] = Query(default=None, pattern=CAT_PATTERN),
    hidden: Optional[bool] = Query(default=None, description="true = hanya wisata tersembunyi"),
    lat: Optional[float] = Query(default=None, ge=-90, le=90),
    lon: Optional[float] = Query(default=None, ge=-180, le=180),
    radius_m: Optional[float] = Query(default=None, gt=0, le=500000),
    status: Optional[str] = Query(default=None, pattern="^(waiting|published|rejected)$", description="Hanya berlaku untuk admin"),
    mine: bool = Query(default=False, description="true = kiriman saya (perlu login)"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: Optional[User] = Depends(optional_user),
    conn=Depends(get_conn),
):
    if (lat is None) != (lon is None):
        raise HTTPException(422, "lat dan lon harus diisi bersamaan")
    if radius_m is not None and lat is None:
        raise HTTPException(422, "radius_m memerlukan lat dan lon")
    where, args = [], []
    if mine:
        if not user:
            raise HTTPException(401, "Login diperlukan untuk mine=true")
        where.append("submitted_by=?")
        args.append(user.id)
    elif status and user and user.role == "admin":
        where.append("status=?")
        args.append(STATUS_INTERNAL[status])
    else:
        where.append("status='terbit'")
    if q:
        like = f"%{q.strip()}%"
        where.append("(name LIKE ? OR address LIKE ? OR description LIKE ?)")
        args += [like, like, like]
    if category:
        where.append("category=?")
        args.append(CATEGORY_INTERNAL[category])
    if hidden is not None:
        where.append("hidden_gem=?")
        args.append(1 if hidden else 0)
    rows = [dict(r) for r in conn.execute(
        f"SELECT * FROM destinations WHERE {' AND '.join(where)} ORDER BY created_at DESC, id DESC", args)]
    items = []
    for r in rows:
        if lat is not None:
            r["distance_m"] = round(haversine_km(lat, lon, r["latitude"], r["longitude"]) * 1000)
            if radius_m is not None and r["distance_m"] > radius_m:
                continue
        items.append(r)
    if lat is not None:
        items.sort(key=lambda r: r["distance_m"])
    chunk, total = slice_of([dest_out(r) for r in items], limit, offset)
    return ok(conn, chunk, total=total)


@router.get("/destinations/{destination_id}", summary="Detail destinasi")
def get_destination(destination_id: int, user: Optional[User] = Depends(optional_user), conn=Depends(get_conn)):
    row = conn.execute("SELECT * FROM destinations WHERE id=?", (destination_id,)).fetchone()
    if not row or (row["status"] != "terbit" and not can_see_unpublished(user, row["submitted_by"])):
        raise HTTPException(404, "Destinasi tidak ditemukan")
    return ok(conn, dest_out(row))


@router.post("/destinations", status_code=201, summary="Kirim destinasi baru (contributor)")
def create_destination(body: DestinationIn, user: User = Depends(require_roles("contributor", "admin")),
                       conn=Depends(get_conn)):
    status = "terbit" if user.role == "admin" else "menunggu"
    cur = conn.execute(
        """INSERT INTO destinations(name,category,description,latitude,longitude,address,opening_hours,
           photo_url,wikipedia_title,status,submitted_by) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (body.name.strip(), CATEGORY_INTERNAL[body.category], body.description.strip(), body.lat, body.lon, body.address,
         body.opening_hours, body.photo_url, body.wikipedia_title, status, user.id))
    new_id = cur.lastrowid
    if status == "terbit":
        events.publish("DestinasiTerbit", conn, destination_id=new_id)
    conn.commit()
    return ok(conn, dest_out(conn.execute("SELECT * FROM destinations WHERE id=?", (new_id,)).fetchone()))


@router.patch("/destinations/{destination_id}/status", summary="Terbitkan atau tolak destinasi (admin)")
def set_destination_status(destination_id: int, body: StatusIn, _: User = Depends(require_roles("admin")),
                           conn=Depends(get_conn)):
    row = conn.execute("SELECT * FROM destinations WHERE id=?", (destination_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Destinasi tidak ditemukan")
    if row["status"] != "menunggu":
        raise HTTPException(409, f"Destinasi sudah berstatus {STATUS_API[row['status']]}")
    if body.status == "rejected" and not body.reason:
        raise HTTPException(422, "Alasan penolakan wajib diisi")
    conn.execute("UPDATE destinations SET status=?, reject_reason=?, updated_at=datetime('now') WHERE id=?",
                 (STATUS_INTERNAL[body.status], body.reason, destination_id))
    if body.status == "published":
        events.publish("DestinasiTerbit", conn, destination_id=destination_id)
    conn.commit()
    return dest_out(conn.execute("SELECT * FROM destinations WHERE id=?", (destination_id,)).fetchone())
