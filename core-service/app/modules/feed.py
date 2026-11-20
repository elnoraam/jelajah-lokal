"""Konteks Umpan Destinasi: antarmuka terbuka untuk layanan lain (open host service)."""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from ..db import get_conn
from ..security import api_key_required
from .common import ok, to_iso_z

router = APIRouter(tags=["umpan-destinasi"])

# Nilai category untuk layanan lain memakai English. Slug internal tetap Indonesia.
CATEGORY_API = {
    "alam": "nature",
    "budaya-sejarah": "culture_history",
    "kuliner-lokal": "local_culinary",
    "desa-wisata": "tourism_village",
    "kerajinan": "craft",
}


def _parse_since(value: str) -> str:
    """ISO 8601 (UTC, boleh berakhiran Z) -> format SQLite untuk perbandingan."""
    try:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(422, "updated_since harus berformat ISO 8601 UTC, contoh 2026-11-20T10:00:00Z")
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


@router.get("/feed/destinations", summary="Umpan destinasi terbit untuk layanan lain (X-API-Key)")
def feed(updated_since: Optional[str] = Query(default=None, description="ISO 8601 UTC, contoh 2026-11-20T10:00:00Z"),
         limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0),
         _: str = Depends(api_key_required), conn=Depends(get_conn)):
    sql = "SELECT id,name,category,latitude,longitude,updated_at FROM destinations WHERE status='terbit'"
    args = []
    if updated_since:
        sql += " AND updated_at >= ?"
        args.append(_parse_since(updated_since))
    rows = conn.execute(sql + " ORDER BY id", args).fetchall()
    data = [{"id": str(r["id"]), "name": r["name"], "category": CATEGORY_API.get(r["category"], r["category"]),
             "lat": r["latitude"], "lon": r["longitude"], "updated_at": to_iso_z(r["updated_at"])}
            for r in rows[offset:offset + limit]]
    resp = ok(conn, data)
    resp["meta"]["total"] = len(rows)
    return resp