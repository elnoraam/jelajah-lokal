"""Anti-corruption layer untuk sumber status risiko wilayah.

Sumber luar boleh memakai istilah apa saja; adapter menerjemahkannya menjadi
tiga nilai milik JelajahLokal: Aman, Waspada, Bahaya. Alamat, kunci, dan nama
field dikonfigurasi lewat environment sehingga sumber dapat diganti tanpa
mengubah kode konteks lain.
"""
from typing import Optional

from ..config import settings
from .http import UpstreamError, cached_get_json

ALIASES = {
    "aman": "Aman", "safe": "Aman", "low": "Aman", "hijau": "Aman", "green": "Aman", "normal": "Aman",
    "waspada": "Waspada", "warning": "Waspada", "medium": "Waspada", "kuning": "Waspada", "yellow": "Waspada",
    "siaga": "Waspada",
    "bahaya": "Bahaya", "danger": "Bahaya", "high": "Bahaya", "merah": "Bahaya", "red": "Bahaya",
    "awas": "Bahaya",
}


def translate(raw) -> Optional[str]:
    if raw is None:
        return None
    return ALIASES.get(str(raw).strip().lower())


def _dig(obj, field: str):
    for part in field.split("."):
        if isinstance(obj, dict):
            obj = obj.get(part)
        else:
            return None
    return obj


def get_risk(lat: float, lon: float) -> dict:
    if not settings.risk_url:
        return {"tingkat": None, "keterangan": "Sumber status risiko belum dikonfigurasi", "sumber": None,
                "dari_cache": False}
    headers = {settings.risk_key_header: settings.risk_key} if settings.risk_key else {}
    params = {settings.risk_lat_param: round(lat, 4), settings.risk_lon_param: round(lon, 4)}
    try:
        data, cached, _ = cached_get_json(f"risk:{params}", settings.risk_url, settings.risk_ttl,
                                          params=params, headers=headers)
    except UpstreamError:
        return {"tingkat": None, "keterangan": "Sumber status risiko tidak dapat dihubungi", "sumber": "eksternal",
                "dari_cache": False}
    level = translate(_dig(data, settings.risk_level_field))
    if level is None:
        return {"tingkat": None, "keterangan": "Format status risiko dari sumber tidak dikenali",
                "sumber": "eksternal", "dari_cache": cached}
    return {"tingkat": level, "keterangan": None, "sumber": "eksternal", "dari_cache": cached}
