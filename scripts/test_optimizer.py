"""
Diagnostic script: run the full optimization pipeline on a small synthetic dataset
and print detailed per-courier route stats.

Usage:
    python scripts/test_optimizer.py [num_stops] [num_couriers]

Defaults: 10 stops, 2 couriers, no capacity limit, start 09:00.
"""
import logging
import math
import sys
from pathlib import Path

# Make project root importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

from services.geocoding_service import GeocodingService
from services.matrix_service import build_time_matrix
from solver.vrptw_solver import solve_vrptw, MINUTES_PER_DAY
from utils.time_parser import parse_time_to_seconds, seconds_to_time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("test_optimizer")

DEPOT_ADDRESS = "вулиця Нагірна, 18, Київ, Ukraine"

# Kyiv-area test addresses spread across the city to detect zig-zags
TEST_ADDRESSES = [
    "Kyiv, Khreshchatyk Street 1, Ukraine",
    "Kyiv, Obolon Avenue 15, Ukraine",
    "Kyiv, Poznyaky, Akhmatovoi Street 5, Ukraine",
    "Bucha, Vokzalna Street 10, Ukraine",
    "Brovary, Kyivska Street 20, Ukraine",
    "Kyiv, Boryspilska Street 8, Ukraine",
    "Kyiv, Heroiv Dnipra Street 33, Ukraine",
    "Kyiv, Akademika Palladin Avenue 42, Ukraine",
    "Kyiv, Vasylkivska Street 55, Ukraine",
    "Kyiv, Darnytsia, Mistobudivna Street 3, Ukraine",
    "Irpin, Soborna Street 12, Ukraine",
    "Kyiv, Svyatoshyn, Academica Korolova Street 8, Ukraine",
]


def _fmt_time(minutes: int) -> str:
    return seconds_to_time(minutes * 60)


def _parse_minutes(t: str | None) -> int | None:
    s = parse_time_to_seconds(t)
    return s // 60 if s is not None else None


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def main():
    num_stops = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    num_couriers = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    start_time = "09:00"
    courier_start_min = _parse_minutes(start_time)

    addresses = TEST_ADDRESSES[:num_stops]
    logger.info("=== test_optimizer: %d stops, %d couriers ===", num_stops, num_couriers)

    # --- Geocode ---
    geocoder = GeocodingService()
    depot_coords = geocoder.geocode(DEPOT_ADDRESS)
    if not depot_coords:
        logger.error("Could not geocode depot")
        sys.exit(1)
    logger.info("Depot: %.5f, %.5f", *depot_coords)

    stop_coords: list[tuple[float, float]] = []
    geocoded_addrs: list[str] = []
    for addr in addresses:
        coords = geocoder.geocode(addr)
        if coords:
            stop_coords.append(coords)
            geocoded_addrs.append(addr)
            logger.info("  %-60s → %.5f, %.5f", addr[:60], *coords)
        else:
            logger.warning("  FAILED to geocode: %s", addr)

    if not stop_coords:
        logger.error("No stops geocoded")
        sys.exit(1)

    # --- Straight-line distances from depot (sanity check) ---
    logger.info("\n--- Straight-line distances from depot ---")
    for addr, (lat, lng) in zip(geocoded_addrs, stop_coords):
        d = haversine_km(depot_coords[0], depot_coords[1], lat, lng)
        logger.info("  %-55s  %.1f km", addr[:55], d)

    # --- Matrix ---
    all_coords = [depot_coords] + stop_coords
    time_matrix, distance_matrix = build_time_matrix(all_coords)

    # --- Time windows (none for this test) ---
    time_windows = [(0, MINUTES_PER_DAY)] * len(all_coords)

    # --- KMeans clustering (same logic as main.py) ---
    import random
    def kmeans_cluster(points, k, max_iter=100, seed=42):
        rng = random.Random(seed)
        n = len(points)
        if k >= n:
            return list(range(n))
        centroids = [rng.choice(points)]
        for _ in range(k - 1):
            dists = [min((p[0]-c[0])**2+(p[1]-c[1])**2 for c in centroids) for p in points]
            total = sum(dists)
            r = rng.random() * total
            cumsum = 0.0
            chosen = points[-1]
            for p, d in zip(points, dists):
                cumsum += d
                if cumsum >= r:
                    chosen = p
                    break
            centroids.append(chosen)
        assignments = [0] * n
        for _ in range(max_iter):
            new_a = [min(range(k), key=lambda ci, p=p: (p[0]-centroids[ci][0])**2+(p[1]-centroids[ci][1])**2) for p in points]
            if new_a == assignments:
                break
            assignments = new_a
            for ci in range(k):
                pts = [points[i] for i in range(n) if assignments[i] == ci]
                if pts:
                    centroids[ci] = (sum(p[0] for p in pts)/len(pts), sum(p[1] for p in pts)/len(pts))
        return assignments

    cluster_assignments = kmeans_cluster(stop_coords, k=num_couriers)
    initial_routes: list[list[int]] = [[] for _ in range(num_couriers)]
    for idx, ci in enumerate(cluster_assignments):
        initial_routes[ci].append(idx + 1)

    logger.info("\n--- KMeans clusters ---")
    for ci, nodes in enumerate(initial_routes):
        addrs = [geocoded_addrs[n - 1] for n in nodes]
        logger.info("  Cluster %d (%d stops): %s", ci + 1, len(nodes), ", ".join(a[:40] for a in addrs))

    # --- Solve ---
    routes, etas = solve_vrptw(
        time_matrix,
        time_windows,
        depot=0,
        courier_start_time=courier_start_min,
        service_time_per_stop=3,
        num_couriers=num_couriers,
        capacity=None,
        initial_routes=initial_routes,
        distance_matrix=distance_matrix,
    )

    # --- Print results ---
    logger.info("\n=== RESULTS ===")
    total_dist = 0.0
    for v, (route, route_etas) in enumerate(zip(routes, etas)):
        if not route:
            logger.info("Courier %d: no stops", v + 1)
            continue
        route_dist_km = sum(
            distance_matrix[([0] + route)[i]][route[i]] for i in range(len(route))
        ) / 1000
        total_dist += route_dist_km
        logger.info("Courier %d — %d stops, %.1f km road distance:", v + 1, len(route), route_dist_km)
        for node, eta_min in zip(route, route_etas):
            addr = geocoded_addrs[node - 1]
            lat, lng = stop_coords[node - 1]
            straight = haversine_km(depot_coords[0], depot_coords[1], lat, lng)
            logger.info("  [%s] %s (%.1f km from depot)", _fmt_time(eta_min), addr[:60], straight)
    logger.info("Total road distance: %.1f km", total_dist)


if __name__ == "__main__":
    main()
