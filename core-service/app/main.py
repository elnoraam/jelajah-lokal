"""JelajahLokal core service.

Lima bounded context bisnis berjalan sebagai modul dalam satu proses dan saling
berkomunikasi lewat domain event (lihat events.py dan handlers.py). Identitas &
Akses berjalan di auth-service terpisah.
"""
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI

from . import handlers
from .config import settings
from .db import connect, get_conn, init_db
from .modules import conditions, destinations, feed, plans, reviews, stories
from .seed import seed_demo


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    handlers.register()
    if settings.seed_demo:
        conn = connect()
        seed_demo(conn)
        conn.close()
    yield


DESCRIPTION = """
Layanan wisata tersembunyi dan cerita budaya. Semua path relatif terhadap `/api`.

**Autentikasi**
- Pengguna aplikasi: `Authorization: Bearer <JWT>` dari `POST /api/auth/login`.
- Layanan lain (server ke server): header `X-API-Key`, hanya untuk `/feed/*`.
- Data publik (pencarian, cerita, kondisi) terbuka tanpa autentikasi, tetapi dibatasi jumlah pemanggilannya.
"""

app = FastAPI(title="JelajahLokal Core Service", version="1.0.0", description=DESCRIPTION, lifespan=lifespan)

for module in (destinations, stories, reviews, plans, conditions, feed):
    app.include_router(module.router)


@app.get("/health", tags=["umum"], summary="Cek layanan hidup")
def health(conn=Depends(get_conn)):
    conn.execute("SELECT 1")
    return {"status": "ok", "service": "core", "version": app.version}
