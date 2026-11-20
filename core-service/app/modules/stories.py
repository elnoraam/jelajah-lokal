"""Konteks Cerita Budaya."""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from .. import events
from ..adapters.http import UpstreamError
from ..adapters.wiki import get_background
from ..db import get_conn
from ..security import User, optional_user, require_roles
from ..config import STATUS_API, STATUS_INTERNAL
from .common import can_see_unpublished, get_published_destination, ok, parse_id, slice_of, to_iso_z

router = APIRouter(tags=["cerita-budaya"])
SUMMARY_CHARS = 280


class StoryIn(BaseModel):
    title: str = Field(min_length=3, max_length=150)
    body: str = Field(min_length=50, max_length=20000)
    summary: Optional[str] = Field(default=None, max_length=400)
    destination_ids: List[str] = Field(min_length=1, max_length=10)


class StatusIn(BaseModel):
    status: str = Field(pattern="^(published|rejected)$")
    reason: Optional[str] = Field(default=None, max_length=300)


def short_text(row) -> str:
    if row["summary"]:
        return row["summary"]
    text = " ".join(row["body"].split())
    return text if len(text) <= SUMMARY_CHARS else text[:SUMMARY_CHARS].rsplit(" ", 1)[0] + "..."


def story_out(conn, row, mode: Optional[str] = None) -> dict:
    out = {"id": str(row["id"]), "title": row["title"], "status": STATUS_API[row["status"]],
           "author_id": str(row["author_id"]),
           "created_at": to_iso_z(row["created_at"]),
           "destination_ids": [str(r["destination_id"]) for r in conn.execute(
               "SELECT destination_id FROM story_destinations WHERE story_id=? ORDER BY destination_id", (row["id"],))]}
    if mode == "short":
        out["excerpt"] = short_text(row)
    else:
        out["summary"] = row["summary"]
        out["body"] = row["body"]
    return out


@router.get("/destinations/{destination_id}/stories", summary="Daftar cerita sebuah destinasi")
def list_destination_stories(destination_id: int, limit: int = Query(default=50, ge=1, le=200),
                             offset: int = Query(default=0, ge=0), conn=Depends(get_conn)):
    get_published_destination(conn, destination_id)
    rows = conn.execute(
        """SELECT s.* FROM stories s JOIN story_destinations sd ON sd.story_id = s.id
           WHERE sd.destination_id=? AND s.status='terbit' ORDER BY s.created_at DESC, s.id DESC""",
        (destination_id,)).fetchall()
    chunk, total = slice_of([story_out(conn, r, "short") for r in rows], limit, offset)
    return ok(conn, chunk, total=total)


@router.get("/destinations/{destination_id}/background", summary="Ringkasan latar sejarah (Wikipedia)")
def destination_background(destination_id: int, conn=Depends(get_conn)):
    dest = get_published_destination(conn, destination_id)
    if not dest["wikipedia_title"]:
        raise HTTPException(404, "Destinasi ini belum memiliki rujukan Wikipedia")
    try:
        return ok(conn, get_background(dest["wikipedia_title"]))
    except UpstreamError:
        raise HTTPException(503, "Wikipedia tidak dapat dihubungi dan belum ada data tersimpan")


@router.get("/stories", summary="Daftar cerita (admin dapat memfilter status)")
def list_stories(status: Optional[str] = Query(default=None, pattern="^(waiting|published|rejected)$"),
                 limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0),
                 user: Optional[User] = Depends(optional_user), conn=Depends(get_conn)):
    st = STATUS_INTERNAL[status] if (user and user.role == "admin" and status) else "terbit"
    rows = conn.execute("SELECT * FROM stories WHERE status=? ORDER BY created_at DESC, id DESC", (st,)).fetchall()
    chunk, total = slice_of([story_out(conn, r, "ringkas") for r in rows], limit, offset)
    return ok(conn, chunk, total=total)


@router.get("/stories/{story_id}", summary="Isi cerita")
def get_story(story_id: int, mode: Optional[str] = Query(default=None, pattern="^short$",
              description="short = hanya kutipan singkat (excerpt)"), user: Optional[User] = Depends(optional_user),
              conn=Depends(get_conn)):
    row = conn.execute("SELECT * FROM stories WHERE id=?", (story_id,)).fetchone()
    if not row or (row["status"] != "terbit" and not can_see_unpublished(user, row["author_id"])):
        raise HTTPException(404, "Cerita tidak ditemukan")
    return ok(conn, story_out(conn, row, mode))


@router.post("/stories", status_code=201, summary="Kirim cerita budaya (contributor)")
def create_story(body: StoryIn, user: User = Depends(require_roles("contributor", "admin")), conn=Depends(get_conn)):
    ids = sorted({parse_id(i) for i in body.destination_ids})
    for dest_id in ids:
        get_published_destination(conn, dest_id)
    status = "terbit" if user.role == "admin" else "menunggu"
    cur = conn.execute("INSERT INTO stories(title,body,summary,status,author_id) VALUES (?,?,?,?,?)",
                       (body.title.strip(), body.body.strip(), body.summary, status, user.id))
    story_id = cur.lastrowid
    conn.executemany("INSERT INTO story_destinations(story_id,destination_id) VALUES (?,?)",
                     [(story_id, d) for d in ids])
    if status == "terbit":
        events.publish("CeritaTerbit", conn, story_id=story_id, destination_ids=ids)
    conn.commit()
    return ok(conn, story_out(conn, conn.execute("SELECT * FROM stories WHERE id=?", (story_id,)).fetchone()))


@router.patch("/stories/{story_id}/status", summary="Terbitkan atau tolak cerita (admin)")
def set_story_status(story_id: int, body: StatusIn, _: User = Depends(require_roles("admin")), conn=Depends(get_conn)):
    row = conn.execute("SELECT * FROM stories WHERE id=?", (story_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Cerita tidak ditemukan")
    if row["status"] != "menunggu":
        raise HTTPException(409, f"Cerita sudah berstatus {STATUS_API[row['status']]}")
    if body.status == "rejected" and not body.reason:
        raise HTTPException(422, "Alasan penolakan wajib diisi")
    conn.execute("UPDATE stories SET status=?, reject_reason=?, updated_at=datetime('now') WHERE id=?",
                 (STATUS_INTERNAL[body.status], body.reason, story_id))
    if body.status == "published":
        ids = [r["destination_id"] for r in conn.execute(
            "SELECT destination_id FROM story_destinations WHERE story_id=?", (story_id,))]
        events.publish("CeritaTerbit", conn, story_id=story_id, destination_ids=ids)
    conn.commit()
    return ok(conn, story_out(conn, conn.execute("SELECT * FROM stories WHERE id=?", (story_id,)).fetchone()))
