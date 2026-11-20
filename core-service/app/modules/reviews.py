"""Konteks Ulasan Pengunjung."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from .. import events
from ..db import get_conn
from ..security import User, current_user, require_roles
from .common import get_published_destination, ok, slice_of, to_iso_z

router = APIRouter(tags=["ulasan"])


class ReviewIn(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: Optional[str] = Field(default=None, max_length=1000)


class ModerationIn(BaseModel):
    hidden: bool


def review_out(r, with_flags=False) -> dict:
    out = {"id": str(r["id"]), "destination_id": str(r["destination_id"]), "user_name": r["user_name"],
           "rating": r["rating"], "comment": r["comment"], "created_at": to_iso_z(r["created_at"])}
    if with_flags:
        out.update(reported=bool(r["reported"]), hidden=bool(r["hidden"]))
    return out


@router.get("/destinations/{destination_id}/reviews", summary="Daftar ulasan dan rata-rata rating")
def list_reviews(destination_id: int, limit: int = Query(default=1, ge=1), offset: int = Query(default=0, ge=0),
                 conn=Depends(get_conn)):
    dest = get_published_destination(conn, destination_id)
    rows = conn.execute("SELECT * FROM reviews WHERE destination_id=? AND hidden=0 ORDER BY created_at DESC, id DESC",
                        (destination_id,)).fetchall()
    chunk, total = slice_of([review_out(r) for r in rows], limit, offset)
    resp = ok(conn, chunk, total=total)
    resp["meta"].update(rating_avg=dest["rating_avg"], review_count=dest["review_count"])
    return resp


@router.post("/destinations/{destination_id}/reviews", status_code=201, summary="Tulis ulasan (login)")
def create_review(destination_id: int, body: ReviewIn, user: User = Depends(current_user), conn=Depends(get_conn)):
    get_published_destination(conn, destination_id)
    if conn.execute("SELECT 1 FROM reviews WHERE destination_id=? AND user_id=?", (destination_id, user.id)).fetchone():
        raise HTTPException(409, "Anda sudah mengulas destinasi ini")
    cur = conn.execute("INSERT INTO reviews(destination_id,user_id,user_name,rating,comment) VALUES (?,?,?,?,?)",
                       (destination_id, user.id, user.name or "Pengguna", body.rating, body.comment))
    events.publish("UlasanDitambahkan", conn, destination_id=destination_id, review_id=cur.lastrowid)
    conn.commit()
    return ok(conn, review_out(conn.execute("SELECT * FROM reviews WHERE id=?", (cur.lastrowid,)).fetchone()))


@router.post("/reviews/{review_id}/report", summary="Laporkan ulasan untuk ditinjau (login)")
def report_review(review_id: int, _: User = Depends(current_user), conn=Depends(get_conn)):
    cur = conn.execute("UPDATE reviews SET reported=1 WHERE id=? AND hidden=0", (review_id,))
    conn.commit()
    if cur.rowcount == 0:
        raise HTTPException(404, "Ulasan tidak ditemukan")
    return ok(conn, {"id": str(review_id), "reported": True})


@router.get("/reviews/reported", summary="Ulasan yang dilaporkan (admin)")
def list_reported(limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0),
                  _: User = Depends(require_roles("admin")), conn=Depends(get_conn)):
    rows = conn.execute("SELECT * FROM reviews WHERE reported=1 ORDER BY id DESC").fetchall()
    chunk, total = slice_of([review_out(r, True) for r in rows], limit, offset)
    return ok(conn, chunk, total=total)


@router.patch("/reviews/{review_id}/moderation", summary="Sembunyikan atau tampilkan ulasan (admin)")
def moderate_review(review_id: int, body: ModerationIn, _: User = Depends(require_roles("admin")),
                    conn=Depends(get_conn)):
    row = conn.execute("SELECT * FROM reviews WHERE id=?", (review_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Ulasan tidak ditemukan")
    conn.execute("UPDATE reviews SET hidden=?, reported=0 WHERE id=?", (1 if body.hidden else 0, review_id))
    events.publish("UlasanDimoderasi", conn, destination_id=row["destination_id"], review_id=review_id)
    conn.commit()
    return ok(conn, review_out(conn.execute("SELECT * FROM reviews WHERE id=?", (review_id,)).fetchone(), True))
