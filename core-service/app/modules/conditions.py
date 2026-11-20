"""Konteks Kondisi Sekitar Destinasi (anti-corruption layer ke sumber luar)."""
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from ..adapters.http import UpstreamError
from ..adapters.risk import get_risk
from ..adapters.route import get_route
from ..adapters.weather import get_weather
from ..db import get_conn
from .common import get_published_destination, ok

router = APIRouter(tags=["kondisi-sekitar-destinasi"])


@router.get("/destinations/{destination_id}/conditions", summary="Cuaca dan tingkat risiko di sekitar destinasi")
def conditions(destination_id: int,
               date_: Optional[date] = Query(default=None, alias="date", description="YYYY-MM-DD, maksimal 14 hari ke depan"),
               conn=Depends(get_conn)):
    dest = get_published_destination(conn, destination_id)
    if date_ and not (date.today() <= date_ <= date.today() + timedelta(days=14)):
        raise HTTPException(422, "date harus antara hari ini dan 14 hari ke depan")
    try:
        weather = get_weather(dest["latitude"], dest["longitude"], date_.isoformat() if date_ else None)
    except UpstreamError:
        weather = {"message": "Data cuaca tidak dapat diambil dan belum ada data tersimpan",
                   "source": "open-meteo", "stale": False}
    risk = get_risk(dest["latitude"], dest["longitude"])
    stale = bool(weather.get("stale") or risk.get("stale"))
    return ok(conn, {"destination_id": str(destination_id), "destination_name": dest["name"],
                     "weather": weather, "risk": risk}, stale=stale)


@router.get("/destinations/{destination_id}/route", summary="Rute mobil menuju destinasi")
def route(destination_id: int, from_lat: float = Query(ge=-90, le=90), from_lon: float = Query(ge=-180, le=180),
          conn=Depends(get_conn)):
    dest = get_published_destination(conn, destination_id)
    try:
        r = get_route(from_lat, from_lon, dest["latitude"], dest["longitude"])
    except UpstreamError:
        raise HTTPException(503, "Layanan rute tidak dapat dihubungi dan belum ada data tersimpan")
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    return ok(conn, {"destination_id": str(destination_id), "destination_name": dest["name"], **r},
              stale=r["stale"])