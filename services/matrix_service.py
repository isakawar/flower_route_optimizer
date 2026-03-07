"""Build distance/time matrix using OSRM Table API."""

import logging

import requests

logger = logging.getLogger(__name__)
OSRM_TABLE_URL = "http://router.project-osrm.org/table/v1/driving"


def build_time_matrix(
    coordinates: list[tuple[float, float]],
    profile: str = "driving",
) -> list[list[float]]:
    """
    Build a matrix of travel times between all pairs of coordinates.

    Uses OSRM Table API. Values are in seconds.
    durations[i][j] = travel time from coordinate i to coordinate j.

    Args:
        coordinates: List of (lat, lng) pairs. E.g. [(50.45, 30.52), ...] for Kyiv.
        profile: OSRM profile (driving, walking, cycling). Default: driving.

    Returns:
        Square matrix of travel times in seconds.
        Returns empty list if request fails.
    """
    if not coordinates:
        return []

    # OSRM expects lon,lat;lon,lat;...
    coord_str = ";".join(f"{lon},{lat}" for lat, lon in coordinates)
    url = f"{OSRM_TABLE_URL.replace('driving', profile)}/{coord_str}"
    params = {"annotations": "duration"}

    logger.info("OSRM Table API call: %d coordinates", len(coordinates))
    try:
        response = requests.get(url, params=params, timeout=60)
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
    if durations is None:
        logger.error("OSRM response missing durations")
        raise RuntimeError("OSRM response missing durations")

    logger.info("OSRM: built %dx%d time matrix", len(durations), len(durations[0]) if durations else 0)
    return durations
