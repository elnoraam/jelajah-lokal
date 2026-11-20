import httpx
import pytest

from app.adapters import http as outbound
from app.adapters import risk
from app.config import settings

from conftest import ADMIN, KONTRIBUTOR, WISATAWAN, WISATAWAN2, WISATAWAN3

DEST = {"name": "Curug Rahasia Lembang", "category": "nature", "lat": -6.80, "lon": 107.60,
        "description": "Air terjun kecil di balik kebun teh yang jarang dikunjungi wisatawan luar kota.",
        "wikipedia_title": "Curug Cimahi"}
STORY = {"title": "Legenda Curug Rahasia", "destination_ids": [],
         "body": "Konon warga sekitar menjaga mata air ini selama berabad-abad dan menyebutnya sumber kehidupan kampung. " * 2}


def data_of(r):
    """Isi `data` dari envelope sukses, setelah memastikan envelope dan meta lengkap."""
    body = r.json()
    assert set(body) == {"data", "meta"}, body
    assert {"seq", "updated_at", "source", "stale"} <= set(body["meta"])
    return body["data"]


def make_published(client, **over):
    body = {**DEST, **over}
    r = client.post("/destinations", json=body, headers=KONTRIBUTOR)
    assert r.status_code == 201, r.text
    assert data_of(r)["status"] == "waiting"
    r = client.patch(f"/destinations/{data_of(r)['id']}/status", json={"status": "published"}, headers=ADMIN)
    assert r.status_code == 200, r.text
    return data_of(r)


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_destination_lifecycle_and_access(client):
    assert client.post("/destinations", json=DEST).status_code == 401
    assert client.post("/destinations", json=DEST, headers=WISATAWAN).status_code == 403
    r = client.post("/destinations", json=DEST, headers=KONTRIBUTOR)
    d = data_of(r)
    assert r.status_code == 201 and d["status"] == "waiting" and isinstance(d["id"], str)
    assert d["created_at"].endswith("Z") and d["lat"] == -6.80 and "latitude" not in d
    # belum terbit: tidak terlihat publik, terlihat pemilik dan admin
    assert client.get(f"/destinations/{d['id']}").status_code == 404
    assert client.get(f"/destinations/{d['id']}", headers=KONTRIBUTOR).status_code == 200
    assert client.get(f"/destinations/{d['id']}", headers=WISATAWAN).status_code == 404
    # hanya admin bisa mengubah status
    assert client.patch(f"/destinations/{d['id']}/status", json={"status": "published"}, headers=KONTRIBUTOR).status_code == 403
    r = client.patch(f"/destinations/{d['id']}/status", json={"status": "rejected"}, headers=ADMIN)
    assert r.status_code == 422  # alasan wajib
    r = client.patch(f"/destinations/{d['id']}/status", json={"status": "published"}, headers=ADMIN)
    assert r.status_code == 200 and data_of(r)["status"] == "published" and data_of(r)["hidden_gem"] is True
    assert client.patch(f"/destinations/{d['id']}/status", json={"status": "published"}, headers=ADMIN).status_code == 409
    assert client.get(f"/destinations/{d['id']}").status_code == 200
    assert client.get("/destinations/abc").status_code == 422


def test_validation(client):
    bad = {**DEST, "category": "mall"}
    assert client.post("/destinations", json=bad, headers=KONTRIBUTOR).status_code == 422
    bad = {**DEST, "category": "alam"}  # nilai Indonesia tidak lagi diterima di API
    assert client.post("/destinations", json=bad, headers=KONTRIBUTOR).status_code == 422
    bad = {**DEST, "lat": 51.5, "lon": -0.1}
    assert client.post("/destinations", json=bad, headers=KONTRIBUTOR).status_code == 422
    assert client.get("/destinations?lat=-6.9").status_code == 422
    assert client.get("/destinations?limit=201").status_code == 422
    assert client.get("/destinations", headers={"Authorization": "Bearer salah"}).status_code == 401


def test_search_filters_and_distance(client):
    a = make_published(client, name="Situ Sunyi Ciwidey", category="nature", lat=-7.10, lon=107.45)
    b = make_published(client, name="Warung Tua Cigondewah", category="local_culinary", lat=-6.95, lon=107.56)
    r = data_of(client.get("/destinations?category=local_culinary"))
    assert all(i["category"] == "local_culinary" for i in r) and any(i["id"] == b["id"] for i in r)
    r = data_of(client.get("/destinations?q=Situ Sunyi"))
    assert [i["id"] for i in r] == [a["id"]]
    near = data_of(client.get("/destinations?lat=-6.95&lon=107.56&radius_m=5000"))
    ids = [i["id"] for i in near]
    assert b["id"] in ids and a["id"] not in ids
    assert near[0]["distance_m"] <= 5000 and isinstance(near[0]["distance_m"], int)
    allr = data_of(client.get("/destinations?lat=-6.95&lon=107.56&limit=200"))
    assert [i["distance_m"] for i in allr] == sorted(i["distance_m"] for i in allr)
    mine = client.get("/destinations?mine=true", headers=KONTRIBUTOR).json()
    assert mine["meta"]["total"] >= 2
    one = client.get("/destinations?mine=true&limit=1&offset=1", headers=KONTRIBUTOR).json()
    assert len(one["data"]) == 1 and one["meta"]["total"] == mine["meta"]["total"]
    assert client.get("/destinations?mine=true").status_code == 401
    pend = data_of(client.get("/destinations?status=waiting"))
    assert all(i["status"] == "published" for i in pend)  # non-admin tidak bisa melihat waiting


def test_stories_and_short_mode(client):
    d = make_published(client, name="Kampung Ciptagelar Uji")
    r = client.post("/stories", json={**STORY, "destination_ids": [d["id"]]}, headers=WISATAWAN)
    assert r.status_code == 403
    r = client.post("/stories", json={**STORY, "destination_ids": ["999999"]}, headers=KONTRIBUTOR)
    assert r.status_code == 404
    r = client.post("/stories", json={**STORY, "destination_ids": [d["id"]]}, headers=KONTRIBUTOR)
    s = data_of(r)
    assert r.status_code == 201 and s["status"] == "waiting" and s["destination_ids"] == [d["id"]]
    assert client.get(f"/destinations/{d['id']}/stories").json()["meta"]["total"] == 0
    assert client.get(f"/stories/{s['id']}").status_code == 404
    assert client.patch(f"/stories/{s['id']}/status", json={"status": "published"}, headers=ADMIN).status_code == 200
    lst = client.get(f"/destinations/{d['id']}/stories").json()
    assert lst["meta"]["total"] == 1 and "excerpt" in lst["data"][0]
    full = data_of(client.get(f"/stories/{s['id']}"))
    short = data_of(client.get(f"/stories/{s['id']}?mode=short"))
    assert "body" in full and "body" not in short and len(short["excerpt"]) <= 283
    # event CeritaTerbit memperbarui story_count
    assert data_of(client.get(f"/destinations/{d['id']}"))["story_count"] == 1


def test_reviews_rating_hidden_gem_and_moderation(client):
    d = make_published(client, name="Desa Wisata Uji Ulasan")
    path = f"/destinations/{d['id']}/reviews"
    assert client.post(path, json={"rating": 5}).status_code == 401
    assert client.post(path, json={"rating": 6}, headers=WISATAWAN).status_code == 422
    r = client.post(path, json={"rating": 5, "comment": "Bagus"}, headers=WISATAWAN)
    assert r.status_code == 201
    review_id = data_of(r)["id"]
    assert client.post(path, json={"rating": 4}, headers=WISATAWAN).status_code == 409  # satu ulasan per pengguna
    r = client.post(path, json={"rating": 3}, headers=WISATAWAN2)
    assert r.status_code == 201
    det = data_of(client.get(f"/destinations/{d['id']}"))
    assert det["review_count"] == 2 and det["rating_avg"] == 4.0
    assert det["hidden_gem"] is False  # ambang uji = 2 ulasan
    # moderasi: ulasan disembunyikan -> rating dan penanda dihitung ulang
    assert client.post(f"/reviews/{review_id}/report", headers=WISATAWAN2).status_code == 200
    assert client.get("/reviews/reported", headers=WISATAWAN).status_code == 403
    assert any(i["id"] == review_id for i in data_of(client.get("/reviews/reported", headers=ADMIN)))
    r = client.patch(f"/reviews/{review_id}/moderation", json={"hidden": True}, headers=ADMIN)
    assert r.status_code == 200
    det = data_of(client.get(f"/destinations/{d['id']}"))
    assert det["review_count"] == 1 and det["rating_avg"] == 3.0 and det["hidden_gem"] is True
    listed = client.get(path).json()
    assert listed["meta"]["total"] == 1 and listed["meta"]["rating_avg"] == 3.0


def test_plans_are_private(client):
    d = make_published(client, name="Pasar Antik Uji Rencana")
    assert client.get("/plans").status_code == 401
    r = client.post("/plans", json={"destination_id": d["id"], "visit_date": "2000-01-01"}, headers=WISATAWAN)
    assert r.status_code == 422
    r = client.post("/plans", json={"destination_id": "999999", "visit_date": "2099-01-01"}, headers=WISATAWAN)
    assert r.status_code == 404
    r = client.post("/plans", json={"destination_id": d["id"], "visit_date": "2099-01-01", "note": "Bawa jaket"},
                    headers=WISATAWAN)
    plan = data_of(r)
    assert r.status_code == 201 and plan["destination_name"] == "Pasar Antik Uji Rencana"
    assert data_of(client.get("/plans", headers=WISATAWAN))[0]["id"] == plan["id"]
    assert data_of(client.get("/plans", headers=WISATAWAN2)) == []
    assert client.delete(f"/plans/{plan['id']}", headers=WISATAWAN2).status_code == 404
    assert client.delete(f"/plans/{plan['id']}", headers=WISATAWAN).status_code == 200

def test_conditions_with_fallback(client, monkeypatch):
    d = make_published(client, name="Bukit Uji Kondisi")
    calls = {"n": 0}

    def fake_get(url, params=None, headers=None, timeout=None):
        calls["n"] += 1
        if calls["n"] > 1 and "open-meteo" in url:
            raise httpx.ConnectError("mati")
        req = httpx.Request("GET", url)
        return httpx.Response(200, request=req, json={"current": {"temperature_2m": 21.5, "rain": 0.2, "weather_code": 61}})

    monkeypatch.setattr(httpx, "get", fake_get)
    monkeypatch.setattr(settings, "weather_ttl", 0)  # paksa panggil ulang agar fallback teruji
    r = client.get(f"/destinations/{d['id']}/conditions")
    assert r.status_code == 200
    body, meta = r.json()["data"], r.json()["meta"]
    assert body["destination_id"] == str(d["id"])
    assert body["weather"]["temperature_c"] == 21.5 and body["weather"]["description"] == "Hujan ringan"
    assert body["weather"]["stale"] is False and meta["stale"] is False and meta["source"] == "live"
    assert body["risk"]["risk_level"] is None and "belum tersedia" in body["risk"]["message"]
    # sumber mati -> data terakhir dikembalikan dengan stale=true
    r2 = client.get(f"/destinations/{d['id']}/conditions").json()
    assert r2["data"]["weather"]["temperature_c"] == 21.5 and r2["data"]["weather"]["stale"] is True
    assert r2["meta"]["stale"] is True
    bad = client.get(f"/destinations/{d['id']}/conditions?date=2001-01-01")
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "validation_error"


def test_conditions_no_data_message(client, monkeypatch):
    d = make_published(client, name="Bukit Uji Tanpa Data")
    monkeypatch.setattr(httpx, "get", lambda *a, **k: (_ for _ in ()).throw(httpx.ConnectError("mati")))
    r = client.get(f"/destinations/{d['id']}/conditions")
    assert r.status_code == 200 and "tidak dapat diambil" in r.json()["data"]["weather"]["message"]


def test_risk_adapter(monkeypatch):
    monkeypatch.setattr(settings, "risk_url", "https://sumber.contoh/risk")
    monkeypatch.setattr(settings, "risk_level_field", "data.risk_level")

    def serve(payload):
        monkeypatch.setattr(httpx, "get", lambda url, params=None, headers=None, timeout=None: httpx.Response(
            200, request=httpx.Request("GET", url), json=payload))
        outbound.clear_cache()
        return risk.get_risk(-6.9, 107.6)

    out = serve({"data": {"risk_level": "caution"}, "meta": {"stale": False}})
    assert out["risk_level"] == "caution" and out["stale"] is False and out["source"] == "kotasiaga"
    # nilai di luar kontrak ditolak, tidak ditebak
    out = serve({"data": {"risk_level": "yellow"}})
    assert out["risk_level"] is None and "tidak dikenali" in out["message"]
    # stale dari sumber diteruskan
    assert serve({"data": {"risk_level": "danger"}, "meta": {"stale": True}})["stale"] is True
    # sumber mati dan tanpa cache
    monkeypatch.setattr(httpx, "get", lambda *a, **k: (_ for _ in ()).throw(httpx.ConnectError("mati")))
    outbound.clear_cache()
    out = risk.get_risk(-6.9, 107.6)
    assert out["risk_level"] is None and "tidak dapat dihubungi" in out["message"]


def test_route(client, monkeypatch):
    d = make_published(client, name="Bukit Uji Rute")

    def fake_get(url, params=None, headers=None, timeout=None):
        return httpx.Response(200, request=httpx.Request("GET", url), json={
            "code": "Ok", "routes": [{"distance": 12345, "duration": 1500,
                                      "geometry": {"type": "LineString", "coordinates": [[107.6, -6.9], [107.61, -6.8]]}}]})

    monkeypatch.setattr(httpx, "get", fake_get)
    r = client.get(f"/destinations/{d['id']}/route?from_lat=-6.9&from_lon=107.6")
    data = r.json()["data"]
    assert r.status_code == 200 and data["distance_m"] == 12345 and data["duration_s"] == 1500
    assert data["mode"] == "driving" and r.json()["meta"]["stale"] is False
    assert client.get(f"/destinations/{d['id']}/route").status_code == 422
    monkeypatch.setattr(httpx, "get", lambda *a, **k: (_ for _ in ()).throw(httpx.ConnectError("mati")))
    assert client.get(f"/destinations/{d['id']}/route?from_lat=1&from_lon=2").status_code == 503


def test_background_wikipedia(client, monkeypatch):
    d = make_published(client, name="Situs Uji Wikipedia")
    nowiki = make_published(client, name="Situs Tanpa Wikipedia", wikipedia_title=None)
    monkeypatch.setattr(httpx, "get", lambda url, **k: httpx.Response(
        200, request=httpx.Request("GET", url),
        json={"title": "Curug Cimahi", "extract": "Air terjun di Bandung Barat.",
              "content_urls": {"desktop": {"page": "https://id.wikipedia.org/wiki/Curug_Cimahi"}}}))
    r = client.get(f"/destinations/{d['id']}/background")
    assert r.status_code == 200 and data_of(r)["summary"].startswith("Air terjun")
    assert client.get(f"/destinations/{nowiki['id']}/background").status_code == 404

def test_feed_requires_api_key_and_hides_private_data(client):
    d = make_published(client, name="Sumber Uji Umpan")
    h = {"X-API-Key": "jl_valid"}
    for headers in ({}, {"X-API-Key": "salah"}):
        r = client.get("/feed/destinations", headers=headers)
        assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_api_key"
    r = client.get("/feed/destinations?limit=200", headers=h)
    assert r.status_code == 200
    item = next(i for i in r.json()["data"] if i["id"] == str(d["id"]))
    assert set(item) == {"id", "name", "category", "lat", "lon", "updated_at"}
    assert item["category"] == "nature" and item["lat"] == -6.80 and item["lon"] == 107.60
    assert item["updated_at"].endswith("Z")
    assert {"seq", "updated_at", "source", "stale", "total"} <= set(r.json()["meta"])
    # data yang belum terbit tidak ikut
    pending = data_of(client.post("/destinations", json={**DEST, "name": "Belum Terbit Uji"}, headers=KONTRIBUTOR))
    ids = [i["id"] for i in client.get("/feed/destinations?limit=200", headers=h).json()["data"]]
    assert str(pending["id"]) not in ids
    # paginasi limit/offset
    page = client.get("/feed/destinations?limit=1&offset=0", headers=h).json()
    assert len(page["data"]) == 1 and page["meta"]["total"] >= 1
    assert client.get("/feed/destinations?limit=201", headers=h).status_code == 422
    # updated_since: ISO 8601 UTC
    future = client.get("/feed/destinations?updated_since=2999-01-01T00:00:00Z", headers=h).json()
    assert future["data"] == [] and future["meta"]["total"] == 0
    bad = client.get("/feed/destinations?updated_since=kemarin", headers=h)
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "validation_error"


def test_admin_publishes_directly(client):
    r = client.post("/destinations", json={**DEST, "name": "Langsung Terbit Admin"}, headers=ADMIN)
    assert r.status_code == 201 and data_of(r)["status"] == "published" and data_of(r)["hidden_gem"] is True


def test_meta_seq_increases_on_data_change(client, monkeypatch):
    d = make_published(client, name="Bukit Uji Seq")
    monkeypatch.setattr(httpx, "get", lambda *a, **k: (_ for _ in ()).throw(httpx.ConnectError("mati")))
    s1 = client.get(f"/destinations/{d['id']}/conditions").json()["meta"]["seq"]
    assert client.get(f"/destinations/{d['id']}/conditions").json()["meta"]["seq"] == s1  # tanpa perubahan, seq tetap
    make_published(client, name="Bukit Uji Seq Dua")
    assert client.get(f"/destinations/{d['id']}/conditions").json()["meta"]["seq"] > s1


def test_weather_from_kotasiaga_with_fallback(monkeypatch):
    from app.adapters import weather
    monkeypatch.setattr(settings, "weather_url", "https://kotasiaga.contoh/api/weather")
    monkeypatch.setattr(settings, "weather_ttl", 0)
    state = {"sc": "ok", "om": "ok"}
    calls = []

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.append(url)
        req = httpx.Request("GET", url)
        if "kotasiaga" in url:
            if state["sc"] == "down":
                raise httpx.ConnectError("mati")
            return httpx.Response(200, request=req, json={
                "data": {"temperature_c": 27.4, "rain_mm_h": 18.0, "condition": "heavy_rain"},
                "meta": {"stale": False}})
        if state["om"] == "down":
            raise httpx.ConnectError("mati")
        return httpx.Response(200, request=req, json={"current": {"temperature_2m": 21.5, "rain": 0.2, "weather_code": 61}})

    monkeypatch.setattr(httpx, "get", fake_get)
    outbound.clear_cache()
    w = weather.get_weather(-6.9, 107.6)
    assert w["source"] == "kotasiaga" and w["temperature_c"] == 27.4 and w["rain_mm"] == 18.0
    assert w["condition"] == "heavy_rain" and w["stale"] is False
    state.update(sc="down", om="down")   # keduanya mati: data KotaSiaga lama dikembalikan sebagai stale
    w = weather.get_weather(-6.9, 107.6)
    assert w["source"] == "kotasiaga" and w["stale"] is True
    state.update(sc="down", om="ok")     # hanya KotaSiaga mati: Open-Meteo segar dipakai
    w = weather.get_weather(-6.9, 107.6)
    assert w["source"] == "open-meteo" and w["stale"] is False and w["condition"] == "rain"
    calls.clear()                        # dengan date, KotaSiaga tidak dipanggil
    state.update(sc="ok", om="ok")
    assert weather.get_weather(-6.9, 107.6, "2026-11-21")["source"] == "open-meteo"
    assert not any("kotasiaga" in c for c in calls)