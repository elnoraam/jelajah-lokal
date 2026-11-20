"""Adapter OSRM -> RuteKeDestinasi."""
from ..config import settings
from .http import cached_get_json

BASE = "https://router.project-osrm.org/route/v1/driving"


def get_route(from_lat: float, from_lon: float, to_lat: float, to_lon: float) -> dict:
    coords = f"{from_lon:.5f},{from_lat:.5f};{to_lon:.5f},{to_lat:.5f}"
    data, stale, _ = cached_get_json(f"route:{coords}", f"{BASE}/{coords}", settings.route_ttl,
                                     params={"overview": "simplified", "geometries": "geojson"},
                                     service="osrm")
    if data.get("code") != "Ok" or not data.get("routes"):
        raise ValueError("Rute tidak ditemukan")
    best = data["routes"][0]
    return {"distance_m": round(best["distance"]), "duration_s": round(best["duration"]),
            "geometry": best.get("geometry"), "mode": "driving", "source": "osrm", "stale": stale}