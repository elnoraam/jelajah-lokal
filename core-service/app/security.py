import time
from typing import Optional

import httpx
import jwt
from fastapi import Depends, Header, HTTPException

from .config import settings

_key_cache: dict[str, tuple[float, bool]] = {}


class User(dict):
    @property
    def id(self) -> int:
        return int(self["sub"])

    @property
    def role(self) -> str:
        return self["role"]

    @property
    def name(self) -> str:
        return self.get("name", "")


def _decode(token: str) -> User:
    try:
        return User(jwt.decode(token, settings.jwt_secret, algorithms=["HS256"]))
    except jwt.PyJWTError:
        raise HTTPException(401, "Token tidak valid atau kedaluwarsa")


def optional_user(authorization: Optional[str] = Header(default=None)) -> Optional[User]:
    if not authorization:
        return None
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Format Authorization harus 'Bearer <token>'")
    return _decode(authorization[7:])


def current_user(user: Optional[User] = Depends(optional_user)) -> User:
    if user is None:
        raise HTTPException(401, "Login diperlukan")
    return user


def require_roles(*roles: str):
    def dep(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(403, "Peran Anda tidak diizinkan untuk aksi ini")
        return user
    return dep


def verify_api_key_remote(key: str) -> bool:
    """Tanya auth-service apakah API key valid. Hasil di-cache singkat."""
    now = time.time()
    hit = _key_cache.get(key)
    if hit and hit[0] > now:
        return hit[1]
    try:
        r = httpx.post(f"{settings.auth_url}/internal/verify-key", json={"key": key},
                       headers={"X-Internal-Token": settings.internal_token}, timeout=3)
    except httpx.HTTPError:
        raise HTTPException(503, "Layanan autentikasi tidak dapat dihubungi")
    ok = r.status_code == 200
    if r.status_code not in (200, 401):
        raise HTTPException(503, "Layanan autentikasi tidak dapat dihubungi")
    _key_cache[key] = (now + (60 if ok else 10), ok)
    return ok


def api_key_required(x_api_key: Optional[str] = Header(default=None)) -> str:
    if not x_api_key:
        raise HTTPException(401, "Header X-API-Key diperlukan")
    if not verify_api_key_remote(x_api_key):
        raise HTTPException(401, "API key tidak valid")
    return x_api_key
