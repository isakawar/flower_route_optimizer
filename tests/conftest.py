"""Shared fixtures and helpers for the test suite."""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

# Make project root importable from every test file.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import main  # noqa: E402  (must come after sys.path tweak)
from main import app  # noqa: E402

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent / "fixtures"

# ---------------------------------------------------------------------------
# Synthetic matrices
# ---------------------------------------------------------------------------
# All API tests mock build_time_matrix with this helper so no network is needed.
# Times are in seconds; distances in meters (≈ time × 8.33 m/s = 30 km/h).


def make_matrix(n: int) -> tuple[list[list[float]], list[list[float]]]:
    """Return a synthetic (n×n, n×n) time/distance matrix pair.

    Diagonal is 0; off-diagonal values grow with node distance to produce
    realistic asymmetry without requiring an actual OSRM call.
    """
    t: list[list[float]] = []
    for i in range(n):
        row: list[float] = []
        for j in range(n):
            if i == j:
                row.append(0.0)
            else:
                # Base 600s (10 min) + spacing so nearer nodes are cheaper
                row.append(float(600 + abs(i - j) * 120 + (i + j) * 20))
        t.append(row)
    d = [[v * 8.33 for v in row] for row in t]
    return t, d


# ---------------------------------------------------------------------------
# Geocoding fixtures
# ---------------------------------------------------------------------------
# These addresses are the exact strings _optimize_sync constructs from fixture CSVs:
# f"{order.city}, {order.address} {order.house}, Ukraine"

_GEOCODE_MAP: dict[str, tuple[float, float]] = {
    main.DEPOT_ADDRESS: (50.4501, 30.5234),
    # small_orders.csv + infeasible_orders.csv
    "Київ, вул. Хрещатик 1, Ukraine":                (50.4548, 30.5238),
    "Київ, просп. Перемоги 26, Ukraine":              (50.4571, 30.5060),
    "Київ, вул. Богдана Хмельницького 55, Ukraine":   (50.4480, 30.5190),
    "Буча, вул. Вокзальна 10, Ukraine":               (50.5491, 30.2295),
    "Бровари, вул. Київська 20, Ukraine":             (50.5115, 30.7890),
    # time_windows_orders.csv (additional addresses)
    "Київ, вул. Жилянська 63, Ukraine":               (50.4420, 30.5180),
    "Ірпінь, вул. Соборна 12, Ukraine":               (50.5223, 30.2474),
}


def geocoder_side_effect(address: str) -> tuple[float, float] | None:
    return _GEOCODE_MAP.get(address)


def make_geocoder_mock() -> MagicMock:
    """Return a patched GeocodingService class whose instance resolves fixture addresses."""
    instance = MagicMock()
    instance.geocode.side_effect = geocoder_side_effect
    cls_mock = MagicMock(return_value=instance)
    return cls_mock


def make_matrix_mock() -> MagicMock:
    """Return a patched build_time_matrix that generates synthetic matrices on the fly."""
    def _impl(coordinates: list) -> tuple[list[list[float]], list[list[float]]]:
        return make_matrix(len(coordinates))

    return MagicMock(side_effect=_impl)


# ---------------------------------------------------------------------------
# pytest fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture()
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture()
def small_csv(fixtures_dir: Path) -> Path:
    return fixtures_dir / "small_orders.csv"


@pytest.fixture()
def tw_csv(fixtures_dir: Path) -> Path:
    return fixtures_dir / "time_windows_orders.csv"


@pytest.fixture()
def infeasible_csv(fixtures_dir: Path) -> Path:
    return fixtures_dir / "infeasible_orders.csv"
