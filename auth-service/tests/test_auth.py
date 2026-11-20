import os
import sys
import tempfile

os.environ["AUTH_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "auth.db")
os.environ["JWT_SECRET"] = "rahasia-uji-minimal-32-karakter-aman!!"
os.environ["INTERNAL_TOKEN"] = "token-internal-uji"
os.environ["ADMIN_EMAIL"] = "admin@uji.test"
os.environ["ADMIN_PASSWORD"] = "adminpass123"
os.environ["SEED_DEMO"] = "true"
os.environ["SEED_API_KEY"] = "jl_demo_key_uji"
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import jwt  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def login(client, email, pw):
    return client.post("/login", json={"email": email, "password": pw})


def bearer(client, email, pw):
    return {"Authorization": "Bearer " + login(client, email, pw).json()["access_token"]}


def test_register_login_me(client):
    r = client.post("/register", json={"email": "Budi@Contoh.test", "password": "rahasia123", "name": "Budi"})
    assert r.status_code == 201 and r.json()["role"] == "wisatawan" and r.json()["email"] == "budi@contoh.test"
    assert "password" not in r.text and "hash" not in r.text
    assert client.post("/register", json={"email": "budi@contoh.test", "password": "rahasia123", "name": "Budi"}).status_code == 409
    r = login(client, "budi@contoh.test", "rahasia123")
    assert r.status_code == 200
    tok = r.json()["access_token"]
    claims = jwt.decode(tok, os.environ["JWT_SECRET"], algorithms=["HS256"])
    assert claims["role"] == "wisatawan" and claims["name"] == "Budi" and "sub" in claims
    assert client.get("/me", headers={"Authorization": f"Bearer {tok}"}).json()["name"] == "Budi"
    assert client.get("/me").status_code == 401
    assert client.get("/me", headers={"Authorization": "Bearer rusak"}).status_code == 401


def test_bad_credentials_and_validation(client):
    assert login(client, "budi@contoh.test", "salah-salah").status_code == 401
    assert login(client, "tidakada@contoh.test", "rahasia123").status_code == 401
    assert client.post("/register", json={"email": "bukan-email", "password": "rahasia123", "name": "Ani"}).status_code == 422
    assert client.post("/register", json={"email": "a@b.test", "password": "pendek", "name": "Ani"}).status_code == 422


def test_cannot_self_register_as_admin(client):
    r = client.post("/register", json={"email": "x@y.test", "password": "rahasia123", "name": "Eve", "role": "admin"})
    assert r.status_code == 422


def test_seeded_accounts(client):
    assert login(client, "admin@uji.test", "adminpass123").json()["user"]["role"] == "admin"
    assert login(client, "kontributor@demo.test", "demo123").json()["user"]["role"] == "kontributor"
    assert login(client, "wisatawan@demo.test", "demo123").status_code == 200


def test_api_key_lifecycle(client):
    admin = bearer(client, "admin@uji.test", "adminpass123")
    user = bearer(client, "wisatawan@demo.test", "demo123")
    assert client.post("/api-keys", json={"name": "Layanan Uji"}).status_code == 401
    assert client.post("/api-keys", json={"name": "Layanan Uji"}, headers=user).status_code == 403
    r = client.post("/api-keys", json={"name": "Layanan Uji"}, headers=admin)
    assert r.status_code == 201
    key, key_id = r.json()["api_key"], r.json()["id"]
    assert key.startswith("jl_")
    listed = client.get("/api-keys", headers=admin).json()
    assert key not in str(listed) and any(k["id"] == key_id for k in listed)  # key tidak pernah tampil lagi
    internal = {"X-Internal-Token": "token-internal-uji"}
    assert client.post("/internal/verify-key", json={"key": key}, headers=internal).status_code == 200
    assert client.post("/internal/verify-key", json={"key": key}).status_code == 403
    assert client.post("/internal/verify-key", json={"key": key}, headers={"X-Internal-Token": "salah"}).status_code == 403
    assert client.post("/internal/verify-key", json={"key": "jl_demo_key_uji"}, headers=internal).status_code == 200
    assert client.delete(f"/api-keys/{key_id}", headers=admin).status_code == 200
    assert client.post("/internal/verify-key", json={"key": key}, headers=internal).status_code == 401
    assert client.delete("/api-keys/99999", headers=admin).status_code == 404


def test_health(client):
    assert client.get("/health").json() == {"status": "ok", "service": "auth"}
