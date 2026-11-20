"""Endpoint demo mock mode. Hanya didaftarkan saat MOCK_MODE=true, selain itu 404."""
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from .. import mock
from ..db import get_conn
from ..security import User, require_roles
from .common import ok

router = APIRouter(prefix="/_mock", tags=["mock"])


class ScenarioIn(BaseModel):
    name: str = Field(pattern="^(" + "|".join(mock.SCENARIOS) + ")$")
    lat: Optional[float] = Field(default=None, ge=-90, le=90)
    lon: Optional[float] = Field(default=None, ge=-180, le=180)


@router.post("/scenario", summary="Picu skenario demo (admin, hanya MOCK_MODE=true)")
def run_scenario(body: ScenarioIn, _: User = Depends(require_roles("admin")), conn=Depends(get_conn)):
    return ok(conn, mock.get_world().scenario(body.name, conn, lat=body.lat, lon=body.lon))


@router.get("/state", summary="Keadaan generator dan seed (admin, hanya MOCK_MODE=true)")
def mock_state(_: User = Depends(require_roles("admin")), conn=Depends(get_conn)):
    return ok(conn, mock.get_world().state(conn))