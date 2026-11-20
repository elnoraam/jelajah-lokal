"""Reaksi atas domain event antar-bounded context."""
from . import events
from .config import settings


def refresh_destination_stats(conn, destination_id: int) -> None:
    r = conn.execute(
        "SELECT COUNT(*) c, AVG(rating) a FROM reviews WHERE destination_id=? AND hidden=0",
        (destination_id,)).fetchone()
    stories = conn.execute(
        """SELECT COUNT(*) c FROM story_destinations sd JOIN stories s ON s.id = sd.story_id
           WHERE sd.destination_id=? AND s.status='terbit'""", (destination_id,)).fetchone()["c"]
    count = r["c"]
    avg = round(r["a"], 2) if r["a"] is not None else None
    hidden_gem = 1 if count < settings.hidden_max_reviews else 0
    conn.execute(
        """UPDATE destinations SET review_count=?, rating_avg=?, story_count=?, hidden_gem=?,
           updated_at=datetime('now') WHERE id=?""",
        (count, avg, stories, hidden_gem, destination_id))


def on_destinasi_terbit(conn, payload):
    refresh_destination_stats(conn, payload["destination_id"])


def on_ulasan_berubah(conn, payload):
    refresh_destination_stats(conn, payload["destination_id"])


def on_cerita_terbit(conn, payload):
    for dest_id in payload["destination_ids"]:
        refresh_destination_stats(conn, dest_id)


def register() -> None:
    events.subscribe("DestinasiTerbit", on_destinasi_terbit)
    events.subscribe("DestinasiDiperbarui", on_destinasi_terbit)
    events.subscribe("UlasanDitambahkan", on_ulasan_berubah)
    events.subscribe("UlasanDimoderasi", on_ulasan_berubah)
    events.subscribe("CeritaTerbit", on_cerita_terbit)
