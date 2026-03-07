"""Convert addresses to coordinates using OpenStreetMap Nominatim API."""

import json
import logging
from pathlib import Path

import requests

logger = logging.getLogger(__name__)
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "FlowerRouteOptimizer/1.0"
DEFAULT_CACHE_PATH = Path("geocode_cache.json")


class GeocodingService:
    """Geocode addresses with JSON file caching."""

    def __init__(self, cache_path: str | Path = DEFAULT_CACHE_PATH):
        self.cache_path = Path(cache_path)
        self._cache: dict[str, dict[str, float]] = self._load_cache()

    def _load_cache(self) -> dict[str, dict[str, float]]:
        """Load cache from JSON file."""
        if not self.cache_path.exists():
            return {}
        try:
            with self.cache_path.open(encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}

    def _save_cache(self) -> None:
        """Persist cache to JSON file."""
        with self.cache_path.open("w", encoding="utf-8") as f:
            json.dump(self._cache, f, indent=2, ensure_ascii=False)

    def geocode(self, address: str) -> tuple[float, float] | None:
        """
        Convert address string to (latitude, longitude).

        Uses cache first; on cache miss, calls Nominatim API and stores result.

        Returns:
            (lat, lng) or None if address cannot be geocoded.
        """
        address = address.strip()
        if not address:
            return None

        if address in self._cache:
            logger.debug("Geocode cache hit: %s", address[:50])
            c = self._cache[address]
            return (c["lat"], c["lng"])

        logger.info("Nominatim API call: %s", address[:80])
        try:
            response = requests.get(
                NOMINATIM_URL,
                params={"q": address, "format": "json", "limit": 1},
                headers={"User-Agent": USER_AGENT},
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

        lat = float(data[0]["lat"])
        lng = float(data[0]["lon"])
        logger.info("Nominatim: %s -> (%.4f, %.4f)", address[:50], lat, lng)
        self._cache[address] = {"lat": lat, "lng": lng}
        self._save_cache()
        return (lat, lng)
