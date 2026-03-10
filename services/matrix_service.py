"""Build distance/time matrix using OSRM Table API with Haversine fallback."""

import logging
import math
import os
import time

import requests

logger = logging.getLogger(__name__)

# Override via OSRM_URL env var to point at a self-hosted instance.
# E.g. OSRM_URL=http://osrm:5000/table/v1/driving
OSRM_TABLE_URL = os.getenv(
    "OSRM_URL",
    "http://router.project-osrm.org/table/v1/driving",
)

_TIMEOUT = 30        # seconds per attempt
_RETRIES = 3         # total attempts
_RETRY_DELAY = 2.0   # seconds between retries (doubles each time)

# Average city speed used for Haversine fallback duration estimate (km/h).
_FALLBACK_SPEED_KMH = 40


# ── Haversine fallback ────────────────────────────────────────────────────────

def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> tuple[float, float]:
    """Return (duration_seconds, distance_meters) between two points."""
    R = 6_371_000  # Earth radius in metres
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    dist = 2 * R * math.asin(math.sqrt(a))
    duration = dist / (_FALLBACK_SPEED_KMH * 1000 / 3600)
    return duration, dist


def _haversine_matrix(
    coordinates: list[tuple[float, float]],
) -> tuple[list[list[float]], list[list[float]]]:
    n = len(coordinates)
    durations = [[0.0] * n for _ in range(n)]
    distances = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            lat1, lon1 = coordinates[i]
            lat2, lon2 = coordinates[j]
            dur, dist = _haversine(lat1, lon1, lat2, lon2)
            durations[i][j] = dur
            distances[i][j] = dist
    return durations, distances


# ── OSRM with retries ────────────────────────────────────────────────────────

def _osrm_request(
    url: str,
    params: dict,
) -> dict:
    delay = _RETRY_DELAY
    last_exc: Exception | None = None
    for attempt in range(1, _RETRIES + 1):
        try:
            resp = requests.get(url, params=params, timeout=_TIMEOUT)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            last_exc = exc
            logger.warning("OSRM attempt %d/%d failed: %s", attempt, _RETRIES, exc)
            if attempt < _RETRIES:
                time.sleep(delay)
                delay *= 2
    raise last_exc  # type: ignore[misc]


# ── Public API ────────────────────────────────────────────────────────────────

def build_time_matrix(
    coordinates: list[tuple[float, float]],
    profile: str = "driving",
) -> tuple[list[list[float]], list[list[float]]]:
    """
    Build time and distance matrices between all pairs of coordinates.

    Tries OSRM Table API first (up to _RETRIES attempts).
    Falls back to Haversine straight-line estimates if OSRM is unavailable.

    Args:
        coordinates: List of (lat, lng) pairs.
        profile: OSRM profile (driving, walking, cycling).

    Returns:
        (durations_seconds, distances_meters)
    """
    if not coordinates:
        return [], []

    coord_str = ";".join(f"{lon},{lat}" for lat, lon in coordinates)
    base_url = OSRM_TABLE_URL.replace("driving", profile)
    url = f"{base_url}/{coord_str}"
    params = {"annotations": "duration,distance"}

    logger.info("OSRM Table API call: %d coordinates → %s", len(coordinates), base_url)

    try:
        data = _osrm_request(url, params)
    except requests.RequestException as exc:
        logger.error(
            "OSRM unreachable after %d retries (%s). Falling back to Haversine.", _RETRIES, exc
        )
        durations, distances = _haversine_matrix(coordinates)
        logger.warning(
            "Using Haversine fallback (%d km/h). Results are approximate.", _FALLBACK_SPEED_KMH
        )
        return durations, distances

    if data.get("code") != "Ok":
        err = data.get("message", data.get("code", "Unknown"))
        logger.error("OSRM returned error: %s. Falling back to Haversine.", err)
        return _haversine_matrix(coordinates)

    durations = data.get("durations")
    distances = data.get("distances")

    if durations is None or distances is None:
        logger.error("OSRM response missing durations/distances. Falling back to Haversine.")
        return _haversine_matrix(coordinates)

    n = len(durations)
    logger.info("OSRM: built %dx%d matrices", n, len(durations[0]) if durations else 0)

    if n > 1:
        times_flat = [durations[i][j] for i in range(n) for j in range(n) if i != j and durations[i][j] > 0]
        dists_flat = [distances[i][j] for i in range(n) for j in range(n) if i != j and distances[i][j] > 0]
        if times_flat:
            logger.info(
                "OSRM durations (s): min=%.0f max=%.0f avg=%.0f",
                min(times_flat), max(times_flat), sum(times_flat) / len(times_flat),
            )
        if dists_flat:
            logger.info(
                "OSRM distances (m): min=%.0f max=%.0f avg=%.0f",
                min(dists_flat), max(dists_flat), sum(dists_flat) / len(dists_flat),
            )

    return durations, distances
