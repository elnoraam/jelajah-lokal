"""Mock mode.

Yang dimock adalah masukan, bukan keluaran. Generator hanya membangkitkan respons sumber
luar dalam format aslinya (KotaSiaga, Open-Meteo, OSRM, Wikipedia) dan mengubah status
destinasi lewat event yang sama dengan kode asli. Pemetaan, validasi, cache, dan fallback
tetap dijalankan oleh adapter dan modul yang sebenarnya.
"""
import asyncio
import logging
import math
import random
import time
import zlib
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import quote, unquote

from . import events
from .config import settings
from .db import connect
from .meta import bump_seq

log = logging.getLogger("mock")
if not log.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(asctime)s %(name)s %(message)s", "%Y-%m-%dT%H:%M:%S"))
    log.addHandler(_handler)
    log.setLevel(logging.INFO)
    log.propagate = False

MOCK_OWNER = -1            # submitted_by untuk destinasi buatan generator
MIN_PUBLISHED = 4          # umpan tidak pernah kosong saat generator berjalan
INITIAL_PUBLISHED = 8
LAT_RANGE, LON_RANGE = (-6.98, -6.84), (107.54, 107.72)   # Bandung, sama dengan generator Smart City
CENTER = (-6.9147, 107.6098)
SCENARIOS = ("publish_destination", "unpublish_destination", "rain_storm", "disaster_signal",
             "upstream_down", "recover", "reset")

# (nama, kategori, lat, lon). Nama berisi "Uji": data uji, bukan data resmi.
DESTINATIONS = [
    ("Kampung Uji Dago Pakar", "desa-wisata", -6.8610, 107.6290),
    ("Taman Hutan Uji Cigadung", "alam", -6.8790, 107.6370),
    ("Sentra Kerajinan Uji Cibaduyut", "kerajinan", -6.9440, 107.6020),
    ("Kuliner Uji Braga", "kuliner-lokal", -6.9175, 107.6091),
    ("Museum Uji Asia Afrika", "budaya-sejarah", -6.9211, 107.6098),
    ("Rumah Adat Uji Cigondewah", "budaya-sejarah", -6.9330, 107.5560),
    ("Bukit Uji Ciumbuleuit", "alam", -6.8730, 107.6020),
    ("Desa Wisata Uji Cibiru", "desa-wisata", -6.9300, 107.7120),
    ("Pasar Uji Kosambi", "kuliner-lokal", -6.9170, 107.6190),
    ("Sanggar Batik Uji Ciwaruga", "kerajinan", -6.8660, 107.5790),
    ("Curug Uji Gegerkalong", "alam", -6.8590, 107.5900),
    ("Kampung Uji Pasir Impun", "desa-wisata", -6.8980, 107.6780),
]


class MockUpstreamDown(Exception):
    """Sumber luar yang dimock sedang 'mati' (gangguan acak atau skenario upstream_down)."""


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * 6371.0088 * math.asin(math.sqrt(a))


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _crc(lat: float, lon: float) -> int:
    return zlib.crc32(f"{lat:.2f},{lon:.2f}".encode())


class MockWorld:
    def __init__(self, seed: int):
        self.seed = seed
        self.rng = random.Random(seed)
        self.rain = 0.0                       # mm per jam
        self.storm_until = 0.0
        self.storm_floor, self.storm_peak = 25.0, 45.0
        self.disasters: list[tuple[float, float, float]] = []   # (lat, lon, sampai)
        self.fault_service: Optional[str] = None
        self.fault_until = 0.0
        self.ticks = 0
        self.last_level: Optional[str] = None
        self.last_transition = time.time()
        self.last_action: Optional[dict] = None

    # ---- masukan yang dibangkitkan ----
    def start_storm(self, now: float, heavy: bool = False) -> None:
        self.storm_until = now + self.rng.uniform(60, 120)
        self.storm_floor, self.storm_peak = (50.0, 60.0) if heavy else (25.0, 45.0)
        self.rain = self.rng.uniform(55, 60) if heavy else self.rng.uniform(25, 45)

    def add_disaster(self, now: float, lat: Optional[float] = None, lon: Optional[float] = None) -> None:
        lat = self.rng.uniform(*LAT_RANGE) if lat is None else lat
        lon = self.rng.uniform(*LON_RANGE) if lon is None else lon
        self.disasters.append((lat, lon, now + self.rng.uniform(120, 300)))

    def step_inputs(self, now: float) -> None:
        self.ticks += 1
        if now < self.storm_until:
            self.rain = min(self.storm_peak, max(self.storm_floor, self.rain + self.rng.uniform(-3, 3)))
        elif self.rain < 1.0 and self.rng.random() < 0.10:
            self.start_storm(now)
        else:
            self.rain = min(60.0, max(0.0, self.rain + self.rng.uniform(-4, 4) - 0.1 * self.rain))
        self.disasters = [d for d in self.disasters if d[2] > now]
        if len(self.disasters) < 3 and self.rng.random() < 0.02:
            self.add_disaster(now)
        if self.fault_service is not None and now >= self.fault_until:
            self.fault_service = None
        if self.fault_service is None and self.rng.random() < 0.03:
            self.fault_service = self.rng.choice(["kotasiaga", "open-meteo", "osrm"])
            self.fault_until = now + self.rng.uniform(20, 40)
        level = self.risk_level(*CENTER, now)
        if self.last_level is None or level != self.last_level:
            self.last_level, self.last_transition = level, now
        elif now - self.last_transition > 120:      # demo tidak boleh terlihat beku
            self.start_storm(now, heavy=True)
            self.last_transition = now

    # ---- risiko dihitung dari masukan, tidak pernah ditulis langsung ----
    def score(self, lat: float, lon: float, now: float) -> tuple[float, float, int]:
        jitter = 0.9 + (_crc(lat, lon) % 21) / 100
        rain = min(60.0, self.rain * jitter)
        near = sum(1 for dlat, dlon, until in self.disasters
                   if until > now and _haversine_km(lat, lon, dlat, dlon) <= 1.5)
        return min(rain / 50, 1) * 0.4 + 0.4 * near, rain, near

    @staticmethod
    def level(score: float) -> str:
        return "safe" if score < 0.35 else "caution" if score < 0.7 else "danger"

    def risk_level(self, lat: float, lon: float, now: Optional[float] = None) -> str:
        return self.level(self.score(lat, lon, time.time() if now is None else now)[0])

    # ---- destinasi: publish / unpublish lewat event yang sama dengan kode asli ----
    def toggle_destination(self, conn, direction: Optional[str] = None) -> Optional[dict]:
        rows = conn.execute("SELECT id, status FROM destinations WHERE submitted_by=? ORDER BY id",
                            (MOCK_OWNER,)).fetchall()
        published = [r["id"] for r in rows if r["status"] == "terbit"]
        pending = [r["id"] for r in rows if r["status"] != "terbit"]
        options = (["publish"] if pending else []) + (["unpublish"] if len(published) > MIN_PUBLISHED else [])
        if direction is not None and direction not in options:
            return None
        direction = direction or (self.rng.choice(options) if options else None)
        if direction is None:
            return None
        if direction == "publish":
            dest_id = self.rng.choice(pending)
            conn.execute("UPDATE destinations SET status='terbit', reject_reason=NULL, "
                         "updated_at=datetime('now') WHERE id=?", (dest_id,))
            events.publish("DestinasiTerbit", conn, destination_id=dest_id)
        else:
            dest_id = self.rng.choice(published)
            conn.execute("UPDATE destinations SET status='menunggu', updated_at=datetime('now') WHERE id=?", (dest_id,))
            events.publish("DestinasiDiperbarui", conn, destination_id=dest_id)
        self.last_action = {"type": direction, "destination_id": str(dest_id)}
        return self.last_action

    def tick(self, conn=None, now: Optional[float] = None, toggle: bool = True) -> None:
        now = time.time() if now is None else now
        self.step_inputs(now)
        if conn is None:
            return
        if toggle and self.rng.random() < settings.mock_tick_seconds / 30:    # kira-kira tiap 30 detik
            self.toggle_destination(conn)
        bump_seq(conn)
        conn.commit()

    # ---- skenario demo ----
    def scenario(self, name: str, conn, now: Optional[float] = None,
                 lat: Optional[float] = None, lon: Optional[float] = None) -> dict:
        now = time.time() if now is None else now
        applied = {"scenario": name}
        if name == "publish_destination":
            applied["result"] = self.toggle_destination(conn, "publish")
        elif name == "unpublish_destination":
            applied["result"] = self.toggle_destination(conn, "unpublish")
        elif name == "rain_storm":
            self.start_storm(now, heavy=True)
        elif name == "disaster_signal":
            self.add_disaster(now, lat, lon)
        elif name == "upstream_down":
            self.fault_service, self.fault_until = "kotasiaga", now + 40
        elif name == "recover":
            self.fault_service, self.fault_until = None, 0.0
        elif name == "reset":
            self.rain, self.storm_until, self.disasters = 0.0, 0.0, []
            self.fault_service, self.fault_until = None, 0.0
            ids = [r["id"] for r in conn.execute(
                "SELECT id FROM destinations WHERE submitted_by=? ORDER BY id", (MOCK_OWNER,))]
            for i, dest_id in enumerate(ids):
                conn.execute("UPDATE destinations SET status=?, updated_at=datetime('now') WHERE id=?",
                             ("terbit" if i < INITIAL_PUBLISHED else "menunggu", dest_id))
                events.publish("DestinasiDiperbarui", conn, destination_id=dest_id)
        else:
            raise ValueError(f"skenario tidak dikenal: {name}")
        self.last_action = applied
        bump_seq(conn)
        conn.commit()
        return self.state(conn, now)

    def state(self, conn, now: Optional[float] = None) -> dict:
        now = time.time() if now is None else now
        row = conn.execute("SELECT SUM(status='terbit') p, SUM(status!='terbit') w FROM destinations "
                           "WHERE submitted_by=?", (MOCK_OWNER,)).fetchone()
        down = self.fault_service is not None and now < self.fault_until
        return {"seed": self.seed, "tick_seconds": settings.mock_tick_seconds, "ticks": self.ticks,
                "rain_mm_h": round(self.rain, 1), "storm_active": now < self.storm_until,
                "disaster_signals": sum(1 for d in self.disasters if d[2] > now),
                "risk_level_center": self.risk_level(*CENTER, now),
                "fault": {"service": self.fault_service, "seconds_left": max(0, round(self.fault_until - now))} if down else None,
                "mock_destinations": {"published": row["p"] or 0, "unpublished": row["w"] or 0},
                "last_action": self.last_action}

    # ---- respons sumber luar dalam format aslinya ----
    def respond(self, service: str, url: str, params: dict, now: Optional[float] = None):
        now = time.time() if now is None else now
        if self.fault_service == service and now < self.fault_until:
            raise MockUpstreamDown(service)
        if service == "kotasiaga":
            lat = float(params.get(settings.risk_lat_param, params.get("lat", CENTER[0])))
            lon = float(params.get(settings.risk_lon_param, params.get("lon", CENTER[1])))
            return self._risk(lat, lon, now) if url.rstrip("/").endswith("/risk") else self._weather(lat, lon, now)
        if service == "open-meteo":
            return self._open_meteo(params, now)
        if service == "osrm":
            return self._osrm(url)
        if service == "wikipedia":
            return self._wikipedia(url)
        raise MockUpstreamDown(service)

    def _meta(self, now: float) -> dict:
        return {"seq": self.ticks, "updated_at": _iso(now), "source": "mock", "stale": False}

    def _condition(self, rain: float, now: float) -> str:
        if now < self.storm_until:
            return "storm"
        return "clear" if rain < 0.2 else "cloudy" if rain < 1 else "rain" if rain < 15 else "heavy_rain"

    def _weather(self, lat: float, lon: float, now: float) -> dict:
        _, rain, _ = self.score(lat, lon, now)
        temperature = 30 - rain * 0.15 + ((_crc(lat, lon) % 7) - 3) / 10
        return {"data": {"observed_at": _iso(now), "temperature_c": round(temperature, 1),
                         "rain_mm_h": round(rain, 1), "condition": self._condition(rain, now)},
                "meta": self._meta(now)}

    def _risk(self, lat: float, lon: float, now: float) -> dict:
        score, rain, near = self.score(lat, lon, now)
        return {"data": {"cell_id": f"c_{int((lat - LAT_RANGE[0]) * 200)}_{int((lon - LON_RANGE[0]) * 200)}",
                         "risk_level": self.level(score), "score": round(score, 2),
                         "factors": [{"type": "rain", "value": round(rain, 1)},
                                     {"type": "disaster_signal", "count": near}]},
                "meta": self._meta(now)}

    def _open_meteo(self, params: dict, now: float) -> dict:
        lat, lon = float(params.get("latitude", CENTER[0])), float(params.get("longitude", CENTER[1]))
        if "daily" in params:
            seed = zlib.crc32(f"{params.get('start_date')}|{lat:.2f},{lon:.2f}".encode())
            rain_sum = (seed % 200) / 10
            code = 1 if rain_sum < 0.5 else 61 if rain_sum < 5 else 63 if rain_sum < 12 else 65
            return {"daily": {"weather_code": [code], "temperature_2m_max": [27 + seed % 5],
                              "temperature_2m_min": [19 + seed % 3], "precipitation_sum": [rain_sum]}}
        _, rain, _ = self.score(lat, lon, now)
        code = 95 if now < self.storm_until else 1 if rain < 0.2 else 3 if rain < 1 else 61 if rain < 5 else 63 if rain < 15 else 65
        return {"current": {"temperature_2m": round(30 - rain * 0.15, 1), "rain": round(rain, 1), "weather_code": code}}

    def _osrm(self, url: str) -> dict:
        try:
            a, b = unquote(url.rsplit("/", 1)[-1]).split(";")
            lon1, lat1 = (float(x) for x in a.split(","))
            lon2, lat2 = (float(x) for x in b.split(","))
        except ValueError:
            return {"code": "InvalidUrl"}
        meters = _haversine_km(lat1, lon1, lat2, lon2) * 1000 * 1.3
        offset = ((_crc(lat1, lon1) % 5) - 2) * 0.0005
        return {"code": "Ok", "routes": [{"distance": round(meters, 1), "duration": round(meters / (30 / 3.6), 1),
                                          "geometry": {"type": "LineString", "coordinates": [
                                              [lon1, lat1], [(lon1 + lon2) / 2 + offset, (lat1 + lat2) / 2 + offset],
                                              [lon2, lat2]]}}]}

    def _wikipedia(self, url: str) -> dict:
        title = unquote(url.rsplit("/", 1)[-1]).replace("_", " ")
        return {"title": title, "extract": f"{title} adalah destinasi uji untuk demo mock mode.",
                "content_urls": {"desktop": {"page": "https://id.wikipedia.org/wiki/" + quote(title.replace(" ", "_"))}}}


_world: Optional[MockWorld] = None


def get_world() -> MockWorld:
    if _world is None:
        raise RuntimeError("mock mode belum dijalankan")
    return _world


def is_mocked(service: str) -> bool:
    return settings.mock_mode or (service == "kotasiaga" and settings.mock_upstream_smartcity)


def seed_mock_destinations(conn) -> None:
    if conn.execute("SELECT 1 FROM destinations WHERE submitted_by=? LIMIT 1", (MOCK_OWNER,)).fetchone():
        return
    for i, (name, category, lat, lon) in enumerate(DESTINATIONS):
        status = "terbit" if i < INITIAL_PUBLISHED else "menunggu"
        cur = conn.execute(
            """INSERT INTO destinations(name,category,description,latitude,longitude,wikipedia_title,status,submitted_by)
               VALUES (?,?,?,?,?,?,?,?)""",
            (name, category, f"{name}: destinasi uji untuk demo mock mode, bukan data resmi.", lat, lon, name,
             status, MOCK_OWNER))
        if status == "terbit":
            events.publish("DestinasiTerbit", conn, destination_id=cur.lastrowid)
    conn.commit()


def start(conn) -> MockWorld:
    global _world
    seed = settings.mock_seed if settings.mock_seed is not None else random.SystemRandom().randrange(1, 2 ** 31)
    _world = MockWorld(seed)
    log.info("mock aktif MOCK_SEED=%s tick=%ss mock_mode=%s mock_upstream_smartcity=%s",
             seed, settings.mock_tick_seconds, settings.mock_mode, settings.mock_upstream_smartcity)
    if settings.mock_mode:
        seed_mock_destinations(conn)
    return _world


def _tick_once() -> None:
    conn = connect()
    try:
        get_world().tick(conn, toggle=settings.mock_mode)
    finally:
        conn.close()


async def run_forever() -> None:
    while True:
        await asyncio.sleep(settings.mock_tick_seconds)
        try:
            await asyncio.to_thread(_tick_once)
        except Exception:
            log.exception("tick mock gagal")