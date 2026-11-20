"""Adapter Wikipedia -> LatarSejarah."""
from urllib.parse import quote

from ..config import settings
from .http import cached_get_json


def get_background(title: str) -> dict:
    url = f"https://id.wikipedia.org/api/rest_v1/page/summary/{quote(title.replace(' ', '_'), safe='')}"
    data, cached, _ = cached_get_json(f"wiki:{title}", url, settings.wiki_ttl, service="wikipedia")
    return {"title": data.get("title", title), "summary": data.get("extract"),
            "url": (data.get("content_urls", {}).get("desktop", {}) or {}).get("page"),
            "source": "wikipedia", "from_cache": cached}
