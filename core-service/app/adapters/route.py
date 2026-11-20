"""Adapter OSRM -> RuteKeDestinasi."""
from .http import cached_get_json
from ..config import settings

BASE = "https://router.project-osrm.org/route/v1/driving"


def get_route(from_lat: float, from_lon: float, to_lat: float, to_lon: float) -> dict:
    coords = f"{from_lon:.5f},{from_lat:.5f};{to_lon:.5f},{to_lat:.5f}"
    data, cached, _ = cached_get_json(f"route:{coords}", f"{BASE}/{coords}", settings.route_ttl,
                                      params={"overview": "simplified", "geometries": "geojson"})
    if data.get("code") != "Ok" or not data.get("routes"):
        raise ValueError("Rute tidak ditemukan")
    best = data["routes"][0]
    return {"jarak_km": round(best["distance"] / 1000, 2), "durasi_menit": round(best["duration"] / 60),
            "geometri": best.get("geometry"), "moda": "mobil", "sumber": "osrm", "dari_cache": cached}
