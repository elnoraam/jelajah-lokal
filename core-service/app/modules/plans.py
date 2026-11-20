"""Konteks Rencana Kunjungan."""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..db import get_conn
from ..security import User, current_user
from .common import get_published_destination, ok

router = APIRouter(tags=["rencana-kunjungan"])


class PlanIn(BaseModel):
    destination_id: int
    visit_date: date
    note: Optional[str] = Field(default=None, max_length=300)


def plan_out(r) -> dict:
    return {"id": r["id"], "destination_id": r["destination_id"], "destination_name": r["name"],
            "visit_date": r["visit_date"], "note": r["note"], "created_at": r["created_at"]}


@router.get("/plans", summary="Rencana kunjungan milik saya")
def list_plans(user: User = Depends(current_user), conn=Depends(get_conn)):
    rows = conn.execute(
        """SELECT p.*, d.name FROM plans p JOIN destinations d ON d.id = p.destination_id
           WHERE p.user_id=? ORDER BY p.visit_date, p.id""", (user.id,)).fetchall()
    return ok(conn, [plan_out(r) for r in rows], total=len(rows))


@router.post("/plans", status_code=201, summary="Simpan destinasi dan tanggal kunjungan")
def create_plan(body: PlanIn, user: User = Depends(current_user), conn=Depends(get_conn)):
    get_published_destination(conn, body.destination_id)
    if body.visit_date < date.today():
        raise HTTPException(422, "Tanggal kunjungan tidak boleh di masa lalu")
    cur = conn.execute("INSERT INTO plans(user_id,destination_id,visit_date,note) VALUES (?,?,?,?)",
                       (user.id, body.destination_id, body.visit_date.isoformat(), body.note))
    conn.commit()
    row = conn.execute("SELECT p.*, d.name FROM plans p JOIN destinations d ON d.id = p.destination_id WHERE p.id=?",
                       (cur.lastrowid,)).fetchone()
    return ok(conn, plan_out(row))


@router.delete("/plans/{plan_id}", summary="Hapus rencana kunjungan")
def delete_plan(plan_id: int, user: User = Depends(current_user), conn=Depends(get_conn)):
    cur = conn.execute("DELETE FROM plans WHERE id=? AND user_id=?", (plan_id, user.id))
    conn.commit()
    if cur.rowcount == 0:
        raise HTTPException(404, "Rencana tidak ditemukan")
    return ok(conn, {"id": plan_id, "deleted": True})
