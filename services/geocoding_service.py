"""Convert addresses to coordinates using Nominatim (OSM) or Google Maps Geocoding API.

Cache strategy
--------------
When the ``REDIS_URL`` env var is set and Redis is reachable, coordinates are
stored in Redis (TTL = 30 days) so they survive container restarts without any
volume mounts.

When Redis is not configured or unavailable, the service falls back to a
local JSON file (path controlled by ``cache_path`` constructor arg or the
``GEOCODE_CACHE_PATH`` env var).  This fallback keeps the test suite working
without a Redis dependency.
"""

import json
import logging
import os
import re
from pathlib import Path

import requests

logger = logging.getLogger(__name__)
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_USER_AGENT = "FlowerRouteOptimizer/1.0"
GOOGLE_GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
DEFAULT_CACHE_PATH = Path(os.getenv("GEOCODE_CACHE_PATH", "geocode_cache.json"))

_REDIS_KEY_PREFIX = "geocode:"
_REDIS_TTL = 30 * 24 * 3600  # 30 days

# Street-type prefixes to strip before using an address as a cache key.
_PREFIX_RE = re.compile(
    r"\b(вул\.?|вулиця|ул\.?|улица|str\.?|street|пр\.?|просп\.?|проспект"
    r"|бул\.?|бульвар|boulevard|blvd\.?|ave\.?|avenue"
    r"|пл\.?|площа|площадь|sq\.?|square|lane|ln\.?|road|rd\.?|шосе)\b",
    re.IGNORECASE | re.UNICODE,
)


def _normalize(address: str) -> str:
    """Return a canonical cache key for an address string.

    Rules: lowercase → strip street-type prefixes → remove punctuation
    → collapse whitespace.
    """
    s = address.lower()
    s = _PREFIX_RE.sub(" ", s)
    s = re.sub(r"[^\w\s]", " ", s)      # drop punctuation (keeps Unicode letters/digits)
    s = re.sub(r"\s+", " ", s).strip()
    return s


class GeocodingService:
    """Geocode addresses with Redis or file-based JSON caching."""

    def __init__(self, cache_path: str | Path = DEFAULT_CACHE_PATH):
        # ── try Redis ──────────────────────────────────────────────────────────
        self._redis = None
        redis_url = os.getenv("REDIS_URL")
        if redis_url:
            try:
                import redis as redis_lib  # lazy import — optional dependency
                client = redis_lib.from_url(
                    redis_url,
                    decode_responses=True,
                    socket_connect_timeout=2,
                )
                client.ping()
                self._redis = client
                logger.info("Geocoding cache: Redis at %s", redis_url)
            except Exception as exc:
                logger.warning(
                    "Redis unavailable (%s) — falling back to file cache", exc
                )

        # ── file-based fallback ────────────────────────────────────────────────
        # Populated only when Redis is not in use (also used by the test suite).
        self.cache_path = Path(cache_path)
        self._file_cache: dict[str, dict[str, float]] = (
            {} if self._redis else self._load_file_cache()
        )

    # ── internal cache helpers ─────────────────────────────────────────────────

    def _cache_get(self, key: str) -> tuple[float, float] | None:
        if self._redis:
            try:
                raw = self._redis.get(f"{_REDIS_KEY_PREFIX}{key}")
                if raw:
                    entry = json.loads(raw)
                    return (entry["lat"], entry["lng"])
            except Exception as exc:
                logger.warning("Redis read error: %s", exc)
        else:
            entry = self._file_cache.get(key)
            if entry:
                return (entry["lat"], entry["lng"])
        return None

    def _cache_set(self, key: str, lat: float, lng: float) -> None:
        payload = {"lat": lat, "lng": lng}
        if self._redis:
            try:
                self._redis.setex(
                    f"{_REDIS_KEY_PREFIX}{key}",
                    _REDIS_TTL,
                    json.dumps(payload),
                )
                return
            except Exception as exc:
                logger.warning("Redis write error: %s", exc)
        # File-based path (also fallback when Redis write fails)
        self._file_cache[key] = payload
        self._save_file_cache()

    # ── file cache I/O ─────────────────────────────────────────────────────────

    def _load_file_cache(self) -> dict[str, dict[str, float]]:
        """Load cache from JSON file, re-keying all entries with normalized keys."""
        if not self.cache_path.exists():
            return {}
        try:
            with self.cache_path.open(encoding="utf-8") as f:
                raw: dict[str, dict[str, float]] = json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
        # Migrate old keys to normalized form (first entry wins on collision)
        normalized: dict[str, dict[str, float]] = {}
        for k, val in raw.items():
            nk = _normalize(k)
            if nk not in normalized:
                normalized[nk] = val
        return normalized

    def _save_file_cache(self) -> None:
        """Persist cache to JSON file."""
        with self.cache_path.open("w", encoding="utf-8") as f:
            json.dump(self._file_cache, f, indent=2, ensure_ascii=False)

    # ── public API ─────────────────────────────────────────────────────────────

    def geocode(self, address: str) -> tuple[float, float] | None:
        """
        Convert address string to (latitude, longitude).

        Uses cache first; on cache miss, calls Google Maps Geocoding API.
        Requires GOOGLE_MAPS_API_KEY environment variable.

        Returns:
            (lat, lng) or None if address cannot be geocoded.
        """
        address = address.strip()
        if not address:
            return None

        key = _normalize(address)
        cached = self._cache_get(key)
        if cached is not None:
            logger.debug("Geocode cache hit: %s", address[:50])
            return cached

        api_key = os.environ.get("GOOGLE_MAPS_API_KEY")
        if api_key:
            return self._geocode_google(address, key, api_key)
        return self._geocode_nominatim(address, key)

    def _geocode_google(self, address: str, key: str, api_key: str) -> tuple[float, float] | None:
        logger.info("Google Geocoding API call: %s", address[:80])
        try:
            response = requests.get(
                GOOGLE_GEOCODE_URL,
                params={"address": address, "key": api_key},
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as e:
            logger.error("Google Geocoding API error for %s: %s", address[:50], e)
            raise

        if data.get("status") != "OK" or not data.get("results"):
            logger.warning(
                "Google Geocoding: no results for %s (status: %s) — falling back to Nominatim",
                address[:50],
                data.get("status"),
            )
            return self._geocode_nominatim(address, key)

        location = data["results"][0]["geometry"]["location"]
        lat, lng = float(location["lat"]), float(location["lng"])
        logger.info("Google Geocoding: %s -> (%.4f, %.4f)", address[:50], lat, lng)
        self._cache_set(key, lat, lng)
        return (lat, lng)

    def _geocode_nominatim(self, address: str, key: str) -> tuple[float, float] | None:
        logger.info("Nominatim API call: %s", address[:80])
        try:
            response = requests.get(
                NOMINATIM_URL,
                params={"q": address, "format": "json", "limit": 1},
                headers={"User-Agent": NOMINATIM_USER_AGENT},
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as e:
            logger.error("Nominatim API error for %s: %s", address[:50], e)
            raise

        if not data:
            logger.warning("Nominatim: no results for %s", address[:50])
            return None

        lat, lng = float(data[0]["lat"]), float(data[0]["lon"])
        logger.info("Nominatim: %s -> (%.4f, %.4f)", address[:50], lat, lng)
        self._cache_set(key, lat, lng)
        return (lat, lng)
