import os


def _bool(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).lower() == "true"


class Settings:
    db_path = os.getenv("CORE_DB_PATH", "/data/core.db")
    jwt_secret = os.getenv("JWT_SECRET", "ganti-di-env-minimal-32-karakter!!")
    auth_url = os.getenv("AUTH_INTERNAL_URL", "http://auth:8000")
    internal_token = os.getenv("INTERNAL_TOKEN", "ganti-token-internal")
    hidden_max_reviews = int(os.getenv("HIDDEN_MAX_REVIEWS", "5"))
    seed_demo = _bool("SEED_DEMO")
    mock_mode = _bool("MOCK_MODE")
    user_agent = os.getenv("OUTBOUND_USER_AGENT", "TugasBesar-TST/1.0 (chitatomigoreng)")
    http_timeout = float(os.getenv("OUTBOUND_TIMEOUT", "5"))
    weather_ttl = int(os.getenv("WEATHER_TTL", "600"))
    route_ttl = int(os.getenv("ROUTE_TTL", "3600"))
    wiki_ttl = int(os.getenv("WIKI_TTL", "86400"))
    risk_ttl = int(os.getenv("RISK_TTL", "60"))
    # Sumber status risiko wilayah (opsional). Kosong = fitur risiko menampilkan pesan.
    risk_url = os.getenv("RISK_API_URL", "")
    risk_key = os.getenv("RISK_API_KEY", "")
    risk_key_header = os.getenv("RISK_API_KEY_HEADER", "X-API-Key")
    risk_lat_param = os.getenv("RISK_LAT_PARAM", "lat")
    risk_lon_param = os.getenv("RISK_LON_PARAM", "lon")
    risk_level_field = os.getenv("RISK_LEVEL_FIELD", "data.risk_level")


settings = Settings()
CATEGORIES = ("alam", "budaya-sejarah", "kuliner-lokal", "desa-wisata", "kerajinan")
