"""
Geocoding service tests.

Verifies the caching layer and API integration without making real HTTP calls.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from services.geocoding_service import GeocodingService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_google_response(lat: float, lng: float) -> dict:
    return {
        "status": "OK",
        "results": [{"geometry": {"location": {"lat": lat, "lng": lng}}}],
    }


def _make_nominatim_response(lat: float, lng: float) -> list:
    return [{"lat": str(lat), "lon": str(lng)}]


def _google_mock(lat: float = 50.45, lng: float = 30.52):
    resp = MagicMock()
    resp.json.return_value = _make_google_response(lat, lng)
    resp.raise_for_status.return_value = None
    return MagicMock(return_value=resp)


def _nominatim_mock(lat: float = 50.45, lng: float = 30.52):
    resp = MagicMock()
    resp.json.return_value = _make_nominatim_response(lat, lng)
    resp.raise_for_status.return_value = None
    return MagicMock(return_value=resp)


@pytest.fixture()
def tmp_cache(tmp_path: Path) -> Path:
    return tmp_path / "geocode_cache.json"


@pytest.fixture()
def service(tmp_cache: Path) -> GeocodingService:
    """Fresh GeocodingService backed by a temp cache file."""
    return GeocodingService(cache_path=tmp_cache)


# ---------------------------------------------------------------------------
# Cache hit / miss
# ---------------------------------------------------------------------------

class TestCaching:
    def test_cache_hit_skips_http(self, service: GeocodingService):
        """Second call for same address must not make a new HTTP request."""
        with patch("services.geocoding_service.requests.get", _google_mock()) as mock_get:
            with patch.dict("os.environ", {"GOOGLE_MAPS_API_KEY": "test-key"}):
                service.geocode("Kyiv, Khreshchatyk 1, Ukraine")
                service.geocode("Kyiv, Khreshchatyk 1, Ukraine")
        assert mock_get.call_count == 1

    def test_cache_miss_triggers_http(self, service: GeocodingService):
        with patch("services.geocoding_service.requests.get", _google_mock()) as mock_get:
            with patch.dict("os.environ", {"GOOGLE_MAPS_API_KEY": "test-key"}):
                service.geocode("Kyiv, Khreshchatyk 1, Ukraine")
        assert mock_get.call_count == 1

    def test_cached_result_matches_original(self, service: GeocodingService):
        with patch("services.geocoding_service.requests.get", _google_mock(50.45, 30.52)):
            with patch.dict("os.environ", {"GOOGLE_MAPS_API_KEY": "test-key"}):
                first = service.geocode("Kyiv, Khreshchatyk 1, Ukraine")
                second = service.geocode("Kyiv, Khreshchatyk 1, Ukraine")
        assert first == second
        assert first == pytest.approx((50.45, 30.52))

    def test_cache_persists_to_disk(self, tmp_cache: Path):
        """Geocoded result must be written to the JSON cache file."""
        svc = GeocodingService(cache_path=tmp_cache)
        with patch("services.geocoding_service.requests.get", _google_mock(50.45, 30.52)):
            with patch.dict("os.environ", {"GOOGLE_MAPS_API_KEY": "test-key"}):
                svc.geocode("Kyiv, Khreshchatyk 1, Ukraine")
        assert tmp_cache.exists()
        data = json.loads(tmp_cache.read_text(encoding="utf-8"))
        assert len(data) == 1
        entry = next(iter(data.values()))
        assert pytest.approx(entry["lat"]) == 50.45
        assert pytest.approx(entry["lng"]) == 30.52

    def test_cache_survives_reload(self, tmp_cache: Path):
        """A new service instance should read from the existing cache file."""
        # Populate cache
        svc1 = GeocodingService(cache_path=tmp_cache)
        with patch("services.geocoding_service.requests.get", _google_mock(50.45, 30.52)):
            with patch.dict("os.environ", {"GOOGLE_MAPS_API_KEY": "test-key"}):
                svc1.geocode("Kyiv, Khreshchatyk 1, Ukraine")

        # New instance — must hit cache, not network
        svc2 = GeocodingService(cache_path=tmp_cache)
        with patch("services.geocoding_service.requests.get") as mock_get:
            result = svc2.geocode("Kyiv, Khreshchatyk 1, Ukraine")
        mock_get.assert_not_called()
        assert result == pytest.approx((50.45, 30.52))


# ---------------------------------------------------------------------------
# Return type
# ---------------------------------------------------------------------------

class TestReturnType:
    def test_returns_lat_lng_tuple(self, service: GeocodingService):
        with patch("services.geocoding_service.requests.get", _google_mock(50.45, 30.52)):
            with patch.dict("os.environ", {"GOOGLE_MAPS_API_KEY": "test-key"}):
                result = service.geocode("Kyiv, Khreshchatyk 1, Ukraine")
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], float)
        assert isinstance(result[1], float)

    def test_returns_none_for_empty_address(self, service: GeocodingService):
        result = service.geocode("")
        assert result is None

    def test_returns_none_on_nominatim_empty_result(self, service: GeocodingService):
        resp = MagicMock()
        resp.json.return_value = []  # Nominatim found nothing
        resp.raise_for_status.return_value = None
        with patch("services.geocoding_service.requests.get", MagicMock(return_value=resp)):
            # No API key → goes to Nominatim directly
            with patch.dict("os.environ", {}, clear=True):
                result = service.geocode("completely_invalid_address_xyz_12345")
        assert result is None


# ---------------------------------------------------------------------------
# Google → Nominatim fallback
# ---------------------------------------------------------------------------

class TestGoogleToNominatimFallback:
    def test_non_ok_google_falls_back_to_nominatim(self, service: GeocodingService):
        """Google returning ZERO_RESULTS must trigger Nominatim fallback."""
        google_resp = MagicMock()
        google_resp.json.return_value = {"status": "ZERO_RESULTS", "results": []}
        google_resp.raise_for_status.return_value = None

        nominatim_resp = MagicMock()
        nominatim_resp.json.return_value = _make_nominatim_response(50.46, 30.53)
        nominatim_resp.raise_for_status.return_value = None

        responses = [google_resp, nominatim_resp]
        with patch("services.geocoding_service.requests.get", side_effect=responses):
            with patch.dict("os.environ", {"GOOGLE_MAPS_API_KEY": "test-key"}):
                result = service.geocode("Kyiv, Some Street 99, Ukraine")

        assert result == pytest.approx((50.46, 30.53))


# ---------------------------------------------------------------------------
# Address normalisation
# ---------------------------------------------------------------------------

class TestNormalisation:
    def test_different_prefix_same_cache_entry(self, tmp_cache: Path):
        """'вул. Хрещатик 1' and 'вулиця Хрещатик 1' should share a cache key."""
        svc = GeocodingService(cache_path=tmp_cache)
        with patch("services.geocoding_service.requests.get", _google_mock()) as mock_get:
            with patch.dict("os.environ", {"GOOGLE_MAPS_API_KEY": "test-key"}):
                svc.geocode("вул. Хрещатик 1, Київ, Ukraine")
                svc.geocode("вулиця Хрещатик 1, Київ, Ukraine")
        # Second call should have been a cache hit
        assert mock_get.call_count == 1

    def test_cache_key_changes_when_city_country_bias_is_set(self, tmp_cache: Path):
        """Biased queries must not reuse a stale generic cache entry."""
        svc = GeocodingService(cache_path=tmp_cache)
        with patch("services.geocoding_service.requests.get", _google_mock()) as mock_get:
            with patch.dict("os.environ", {"GOOGLE_MAPS_API_KEY": "test-key"}):
                svc.geocode("Nahorna 18")
                svc.geocode("Nahorna 18", city="Kyiv", country="UA")
        assert mock_get.call_count == 2


class TestQueryBias:
    def test_google_request_includes_components_for_city_country(self, service: GeocodingService):
        with patch("services.geocoding_service.requests.get", _google_mock()) as mock_get:
            with patch.dict("os.environ", {"GOOGLE_MAPS_API_KEY": "test-key"}):
                service.geocode("Nahorna 18", city="Kyiv", country="UA")

        _, kwargs = mock_get.call_args
        params = kwargs["params"]
        assert params["address"] == "Nahorna 18"
        assert params["region"] == "ua"
        assert "locality:Kyiv" in params["components"]
        assert "country:ua" in params["components"]

    def test_nominatim_request_includes_country_code_and_extended_query(self, service: GeocodingService):
        with patch("services.geocoding_service.requests.get", _nominatim_mock()) as mock_get:
            with patch.dict("os.environ", {}, clear=True):
                service.geocode("Nahorna 18", city="Kyiv", country="UA")

        _, kwargs = mock_get.call_args
        params = kwargs["params"]
        assert params["countrycodes"] == "ua"
        assert params["q"] == "Nahorna 18, Kyiv, UA"
