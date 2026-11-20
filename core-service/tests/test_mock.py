import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import mock
from app.adapters import risk, weather
from app.config import settings
from app.db import connect, init_db
from app.meta import current_seq
from app.modules import mock_api

from conftest import ADMIN, WISATAWAN


@pytest.fixture
def mock_env(tmp_path, monkeypatch):
    """Database terpisah supaya data mock tidak mengotori tes lain."""
    monkeypatch.setattr(settings, "db_path", str(tmp_path / "mock.db"))
    monkeypatch.setattr(settings, "mock_mode", True)
    monkeypatch.setattr(settings, "mock_seed", 123)
    monkeypatch.setattr(settings, "risk_url", "mock://kotasiaga/risk")
    monkeypatch.setattr(settings, "weather_url", "mock://kotasiaga/weather")
    monkeypatch.setattr(mock, "_world", None)
    init_db()
    conn = connect()
    world = mock.start(conn)
    yield conn, world
    conn.close()


def test_mock_start_seeds_destinations_with_given_seed(mock_env):
    conn, world = mock_env
    state = world.state(conn)
    assert state["seed"] == 123
    assert state["mock_destinations"] == {"published": 8, "unpublished": 4}


def test_mock_inputs_are_deterministic_for_same_seed():
    a, b = mock.MockWorld(7), mock.MockWorld(7)
    for i in range(60):
        a.step_inputs(1000 + i * 5)
        b.step_inputs(1000 + i * 5)
    assert (a.rain, a.disasters, a.fault_service) == (b.rain, b.disasters, b.fault_service)


def test_mock_risk_is_computed_from_inputs():
    world, now = mock.MockWorld(1), time.time()
    world.rain = 0
    assert world.risk_level(-6.9, 107.6, now) == "safe"
    world.rain = 60
    assert world.risk_level(-6.9, 107.6, now) == "caution"
    world.add_disaster(now, -6.9, 107.6)
    assert world.risk_level(-6.9, 107.6, now) == "danger"


def test_mock_tick_advances_seq_and_keeps_feed_non_empty(mock_env):
    conn, world = mock_env
    start, kinds = time.time(), set()
    for i in range(300):
        before = current_seq(conn)
        world.tick(conn, now=start + i * 5)
        assert current_seq(conn) > before          # dua panggilan berjarak 10 detik selalu beda seq
        if world.last_action and "type" in world.last_action:
            kinds.add(world.last_action["type"])
        published = conn.execute(
            "SELECT COUNT(*) FROM destinations WHERE submitted_by=? AND status='terbit'", (mock.MOCK_OWNER,)).fetchone()[0]
        assert published >= mock.MIN_PUBLISHED
    assert kinds == {"publish", "unpublish"}


def test_mock_data_goes_through_real_adapters(mock_env):
    _, world = mock_env
    out = risk.get_risk(-6.9, 107.6)
    assert out["risk_level"] in {"safe", "caution", "danger"} and out["source"] == "kotasiaga" and out["stale"] is False
    w = weather.get_weather(-6.9, 107.6)
    assert w["source"] == "kotasiaga" and w["condition"] in weather.CONDITIONS
    daily = weather.get_weather(-6.9, 107.6, "2026-11-21")
    assert daily["source"] == "open-meteo" and "temperature_max_c" in daily


def test_mock_upstream_fault_returns_stale_then_fallback(mock_env):
    _, world = mock_env
    assert risk.get_risk(-6.9, 107.6)["stale"] is False
    world.fault_service, world.fault_until = "kotasiaga", time.time() + 30
    out = risk.get_risk(-6.9, 107.6)
    assert out["stale"] is True and out["risk_level"] is not None
    w = weather.get_weather(-6.9, 107.6)               # KotaSiaga mati -> Open-Meteo (mock) segar
    assert w["source"] == "open-meteo" and w["stale"] is False


def test_mock_endpoints_are_404_when_mock_is_off(client):
    r = client.get("/_mock/state", headers=ADMIN)
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"


def test_mock_scenario_endpoint_needs_admin(mock_env):
    app = FastAPI()
    app.include_router(mock_api.router)
    with TestClient(app) as c:
        assert c.post("/_mock/scenario", json={"name": "rain_storm"}).status_code == 401
        assert c.post("/_mock/scenario", json={"name": "rain_storm"}, headers=WISATAWAN).status_code == 403
        r = c.post("/_mock/scenario", json={"name": "rain_storm"}, headers=ADMIN)
        assert r.status_code == 200 and r.json()["data"]["storm_active"] is True
        assert r.json()["meta"]["source"] == "mock"
        assert c.post("/_mock/scenario", json={"name": "tidak_ada"}, headers=ADMIN).status_code == 422
        assert c.get("/_mock/state", headers=ADMIN).json()["data"]["seed"] == 123


def test_mock_scenario_accepts_admin_api_key(mock_env, monkeypatch):
    monkeypatch.setattr(settings, "mock_admin_key", "kunci-admin-uji")
    app = FastAPI()
    app.include_router(mock_api.router)
    with TestClient(app) as c:
        body = {"name": "rain_storm"}
        assert c.post("/_mock/scenario", json=body, headers={"X-API-Key": "salah"}).status_code == 401
        r = c.post("/_mock/scenario", json=body, headers={"X-API-Key": "kunci-admin-uji"})
        assert r.status_code == 200 and r.json()["data"]["storm_active"] is True
        assert c.get("/_mock/state", headers={"X-API-Key": "kunci-admin-uji"}).status_code == 200