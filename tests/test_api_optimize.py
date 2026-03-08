"""
/api/optimize integration tests.

All external calls (geocoding, OSRM matrix, OSRM geometry) are mocked so
tests run offline and deterministically.

Invariants verified:
- Response schema is complete and typed correctly
- Every order from the CSV appears exactly once in the result
- No duplicate stops across couriers
- Stats fields are consistent with route data
- Stop coordinates are valid floats
- Infeasible requests return 422 with structured error
- Invalid CSV returns 400
"""

import io
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from tests.conftest import make_geocoder_mock, make_matrix_mock, FIXTURES_DIR

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _post_optimize(client: TestClient, csv_path: Path, **form_fields) -> dict:
    """POST /api/optimize with a CSV file and optional form overrides."""
    defaults = {"start_time": "09:00", "num_couriers": "2"}
    defaults.update({k: str(v) for k, v in form_fields.items()})
    with open(csv_path, "rb") as f:
        resp = client.post(
            "/api/optimize",
            data=defaults,
            files={"file": ("orders.csv", f, "text/csv")},
        )
    return resp


def _post_optimize_bytes(client: TestClient, csv_bytes: bytes, **form_fields) -> dict:
    defaults = {"start_time": "09:00", "num_couriers": "1"}
    defaults.update({k: str(v) for k, v in form_fields.items()})
    resp = client.post(
        "/api/optimize",
        data=defaults,
        files={"file": ("orders.csv", io.BytesIO(csv_bytes), "text/csv")},
    )
    return resp


def _mocks():
    """Return context-manager patches for geocoding, matrix, and geometry."""
    return [
        patch("main.GeocodingService", make_geocoder_mock()),
        patch("main.build_time_matrix", make_matrix_mock()),
        patch("main.fetch_route_geometry", return_value=None),
    ]


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------

class TestResponseSchema:
    def test_top_level_keys_present(self, client):
        with _mocks()[0], _mocks()[1], _mocks()[2]:
            resp = _post_optimize(client, FIXTURES_DIR / "small_orders.csv")
        assert resp.status_code == 200
        body = resp.json()
        assert "routes" in body
        assert "stats" in body
        assert "depot" in body

    def test_stats_fields(self, client):
        with _mocks()[0], _mocks()[1], _mocks()[2]:
            resp = _post_optimize(client, FIXTURES_DIR / "small_orders.csv")
        stats = resp.json()["stats"]
        assert "totalDeliveries" in stats
        assert "totalDriveMin" in stats
        assert "totalDistanceKm" in stats
        assert "numCouriers" in stats

    def test_route_fields(self, client):
        with _mocks()[0], _mocks()[1], _mocks()[2]:
            resp = _post_optimize(client, FIXTURES_DIR / "small_orders.csv")
        for route in resp.json()["routes"]:
            assert "courierId" in route
            assert "stops" in route
            assert "totalDriveMin" in route
            assert "totalDistanceKm" in route

    def test_stop_fields(self, client):
        with _mocks()[0], _mocks()[1], _mocks()[2]:
            resp = _post_optimize(client, FIXTURES_DIR / "small_orders.csv")
        for route in resp.json()["routes"]:
            for stop in route["stops"]:
                assert "address" in stop
                assert "eta" in stop
                assert "driveMin" in stop
                assert "waitMin" in stop
                assert "lat" in stop
                assert "lng" in stop

    def test_depot_coordinates_present(self, client):
        with _mocks()[0], _mocks()[1], _mocks()[2]:
            resp = _post_optimize(client, FIXTURES_DIR / "small_orders.csv")
        depot = resp.json()["depot"]
        assert isinstance(depot["lat"], float)
        assert isinstance(depot["lng"], float)

    def test_dropped_orders_field_present(self, client):
        with _mocks()[0], _mocks()[1], _mocks()[2]:
            resp = _post_optimize(client, FIXTURES_DIR / "small_orders.csv")
        assert "droppedOrders" in resp.json()


# ---------------------------------------------------------------------------
# Delivery invariant tests
# ---------------------------------------------------------------------------

class TestDeliveryInvariants:
    def _get_all_addresses(self, body: dict) -> list[str]:
        return [s["address"] for r in body["routes"] for s in r["stops"]]

    def test_all_stops_served(self, client):
        """Every order in the CSV appears exactly once across all routes."""
        with _mocks()[0], _mocks()[1], _mocks()[2]:
            resp = _post_optimize(client, FIXTURES_DIR / "small_orders.csv")
        body = resp.json()
        addresses = self._get_all_addresses(body)
        assert len(addresses) == 5  # small_orders.csv has 5 orders

    def test_no_duplicate_addresses(self, client):
        with _mocks()[0], _mocks()[1], _mocks()[2]:
            resp = _post_optimize(client, FIXTURES_DIR / "small_orders.csv")
        addresses = self._get_all_addresses(resp.json())
        assert len(addresses) == len(set(addresses))

    def test_stats_total_deliveries_matches_routes(self, client):
        with _mocks()[0], _mocks()[1], _mocks()[2]:
            resp = _post_optimize(client, FIXTURES_DIR / "small_orders.csv")
        body = resp.json()
        route_total = sum(len(r["stops"]) for r in body["routes"])
        assert body["stats"]["totalDeliveries"] == route_total

    def test_stats_num_couriers_matches_routes(self, client):
        with _mocks()[0], _mocks()[1], _mocks()[2]:
            resp = _post_optimize(client, FIXTURES_DIR / "small_orders.csv")
        body = resp.json()
        assert body["stats"]["numCouriers"] == len(body["routes"])

    def test_stop_coordinates_are_valid_floats(self, client):
        with _mocks()[0], _mocks()[1], _mocks()[2]:
            resp = _post_optimize(client, FIXTURES_DIR / "small_orders.csv")
        for route in resp.json()["routes"]:
            for stop in route["stops"]:
                assert isinstance(stop["lat"], float)
                assert isinstance(stop["lng"], float)
                assert -90 <= stop["lat"] <= 90
                assert -180 <= stop["lng"] <= 180

    def test_drive_min_non_negative(self, client):
        with _mocks()[0], _mocks()[1], _mocks()[2]:
            resp = _post_optimize(client, FIXTURES_DIR / "small_orders.csv")
        for route in resp.json()["routes"]:
            for stop in route["stops"]:
                assert stop["driveMin"] >= 0
                assert stop["waitMin"] >= 0

    def test_eta_format_is_hhmm(self, client):
        import re
        pattern = re.compile(r"^\d{2}:\d{2}$")
        with _mocks()[0], _mocks()[1], _mocks()[2]:
            resp = _post_optimize(client, FIXTURES_DIR / "small_orders.csv")
        for route in resp.json()["routes"]:
            for stop in route["stops"]:
                assert pattern.match(stop["eta"]), f"Invalid ETA format: {stop['eta']}"

    def test_courier_id_is_positive_integer(self, client):
        with _mocks()[0], _mocks()[1], _mocks()[2]:
            resp = _post_optimize(client, FIXTURES_DIR / "small_orders.csv")
        for route in resp.json()["routes"]:
            assert isinstance(route["courierId"], int)
            assert route["courierId"] >= 1


# ---------------------------------------------------------------------------
# Error handling tests
# ---------------------------------------------------------------------------

class TestErrorHandling:
    def test_invalid_csv_returns_400(self, client):
        bad_csv = b"this,is,not,a,valid,order\nwrong,data,here\n"
        resp = _post_optimize_bytes(client, bad_csv)
        assert resp.status_code == 400

    def test_empty_csv_returns_400(self, client):
        empty = b"id,city,address,house\n"  # header only, no rows
        with _mocks()[0], _mocks()[1], _mocks()[2]:
            resp = _post_optimize_bytes(client, empty)
        assert resp.status_code == 400

    def test_infeasible_capacity_returns_422(self, client):
        """1 courier, capacity=1, 5 orders → needs 5 couriers → 422."""
        with _mocks()[0], _mocks()[1], _mocks()[2]:
            resp = _post_optimize(
                client,
                FIXTURES_DIR / "small_orders.csv",
                num_couriers=1,
                capacity=1,
            )
        assert resp.status_code == 422
        body = resp.json()
        assert body["error"] == "INFEASIBLE"
        assert "minimum_couriers_required" in body
        assert body["minimum_couriers_required"] > 1

    def test_infeasible_response_has_reason(self, client):
        with _mocks()[0], _mocks()[1], _mocks()[2]:
            resp = _post_optimize(
                client,
                FIXTURES_DIR / "small_orders.csv",
                num_couriers=1,
                capacity=1,
            )
        body = resp.json()
        assert "reason" in body
        assert "message" in body

    def test_no_file_returns_422(self, client):
        resp = client.post("/api/optimize", data={"start_time": "09:00", "num_couriers": "1"})
        assert resp.status_code == 422  # FastAPI validation error


# ---------------------------------------------------------------------------
# Regression: capacity=None must not crash (form parsing fix)
# ---------------------------------------------------------------------------

class TestCapacityFormParsing:
    def test_no_capacity_field_returns_200(self, client):
        """Omitting capacity (sends None) must not crash the endpoint."""
        with _mocks()[0], _mocks()[1], _mocks()[2]:
            with open(FIXTURES_DIR / "small_orders.csv", "rb") as f:
                resp = client.post(
                    "/api/optimize",
                    data={"start_time": "09:00", "num_couriers": "2"},
                    files={"file": ("orders.csv", f, "text/csv")},
                )
        assert resp.status_code == 200

    def test_explicit_capacity_accepted(self, client):
        with _mocks()[0], _mocks()[1], _mocks()[2]:
            resp = _post_optimize(
                client, FIXTURES_DIR / "small_orders.csv",
                num_couriers=3, capacity=3,
            )
        assert resp.status_code == 200
