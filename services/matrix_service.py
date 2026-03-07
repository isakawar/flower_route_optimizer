"""Build distance/time matrix using OSRM Table API."""

import logging

import requests

logger = logging.getLogger(__name__)
OSRM_TABLE_URL = "http://router.project-osrm.org/table/v1/driving"


def build_time_matrix(
    coordinates: list[tuple[float, float]],
    profile: str = "driving",
) -> tuple[list[list[float]], list[list[float]]]:
    """
    Build time and distance matrices between all pairs of coordinates.

    Uses OSRM Table API.
    durations[i][j] = travel time in seconds from i to j.
    distances[i][j] = travel distance in meters from i to j.

    Args:
        coordinates: List of (lat, lng) pairs. E.g. [(50.45, 30.52), ...] for Kyiv.
        profile: OSRM profile (driving, walking, cycling). Default: driving.

    Returns:
        (durations, distances). Empty ([], []) if no coordinates.
    """
    if not coordinates:
        return [], []

    # OSRM expects lon,lat;lon,lat;...
    coord_str = ";".join(f"{lon},{lat}" for lat, lon in coordinates)
    url = f"{OSRM_TABLE_URL.replace('driving', profile)}/{coord_str}"
    params = {"annotations": "duration,distance"}

    logger.info("OSRM Table API call: %d coordinates", len(coordinates))
    try:
        response = requests.get(url, params=params, timeout=20)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as e:
        logger.error("OSRM API error: %s", e)
        raise

    if data.get("code") != "Ok":
        err = data.get("message", data.get("code", "Unknown"))
        logger.error("OSRM error: %s", err)
        raise RuntimeError(f"OSRM error: {err}")

    durations = data.get("durations")
    distances = data.get("distances")
    if durations is None:
        logger.error("OSRM response missing durations")
        raise RuntimeError("OSRM response missing durations")
    if distances is None:
        logger.error("OSRM response missing distances")
        raise RuntimeError("OSRM response missing distances")

    n = len(durations)
    logger.info("OSRM: built %dx%d time and distance matrices", n, len(durations[0]) if durations else 0)

    # Log sample stats for debugging zig-zag issues
    if n > 1:
        times_flat = [durations[i][j] for i in range(n) for j in range(n) if i != j and durations[i][j] > 0]
        dists_flat = [distances[i][j] for i in range(n) for j in range(n) if i != j and distances[i][j] > 0]
        if times_flat:
            logger.info(
                "OSRM durations (s): min=%.0f, max=%.0f, avg=%.0f",
                min(times_flat), max(times_flat), sum(times_flat) / len(times_flat),
            )
        if dists_flat:
            logger.info(
                "OSRM distances (m): min=%.0f, max=%.0f, avg=%.0f",
                min(dists_flat), max(dists_flat), sum(dists_flat) / len(dists_flat),
            )

    return durations, distances
