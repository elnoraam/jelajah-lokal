"""Endpoint demo mock mode. Hanya didaftarkan saat MOCK_MODE=true, selain itu 404."""
import hmac
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from .. import mock
from ..config import settings
from ..db import get_conn
from ..security import User, optional_user
from .common import ok

router = APIRouter(prefix="/_mock", tags=["mock"])


def mock_admin(x_api_key: Optional[str] = Header(default=None), user: Optional[User] = Depends(optional_user)) -> None:
    """Admin lewat X-API-Key (sama dengan MOCK_ADMIN_API_KEY) atau JWT admin."""
    if x_api_key and settings.mock_admin_key and hmac.compare_digest(x_api_key, settings.mock_admin_key):
        return
    if user and user.role == "admin":
        return
    if not x_api_key and not user:
        raise HTTPException(401, "Header X-API-Key diperlukan")
    raise HTTPException(401 if x_api_key else 403, "API key admin tidak valid" if x_api_key else "Hanya admin")


class ScenarioIn(BaseModel):
    name: str = Field(pattern="^(" + "|".join(mock.SCENARIOS) + ")$")
    lat: Optional[float] = Field(default=None, ge=-90, le=90)
    lon: Optional[float] = Field(default=None, ge=-180, le=180)


@router.post("/scenario", summary="Picu skenario demo (admin, hanya MOCK_MODE=true)")
def run_scenario(body: ScenarioIn, _: None = Depends(mock_admin), conn=Depends(get_conn)):
    return ok(conn, mock.get_world().scenario(body.name, conn, lat=body.lat, lon=body.lon))


@router.get("/state", summary="Keadaan generator dan seed (admin, hanya MOCK_MODE=true)")
def mock_state(_: None = Depends(mock_admin), conn=Depends(get_conn)):
    return ok(conn, mock.get_world().state(conn))