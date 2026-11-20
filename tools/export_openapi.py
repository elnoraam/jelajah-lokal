"""Ekspor kontrak OpenAPI. Pakai:  python tools/export_openapi.py core|auth  > docs/openapi-<nama>.yaml"""
import os
import sys
import tempfile

import yaml

which = sys.argv[1]
root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(root, f"{which}-service"))
os.environ.setdefault("CORE_DB_PATH", os.path.join(tempfile.mkdtemp(), "x.db"))
os.environ.setdefault("AUTH_DB_PATH", os.path.join(tempfile.mkdtemp(), "x.db"))
from app.main import app  # noqa: E402

spec = app.openapi()
spec["servers"] = [{"url": "https://chitatomigoreng.stei.site" + ("/api" if which == "core" else "/api/auth")}]
if which == "core":
    spec.setdefault("components", {}).setdefault("securitySchemes", {}).update(
        BearerJWT={"type": "http", "scheme": "bearer", "bearerFormat": "JWT"},
        ApiKey={"type": "apiKey", "in": "header", "name": "X-API-Key"})
yaml.safe_dump(spec, sys.stdout, allow_unicode=True, sort_keys=False)
