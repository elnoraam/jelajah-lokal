"""Pemanggilan sumber luar dengan timeout, retry, cache, dan log.

- Timeout mengikuti settings.http_timeout (default 5 s).
- Satu kali retry dengan jitter untuk timeout, error jaringan, dan 5xx. 4xx tidak di-retry.
- Cache segar mengembalikan stale=False. Jika sumber gagal dan ada cache lama,
  data lama dikembalikan dengan stale=True. Tanpa cache, UpstreamError dilempar
  dan modul pemanggil menampilkan pesan yang jelas.
- Setiap panggilan keluar dicatat satu baris: waktu, service, path, status, ms.
"""
import logging
import random
import time
from typing import Any, Optional
from urllib.parse import urlparse

import httpx

from ..config import settings

MAX_CACHE_ENTRIES = 256
_cache: dict[str, dict] = {}

log = logging.getLogger("xcall")
if not log.handlers:
    _handler = logging.StreamHandler()
    _fmt = logging.Formatter("%(asctime)sZ %(message)s", "%Y-%m-%dT%H:%M:%S")
    _fmt.converter = time.gmtime
    _handler.setFormatter(_fmt)
    log.addHandler(_handler)
    log.setLevel(logging.INFO)
    log.propagate = False


class UpstreamError(Exception):
    pass


def clear_cache() -> None:
    _cache.clear()


def _get(service: str, url: str, params: Optional[dict], headers: dict) -> Any:
    path = urlparse(url).path
    for attempt in (1, 2):
        t0 = time.perf_counter()
        status, retry = "error", False
        try:
            r = httpx.get(url, params=params, headers=headers, timeout=settings.http_timeout)
            status = r.status_code
            if status < 500:
                r.raise_for_status()  # 4xx: gagal langsung, tanpa retry
                return r.json()
            retry = True
        except httpx.TimeoutException:
            status, retry = "timeout", True
        except httpx.TransportError:
            status, retry = "network_error", True
        finally:
            log.info("xcall service=%s path=%s status=%s ms=%d", service, path, status,
                     (time.perf_counter() - t0) * 1000)
        if not retry or attempt == 2:
            raise UpstreamError(f"{service} {status}")
        time.sleep(random.uniform(0.1, 0.4))


def _store(key: str, data: Any, expires: float, at: float) -> None:
    if key not in _cache and len(_cache) >= MAX_CACHE_ENTRIES:
        oldest = min(_cache, key=lambda k: _cache[k]["at"])
        del _cache[oldest]
    _cache[key] = {"data": data, "expires": expires, "at": at}


def cached_get_json(key: str, url: str, ttl: int, params: Optional[dict] = None,
                    headers: Optional[dict] = None, service: str = "") -> tuple[Any, bool, float]:
    """Return (data, stale, diambil_pada_epoch). stale=True hanya jika data dari cache karena sumber gagal."""
    now = time.time()
    entry = _cache.get(key)
    if entry and entry["expires"] > now:
        return entry["data"], False, entry["at"]
    hdrs = {"User-Agent": settings.user_agent, "Accept": "application/json"}
    hdrs.update(headers or {})
    try:
        data = _get(service or urlparse(url).netloc, url, params, hdrs)
    except (httpx.HTTPError, ValueError, UpstreamError) as exc:
        if entry:
            return entry["data"], True, entry["at"]
        raise UpstreamError(str(exc)) from exc
    _store(key, data, now + ttl, now)
    return data, False, now