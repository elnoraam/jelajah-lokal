"""Konteks Umpan Destinasi: antarmuka terbuka untuk layanan lain (open host service)."""
from typing import Optional

from fastapi import APIRouter, Depends, Query

from ..db import get_conn
from ..security import api_key_required
from .common import page_of

router = APIRouter(tags=["umpan-destinasi"])


@router.get("/feed/destinations", summary="Umpan destinasi terbit untuk layanan lain (X-API-Key)")
def feed(updated_since: Optional[str] = Query(default=None, description="Waktu UTC 'YYYY-MM-DD HH:MM:SS'"),
         page: int = Query(default=1, ge=1), size: int = Query(default=50, ge=1, le=200),
         _: str = Depends(api_key_required), conn=Depends(get_conn)):
    sql = "SELECT id,name,category,latitude,longitude,updated_at FROM destinations WHERE status='terbit'"
    args = []
    if updated_since:
        sql += " AND updated_at >= ?"
        args.append(updated_since)
    rows = conn.execute(sql + " ORDER BY id", args).fetchall()
    return page_of([dict(r) for r in rows], page, size)
