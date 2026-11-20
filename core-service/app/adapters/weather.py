"""Adapter Open-Meteo -> CuacaDestinasi."""
from datetime import datetime, timezone
from typing import Optional

from ..config import settings
from .http import cached_get_json

URL = "https://api.open-meteo.com/v1/forecast"

WMO = {0: "Cerah", 1: "Cerah berawan", 2: "Berawan sebagian", 3: "Berawan", 45: "Berkabut", 48: "Kabut tebal",
       51: "Gerimis ringan", 53: "Gerimis", 55: "Gerimis lebat", 61: "Hujan ringan", 63: "Hujan sedang",
       65: "Hujan lebat", 71: "Salju ringan", 80: "Hujan lokal ringan", 81: "Hujan lokal sedang",
       82: "Hujan lokal lebat", 95: "Badai petir", 96: "Badai petir dengan es", 99: "Badai petir lebat"}


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(timespec="seconds")


def get_weather(lat: float, lon: float, date: Optional[str] = None) -> dict:
    params = {"latitude": round(lat, 3), "longitude": round(lon, 3), "timezone": "Asia/Jakarta"}
    if date:
        params.update(daily="weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum",
                      start_date=date, end_date=date)
    else:
        params["current"] = "temperature_2m,rain,weather_code"
    key = f"weather:{params['latitude']}:{params['longitude']}:{date or 'now'}"
    data, cached, at = cached_get_json(key, URL, settings.weather_ttl, params=params)
    if date:
        d = data.get("daily", {})
        code = (d.get("weather_code") or [None])[0]
        out = {"tanggal": date, "suhu_maks_c": (d.get("temperature_2m_max") or [None])[0],
               "suhu_min_c": (d.get("temperature_2m_min") or [None])[0],
               "hujan_mm": (d.get("precipitation_sum") or [None])[0]}
    else:
        c = data.get("current", {})
        code = c.get("weather_code")
        out = {"suhu_c": c.get("temperature_2m"), "hujan_mm": c.get("rain")}
    out.update(kode_cuaca=code, deskripsi=WMO.get(code, "Tidak diketahui") if code is not None else None,
               sumber="open-meteo", diambil_pada=_iso(at), dari_cache=cached)
    return out
