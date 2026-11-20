"""Tes kontrak: envelope, nama field English, enum English, ID string, waktu ISO UTC."""
from test_api import DEST, data_of, make_published
from conftest import ADMIN, KONTRIBUTOR, WISATAWAN

FORBIDDEN_KEYS = {"latitude", "longitude", "jarak_km", "radius_km", "ringkasan", "judul", "tautan", "sumber",
                  "dari_cache", "catatan", "items", "page", "size"}
CATEGORIES = {"nature", "culture_history", "local_culinary", "tourism_village", "craft"}
STATUSES = {"waiting", "published", "rejected"}


def keys_of(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from keys_of(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from keys_of(v)


def test_public_responses_follow_the_contract(client):
    d = make_published(client, name="Uji Kontrak Destinasi")
    story = client.post("/stories", json={"title": "Cerita Uji Kontrak", "destination_ids": [d["id"]],
                                          "body": "Cerita uji untuk kontrak, cukup panjang untuk lolos validasi isi. " * 2},
                        headers=ADMIN)
    assert story.status_code == 201
    client.post(f"/destinations/{d['id']}/reviews", json={"rating": 4}, headers=WISATAWAN)
    client.post("/plans", json={"destination_id": d["id"], "visit_date": "2099-01-01"}, headers=WISATAWAN)
    paths = [("/destinations", {}), (f"/destinations/{d['id']}", {}), (f"/destinations/{d['id']}/stories", {}),
             (f"/destinations/{d['id']}/reviews", {}), ("/stories", {}), ("/plans", WISATAWAN),
             ("/feed/destinations", {"X-API-Key": "jl_valid"})]
    for path, headers in paths:
        r = client.get(path, headers=headers)
        assert r.status_code == 200, (path, r.text)
        body = r.json()
        assert set(body) == {"data", "meta"}, path
        assert {"seq", "updated_at", "source", "stale"} <= set(body["meta"]), path
        assert body["meta"]["updated_at"].endswith("Z") and body["meta"]["source"] in ("live", "mock")
        assert not (set(keys_of(body["data"])) & FORBIDDEN_KEYS), path
        if isinstance(body["data"], list):
            assert "total" in body["meta"], path


def test_values_ids_and_times(client):
    d = make_published(client, name="Uji Kontrak Nilai")
    assert isinstance(d["id"], str) and d["category"] in CATEGORIES and d["status"] in STATUSES
    assert d["created_at"].endswith("Z") and d["updated_at"].endswith("Z")
    for item in data_of(client.get("/destinations?limit=200")):
        assert item["category"] in CATEGORIES and item["status"] in STATUSES and isinstance(item["id"], str)


def test_error_envelope(client):
    r = client.get("/destinations/999999")
    err = r.json()["error"]
    assert r.status_code == 404 and err["code"] == "not_found" and err["request_id"] and set(r.json()) == {"error"}
    r = client.get("/destinations?limit=0")
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"
    r = client.get("/feed/destinations")
    assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_api_key"
    r = client.post("/destinations", json=DEST, headers=WISATAWAN)
    assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden"