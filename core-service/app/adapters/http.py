"""Pemanggilan sumber luar dengan cache dan fallback.

Jika sumber luar gagal, data terakhir yang tersimpan dikembalikan dengan penanda
dari_cache=True. Jika belum pernah ada data, UpstreamError dilempar dan modul
pemanggil menampilkan pesan yang jelas.
"""
import time
from typing import Any, Optional

import httpx

from ..config import settings

_cache: dict[str, dict] = {}


class UpstreamError(Exception):
    pass


def clear_cache() -> None:
    _cache.clear()


def cached_get_json(key: str, url: str, ttl: int, params: Optional[dict] = None,
                    headers: Optional[dict] = None) -> tuple[Any, bool, float]:
    """Return (data, dari_cache, diambil_pada_epoch)."""
    now = time.time()
    entry = _cache.get(key)
    if entry and entry["expires"] > now:
        return entry["data"], True, entry["at"]
    hdrs = {"User-Agent": settings.user_agent, "Accept": "application/json"}
    hdrs.update(headers or {})
    try:
        r = httpx.get(url, params=params, headers=hdrs, timeout=settings.http_timeout)
        r.raise_for_status()
        data = r.json()
    except (httpx.HTTPError, ValueError) as exc:
        if entry:
            return entry["data"], True, entry["at"]
        raise UpstreamError(str(exc)) from exc
    _cache[key] = {"data": data, "expires": now + ttl, "at": now}
    return data, False, now
