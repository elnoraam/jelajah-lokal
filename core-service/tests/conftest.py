import os
import sys
import tempfile
import time

import jwt
import pytest

os.environ["CORE_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "core.db")
os.environ["JWT_SECRET"] = "rahasia-uji-minimal-32-karakter-aman!!"
os.environ["HIDDEN_MAX_REVIEWS"] = "2"
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastapi.testclient import TestClient  # noqa: E402

from app import security  # noqa: E402
from app.adapters import http as outbound  # noqa: E402
from app.config import settings  # noqa: E402
from app.main import app  # noqa: E402


def token(uid: int, role: str, name: str = "Uji") -> dict:
    payload = {"sub": str(uid), "role": role, "name": name, "exp": int(time.time()) + 3600}
    return {"Authorization": "Bearer " + jwt.encode(payload, settings.jwt_secret, algorithm="HS256")}


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def isolate(monkeypatch):
    outbound.clear_cache()
    monkeypatch.setattr(security, "verify_api_key_remote", lambda key: key == "jl_valid")


ADMIN = token(1, "admin", "Admin")
KONTRIBUTOR = token(2, "kontributor", "Kontri")
WISATAWAN = token(3, "wisatawan", "Wisata")
WISATAWAN2 = token(4, "wisatawan", "Wisata Dua")
WISATAWAN3 = token(5, "wisatawan", "Wisata Tiga")
