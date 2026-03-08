"""
Matrix service tests.

No real OSRM network calls — requests.get is mocked to return synthetic
responses that match the OSRM Table API contract.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from services.matrix_service import build_time_matrix


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_osrm_response(n: int) -> dict:
    """Return a minimal valid OSRM Table API response for n coordinates."""
    durations = [[float(abs(i - j) * 300) for j in range(n)] for i in range(n)]
    distances = [[float(abs(i - j) * 2500) for j in range(n)] for i in range(n)]
    return {"code": "Ok", "durations": durations, "distances": distances}


def _mock_requests_get(n: int):
    """Patch requests.get to return a synthetic OSRM response for n nodes."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = _make_osrm_response(n)
    mock_resp.raise_for_status.return_value = None
    return MagicMock(return_value=mock_resp)


# ---------------------------------------------------------------------------
# Shape and type invariants
# ---------------------------------------------------------------------------

class TestMatrixShape:
    def test_returns_square_time_matrix(self):
        n = 5
        with patch("services.matrix_service.requests.get", _mock_requests_get(n)):
            coords = [(50.45 + i * 0.01, 30.52 + i * 0.01) for i in range(n)]
            durations, distances = build_time_matrix(coords)
        assert len(durations) == n
        assert all(len(row) == n for row in durations)

    def test_returns_square_distance_matrix(self):
        n = 4
        with patch("services.matrix_service.requests.get", _mock_requests_get(n)):
            coords = [(50.45 + i * 0.01, 30.52) for i in range(n)]
            _, distances = build_time_matrix(coords)
        assert len(distances) == n
        assert all(len(row) == n for row in distances)

    def test_both_matrices_same_size(self):
        n = 6
        with patch("services.matrix_service.requests.get", _mock_requests_get(n)):
            coords = [(50.0 + i * 0.01, 30.0 + i * 0.01) for i in range(n)]
            durations, distances = build_time_matrix(coords)
        assert len(durations) == len(distances)
        assert len(durations[0]) == len(distances[0])

    def test_empty_coordinates_returns_empty(self):
        durations, distances = build_time_matrix([])
        assert durations == []
        assert distances == []

    def test_single_coordinate_returns_1x1(self):
        n = 1
        with patch("services.matrix_service.requests.get", _mock_requests_get(n)):
            durations, distances = build_time_matrix([(50.45, 30.52)])
        assert len(durations) == 1
        assert len(durations[0]) == 1


# ---------------------------------------------------------------------------
# Value invariants
# ---------------------------------------------------------------------------

class TestMatrixValues:
    def test_diagonal_is_zero(self):
        n = 4
        with patch("services.matrix_service.requests.get", _mock_requests_get(n)):
            coords = [(50.45 + i * 0.01, 30.52) for i in range(n)]
            durations, distances = build_time_matrix(coords)
        for i in range(n):
            assert durations[i][i] == 0.0
            assert distances[i][i] == 0.0

    def test_all_values_non_negative(self):
        n = 5
        with patch("services.matrix_service.requests.get", _mock_requests_get(n)):
            coords = [(50.0 + i * 0.01, 30.0) for i in range(n)]
            durations, distances = build_time_matrix(coords)
        for i in range(n):
            for j in range(n):
                assert durations[i][j] >= 0
                assert distances[i][j] >= 0

    def test_off_diagonal_values_positive(self):
        """Travel between distinct nodes must have positive time/distance."""
        n = 3
        with patch("services.matrix_service.requests.get", _mock_requests_get(n)):
            coords = [(50.0 + i * 0.05, 30.0 + i * 0.05) for i in range(n)]
            durations, distances = build_time_matrix(coords)
        for i in range(n):
            for j in range(n):
                if i != j:
                    assert durations[i][j] > 0
                    assert distances[i][j] > 0


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestMatrixErrors:
    def test_osrm_error_code_raises(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"code": "InvalidQuery", "message": "bad request"}
        mock_resp.raise_for_status.return_value = None
        with patch("services.matrix_service.requests.get", MagicMock(return_value=mock_resp)):
            with pytest.raises(RuntimeError, match="OSRM error"):
                build_time_matrix([(50.45, 30.52), (50.46, 30.53)])

    def test_missing_durations_raises(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"code": "Ok", "distances": [[0, 1], [1, 0]]}
        mock_resp.raise_for_status.return_value = None
        with patch("services.matrix_service.requests.get", MagicMock(return_value=mock_resp)):
            with pytest.raises(RuntimeError, match="missing durations"):
                build_time_matrix([(50.45, 30.52), (50.46, 30.53)])

    def test_missing_distances_raises(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"code": "Ok", "durations": [[0, 300], [300, 0]]}
        mock_resp.raise_for_status.return_value = None
        with patch("services.matrix_service.requests.get", MagicMock(return_value=mock_resp)):
            with pytest.raises(RuntimeError, match="missing distances"):
                build_time_matrix([(50.45, 30.52), (50.46, 30.53)])

    def test_network_error_raises(self):
        import requests as req
        with patch("services.matrix_service.requests.get", side_effect=req.RequestException("timeout")):
            with pytest.raises(req.RequestException):
                build_time_matrix([(50.45, 30.52), (50.46, 30.53)])
