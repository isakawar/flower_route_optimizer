"""
/api/recalculate integration tests.

Core invariant: the endpoint must preserve the exact stop order provided
by the caller and only recompute ETA / driveMin / waitMin.

It must NOT re-run the solver or change which stops belong to which courier.
"""

import re
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from tests.conftest import make_matrix_mock

# ---------------------------------------------------------------------------
# Sample payloads
# ---------------------------------------------------------------------------

DEPOT = {"lat": 50.4501, "lng": 30.5234}

ROUTE_1_STOPS = [
    {"lat": 50.4600, "lng": 30.5100, "address": "Kyiv, Khreshchatyk 1", "timeStart": None, "timeEnd": None},
    {"lat": 50.5000, "lng": 30.4900, "address": "Kyiv, Obolon Avenue 15", "timeStart": None, "timeEnd": None},
    {"lat": 50.4200, "lng": 30.5100, "address": "Kyiv, Velyka Vasylkivska 50", "timeStart": None, "timeEnd": None},
]

ROUTE_2_STOPS = [
    {"lat": 50.5200, "lng": 30.4700, "address": "Kyiv, Heroiv Dnipra 33", "timeStart": None, "timeEnd": None},
    {"lat": 50.4300, "lng": 30.4800, "address": "Kyiv, Borshchahivska 5", "timeStart": None, "timeEnd": None},
]

SINGLE_ROUTE_BODY = {
    "routes": [{"courierId": 1, "stops": ROUTE_1_STOPS}],
    "depot": DEPOT,
    "startTime": "09:00",
}

MULTI_ROUTE_BODY = {
    "routes": [
        {"courierId": 1, "stops": ROUTE_1_STOPS},
        {"courierId": 2, "stops": ROUTE_2_STOPS},
    ],
    "depot": DEPOT,
    "startTime": "09:00",
}


def _post(client: TestClient, body: dict):
    with patch("main.build_time_matrix", make_matrix_mock()):
        with patch("main.fetch_route_geometry", return_value=None):
            return client.post("/api/recalculate", json=body)


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------

class TestRecalculateSchema:
    def test_returns_200(self, client):
        resp = _post(client, SINGLE_ROUTE_BODY)
        assert resp.status_code == 200

    def test_top_level_keys(self, client):
        body = _post(client, SINGLE_ROUTE_BODY).json()
        assert "routes" in body
        assert "stats" in body
        assert "depot" in body

    def test_route_fields(self, client):
        body = _post(client, SINGLE_ROUTE_BODY).json()
        for route in body["routes"]:
            assert "courierId" in route
            assert "stops" in route
            assert "totalDriveMin" in route
            assert "totalDistanceKm" in route

    def test_stop_fields(self, client):
        body = _post(client, SINGLE_ROUTE_BODY).json()
        for route in body["routes"]:
            for stop in route["stops"]:
                assert "address" in stop
                assert "eta" in stop
                assert "driveMin" in stop
                assert "waitMin" in stop
                assert "lat" in stop
                assert "lng" in stop

    def test_eta_format_is_hhmm(self, client):
        body = _post(client, SINGLE_ROUTE_BODY).json()
        pattern = re.compile(r"^\d{2}:\d{2}$")
        for route in body["routes"]:
            for stop in route["stops"]:
                assert pattern.match(stop["eta"]), f"Bad ETA: {stop['eta']}"


# ---------------------------------------------------------------------------
# Stop-order invariant
# ---------------------------------------------------------------------------

class TestStopOrderPreserved:
    def test_single_courier_order_preserved(self, client):
        """Addresses must appear in exactly the same order as in the request."""
        resp = _post(client, SINGLE_ROUTE_BODY)
        result_addresses = [s["address"] for s in resp.json()["routes"][0]["stops"]]
        expected = [s["address"] for s in ROUTE_1_STOPS]
        assert result_addresses == expected

    def test_multi_courier_order_preserved(self, client):
        resp = _post(client, MULTI_ROUTE_BODY)
        routes = {r["courierId"]: r["stops"] for r in resp.json()["routes"]}

        assert [s["address"] for s in routes[1]] == [s["address"] for s in ROUTE_1_STOPS]
        assert [s["address"] for s in routes[2]] == [s["address"] for s in ROUTE_2_STOPS]

    def test_courier_assignment_preserved(self, client):
        """Each courier must receive exactly its own stops, not shuffled."""
        resp = _post(client, MULTI_ROUTE_BODY)
        courier_ids = {r["courierId"] for r in resp.json()["routes"]}
        assert courier_ids == {1, 2}

    def test_stop_count_per_courier_preserved(self, client):
        resp = _post(client, MULTI_ROUTE_BODY)
        routes = {r["courierId"]: r["stops"] for r in resp.json()["routes"]}
        assert len(routes[1]) == len(ROUTE_1_STOPS)
        assert len(routes[2]) == len(ROUTE_2_STOPS)

    def test_lat_lng_preserved(self, client):
        """Coordinates must match the input (not geocoded again)."""
        resp = _post(client, SINGLE_ROUTE_BODY)
        for out_stop, in_stop in zip(resp.json()["routes"][0]["stops"], ROUTE_1_STOPS):
            assert out_stop["lat"] == pytest.approx(in_stop["lat"])
            assert out_stop["lng"] == pytest.approx(in_stop["lng"])


# ---------------------------------------------------------------------------
# Time computation correctness
# ---------------------------------------------------------------------------

class TestTimingRecomputed:
    def test_etas_are_valid_after_start(self, client):
        """All ETAs must be >= startTime (09:00 = 540 min)."""
        resp = _post(client, SINGLE_ROUTE_BODY)
        for route in resp.json()["routes"]:
            for stop in route["stops"]:
                h, m = map(int, stop["eta"].split(":"))
                eta_minutes = h * 60 + m
                assert eta_minutes >= 540

    def test_etas_non_decreasing_within_courier(self, client):
        """Later stops in a route must have ETAs >= earlier stops."""
        resp = _post(client, SINGLE_ROUTE_BODY)
        for route in resp.json()["routes"]:
            etas = []
            for stop in route["stops"]:
                h, m = map(int, stop["eta"].split(":"))
                etas.append(h * 60 + m)
            for i in range(1, len(etas)):
                assert etas[i] >= etas[i - 1]

    def test_drive_min_non_negative(self, client):
        resp = _post(client, SINGLE_ROUTE_BODY)
        for route in resp.json()["routes"]:
            for stop in route["stops"]:
                assert stop["driveMin"] >= 0
                assert stop["waitMin"] >= 0

    def test_time_window_wait_applied(self, client):
        """Stop with timeStart after natural arrival must show positive waitMin."""
        # Force early start; window opens at 14:00 (840 min)
        # Courier starts at 09:00 and travels 10 min → arrives ~09:10 → waits ~5h
        body = {
            "routes": [{
                "courierId": 1,
                "stops": [{
                    "lat": 50.46, "lng": 30.51,
                    "address": "Test Stop",
                    "timeStart": "14:00",
                    "timeEnd": "16:00",
                }],
            }],
            "depot": DEPOT,
            "startTime": "09:00",
        }
        resp = _post(client, body)
        stop = resp.json()["routes"][0]["stops"][0]
        assert stop["waitMin"] > 0
        # ETA must be >= 14:00 (840 min)
        h, m = map(int, stop["eta"].split(":"))
        assert h * 60 + m >= 840


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestRecalculateErrors:
    def test_empty_routes_returns_400(self, client):
        resp = _post(client, {"routes": [], "depot": DEPOT, "startTime": "09:00"})
        assert resp.status_code == 400

    def test_all_empty_stops_returns_400(self, client):
        body = {
            "routes": [{"courierId": 1, "stops": []}],
            "depot": DEPOT,
            "startTime": "09:00",
        }
        resp = _post(client, body)
        assert resp.status_code == 400

    def test_missing_depot_returns_422(self, client):
        body = {"routes": [{"courierId": 1, "stops": ROUTE_1_STOPS}], "startTime": "09:00"}
        with patch("main.build_time_matrix", make_matrix_mock()):
            resp = client.post("/api/recalculate", json=body)
        assert resp.status_code == 422
