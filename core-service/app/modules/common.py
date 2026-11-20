import math
from typing import Optional

from fastapi import HTTPException

from ..security import User


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def page_of(items: list, page: int, size: int) -> dict:
    start = (page - 1) * size
    return {"items": items[start:start + size], "page": page, "size": size, "total": len(items)}


def get_published_destination(conn, destination_id: int):
    row = conn.execute("SELECT * FROM destinations WHERE id=?", (destination_id,)).fetchone()
    if not row or row["status"] != "terbit":
        raise HTTPException(404, "Destinasi tidak ditemukan")
    return row


def can_see_unpublished(user: Optional[User], owner_id: int) -> bool:
    return bool(user and (user.role == "admin" or user.id == owner_id))
