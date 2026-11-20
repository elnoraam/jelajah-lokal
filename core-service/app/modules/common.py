import math
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException

from ..config import settings
from ..meta import current_seq
from ..security import User


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def slice_of(items: list, limit: int, offset: int) -> tuple:
    """Return (potongan, total) untuk paginasi limit/offset."""
    return items[offset:offset + limit], len(items)


def get_published_destination(conn, destination_id: int):
    row = conn.execute("SELECT * FROM destinations WHERE id=?", (destination_id,)).fetchone()
    if not row or row["status"] != "terbit":
        raise HTTPException(404, "Destinasi tidak ditemukan")
    return row


def can_see_unpublished(user: Optional[User], owner_id: int) -> bool:
    return bool(user and (user.role == "admin" or user.id == owner_id))


def parse_id(value) -> int:
    """ID di API berupa string buram; di database berupa integer. ID yang bukan angka tidak ditemukan."""
    try:
        return int(str(value))
    except ValueError:
        raise HTTPException(404, "Data tidak ditemukan")
    

def to_iso_z(sqlite_ts: str) -> str:
    """'YYYY-MM-DD HH:MM:SS' (UTC dari SQLite) -> 'YYYY-MM-DDTHH:MM:SSZ'."""
    return sqlite_ts.replace(" ", "T") + "Z"


def now_z() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ok(conn, data, stale: bool = False, total: Optional[int] = None) -> dict:
    """Envelope sukses standar: {"data": ..., "meta": {seq, updated_at, source, stale}}.
    Untuk daftar, total seluruh hasil diisi di meta.total."""
    resp = {"data": data,
            "meta": {"seq": current_seq(conn), "updated_at": now_z(),
                     "source": "mock" if settings.mock_mode else "live", "stale": bool(stale)}}
    if total is not None:
        resp["meta"]["total"] = total
    return resp
