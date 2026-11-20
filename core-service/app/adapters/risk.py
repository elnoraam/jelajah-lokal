"""Anti-corruption layer untuk sumber status risiko wilayah (KotaSiaga).

Data dari sumber luar divalidasi terhadap kontrak: hanya safe, caution, dan danger yang
diterima, field lain dibuang. Alamat, kunci, dan nama field dikonfigurasi lewat environment
sehingga sumber dapat diganti tanpa mengubah kode konteks lain.
"""
from ..config import settings
from .http import UpstreamError, cached_get_json

RISK_LEVELS = {"safe", "caution", "danger"}
SOURCE = "kotasiaga"


def _dig(obj, field: str):
    for part in field.split("."):
        if isinstance(obj, dict):
            obj = obj.get(part)
        else:
            return None
    return obj


def _result(level, message, stale: bool, source=SOURCE) -> dict:
    return {"risk_level": level, "message": message, "source": source, "stale": stale}


def get_risk(lat: float, lon: float) -> dict:
    if not settings.risk_url:
        return _result(None, "Data risiko belum tersedia (sumber belum dikonfigurasi)", False, source=None)
    headers = {settings.risk_key_header: settings.risk_key} if settings.risk_key else {}
    params = {settings.risk_lat_param: round(lat, 4), settings.risk_lon_param: round(lon, 4)}
    try:
        data, stale, _ = cached_get_json(f"risk:{params}", settings.risk_url, settings.risk_ttl,
                                         params=params, headers=headers, service=SOURCE)
    except UpstreamError:
        return _result(None, "Data risiko belum tersedia (sumber tidak dapat dihubungi)", False)
    stale = stale or _dig(data, "meta.stale") is True
    level = _dig(data, settings.risk_level_field)
    if not (isinstance(level, str) and level in RISK_LEVELS):
        return _result(None, "Format data risiko dari sumber tidak dikenali", stale)
    return _result(level, None, stale)