"""Adapter cuaca -> CuacaDestinasi.

Cuaca saat ini diambil dari KotaSiaga (GET /weather) bila
SMARTCITY_API_URL diisi. Jika KotaSiaga mati atau datanya basi, Open-Meteo dipakai.
Prakiraan per tanggal (parameter date) selalu dari Open-Meteo, karena KotaSiaga hanya
menyediakan cuaca saat ini dan prakiraan 6 jam.
"""
from datetime import datetime, timezone
from typing import Optional

from ..config import settings
from .http import UpstreamError, cached_get_json

URL = "https://api.open-meteo.com/v1/forecast"
CONDITIONS = {"clear": "Cerah", "cloudy": "Berawan", "rain": "Hujan", "heavy_rain": "Hujan lebat",
              "storm": "Badai petir"}

WMO = {0: "Cerah", 1: "Cerah berawan", 2: "Berawan sebagian", 3: "Berawan", 45: "Berkabut", 48: "Kabut tebal",
       51: "Gerimis ringan", 53: "Gerimis", 55: "Gerimis lebat", 61: "Hujan ringan", 63: "Hujan sedang",
       65: "Hujan lebat", 71: "Salju ringan", 80: "Hujan lokal ringan", 81: "Hujan lokal sedang",
       82: "Hujan lokal lebat", 95: "Badai petir", 96: "Badai petir dengan es", 99: "Badai petir lebat"}


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _num(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _condition(code) -> Optional[str]:
    """Kode WMO -> enum condition yang sama dengan KotaSiaga."""
    if code is None:
        return None
    if code in (0, 1):
        return "clear"
    if code in (65, 82):
        return "heavy_rain"
    if code in (95, 96, 99):
        return "storm"
    if code in (51, 53, 55, 61, 63, 80, 81):
        return "rain"
    return "cloudy"


def _from_smartcity(lat: float, lon: float) -> dict:
    params = {"lat": round(lat, 4), "lon": round(lon, 4)}
    key = settings.smartcity_key or settings.risk_key
    headers = {"X-API-Key": key} if key else {}
    data, stale, at = cached_get_json(f"sc-weather:{params}", settings.weather_url, settings.weather_ttl,
                                      params=params, headers=headers, service="kotasiaga")
    w = data.get("data") if isinstance(data, dict) else None
    if not isinstance(w, dict):
        raise ValueError("format cuaca dari sumber tidak dikenali")
    temperature, rain = _num(w.get("temperature_c")), _num(w.get("rain_mm_h"))
    if temperature is None or rain is None:
        raise ValueError("format cuaca dari sumber tidak dikenali")
    condition = w.get("condition") if isinstance(w.get("condition"), str) and w.get("condition") in CONDITIONS else None
    meta = data.get("meta")
    stale = stale or (isinstance(meta, dict) and meta.get("stale") is True)
    return {"temperature_c": temperature, "rain_mm": rain, "weather_code": None,
            "description": CONDITIONS.get(condition), "condition": condition,
            "source": "kotasiaga", "fetched_at": _iso(at), "stale": stale}


def _from_open_meteo(lat: float, lon: float, date: Optional[str]) -> dict:
    params = {"latitude": round(lat, 3), "longitude": round(lon, 3), "timezone": "Asia/Jakarta"}
    if date:
        params.update(daily="weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum",
                      start_date=date, end_date=date)
    else:
        params["current"] = "temperature_2m,rain,weather_code"
    key = f"weather:{params['latitude']}:{params['longitude']}:{date or 'now'}"
    data, stale, at = cached_get_json(key, URL, settings.weather_ttl, params=params, service="open-meteo")
    if date:
        d = data.get("daily", {})
        code = (d.get("weather_code") or [None])[0]
        out = {"date": date, "temperature_max_c": (d.get("temperature_2m_max") or [None])[0],
               "temperature_min_c": (d.get("temperature_2m_min") or [None])[0],
               "rain_mm": (d.get("precipitation_sum") or [None])[0]}
    else:
        c = data.get("current", {})
        code = c.get("weather_code")
        out = {"temperature_c": c.get("temperature_2m"), "rain_mm": c.get("rain")}
    out.update(weather_code=code, description=WMO.get(code, "Tidak diketahui") if code is not None else None,
               condition=_condition(code), source="open-meteo", fetched_at=_iso(at), stale=stale)
    return out


def get_weather(lat: float, lon: float, date: Optional[str] = None) -> dict:
    smartcity = None
    if not date and settings.weather_url:
        try:
            smartcity = _from_smartcity(lat, lon)
        except (UpstreamError, ValueError):
            smartcity = None
        if smartcity and not smartcity["stale"]:
            return smartcity
    try:
        return _from_open_meteo(lat, lon, date)
    except UpstreamError:
        if smartcity:  # data KotaSiaga yang basi masih lebih baik daripada tanpa data
            return smartcity
        raise