"""JelajahLokal core service.

Lima bounded context bisnis berjalan sebagai modul dalam satu proses dan saling
berkomunikasi lewat domain event (lihat events.py dan handlers.py). Identitas &
Akses berjalan di auth-service terpisah.
"""
import asyncio
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import handlers, mock
from .config import settings
from .db import connect, get_conn, init_db
from .modules import conditions, destinations, feed, mock_api, plans, reviews, stories
from .seed import seed_demo


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    handlers.register()
    if settings.seed_demo:
        conn = connect()
        seed_demo(conn)
        conn.close()
    task = None
    if settings.mock_mode or settings.mock_upstream_smartcity:
        conn = connect()
        mock.start(conn)
        conn.close()
        task = asyncio.create_task(mock.run_forever())
    yield
    if task:
        task.cancel()


DESCRIPTION = """
Layanan wisata tersembunyi dan cerita budaya. Semua path relatif terhadap `/api`.

**Autentikasi**
- Pengguna aplikasi: `Authorization: Bearer <JWT>` dari `POST /api/auth/login`.
- Layanan lain (server ke server): header `X-API-Key`, hanya untuk `/feed/*`.
- Data publik (pencarian, cerita, kondisi) terbuka tanpa autentikasi, tetapi dibatasi jumlah pemanggilannya.
"""

app = FastAPI(title="JelajahLokal Core Service", version="1.0.0", description=DESCRIPTION, lifespan=lifespan)

# Kode error mengikuti "unauthorized" (401 token JWT) dan "conflict" (409)
# sementara, menunggu persetujuan grup Smart City.
STATUS_CODE = {403: "forbidden", 404: "not_found", 409: "conflict", 422: "validation_error",
               429: "rate_limited", 503: "upstream_unavailable"}


def error_response(request: Request, status: int, code: str, message: str) -> JSONResponse:
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
    return JSONResponse({"error": {"code": code, "message": message, "request_id": request_id}},
                        status_code=status)


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 401:
        code = "invalid_api_key" if "/feed/" in request.url.path else "unauthorized"
    else:
        code = STATUS_CODE.get(exc.status_code, "error")
    return error_response(request, exc.status_code, code, str(exc.detail))


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    message = "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()[:5])
    return error_response(request, 422, "validation_error", message or "Input tidak valid")


for module in (destinations, stories, reviews, plans, conditions, feed):
    app.include_router(module.router)
if settings.mock_mode:  # /_mock/* hanya ada saat MOCK_MODE=true, selain itu 404
    app.include_router(mock_api.router)


@app.get("/health", tags=["umum"], summary="Cek layanan hidup")
def health(conn=Depends(get_conn)):
    conn.execute("SELECT 1")
    return {"status": "ok", "service": "core", "version": app.version}