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
    mock_upstream_smartcity = _bool("MOCK_UPSTREAM_SMARTCITY")
    mock_tick_seconds = min(60, max(2, int(os.getenv("MOCK_TICK_SECONDS", "5"))))
    mock_seed = int(os.environ["MOCK_SEED"]) if os.getenv("MOCK_SEED") else None
    smartcity_mocked = mock_mode or mock_upstream_smartcity
    # Smart City (KotaSiaga). Kosong = cuaca dari Open-Meteo. Isi setelah API Registry terbit.
    smartcity_url = os.getenv("SMARTCITY_API_URL", "").rstrip("/")
    smartcity_key = os.getenv("SMARTCITY_API_KEY", "")
    weather_url = (smartcity_url + "/weather") if smartcity_url else ("mock://kotasiaga/weather" if smartcity_mocked else "")
    # Opsional: RISK_API_URL dan RISK_API_KEY menimpa nilai turunan dari SMARTCITY_*
    risk_url = os.getenv("RISK_API_URL", "") or ((smartcity_url + "/risk") if smartcity_url else ("mock://kotasiaga/risk" if smartcity_mocked else ""))
    risk_key = os.getenv("RISK_API_KEY", "") or smartcity_key
    risk_key_header = os.getenv("RISK_API_KEY_HEADER", "X-API-Key")
    risk_lat_param = os.getenv("RISK_LAT_PARAM", "lat")
    risk_lon_param = os.getenv("RISK_LON_PARAM", "lon")
    risk_level_field = os.getenv("RISK_LEVEL_FIELD", "data.risk_level")
    user_agent = os.getenv("OUTBOUND_USER_AGENT", "TugasBesar-TST/1.0 (chitatomigoreng)")
    http_timeout = float(os.getenv("OUTBOUND_TIMEOUT", "5"))
    weather_ttl = int(os.getenv("WEATHER_TTL", "600"))
    route_ttl = int(os.getenv("ROUTE_TTL", "3600"))
    wiki_ttl = int(os.getenv("WIKI_TTL", "86400"))
    risk_ttl = int(os.getenv("RISK_TTL", "60"))


settings = Settings()
CATEGORIES = ("alam", "budaya-sejarah", "kuliner-lokal", "desa-wisata", "kerajinan")
