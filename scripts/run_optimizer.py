#!/usr/bin/env python3
"""CLI: read CSV → geocode → build matrix → run solver → print route."""

import json
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.csv_service import read_orders
from services.geocoding_service import GeocodingService
from services.matrix_service import build_time_matrix
from solver.vrptw_solver import solve_vrptw
from utils.time_parser import parse_time_to_seconds, seconds_to_time

logger = logging.getLogger(__name__)
DEFAULT_OFFICE = "вулиця Нагірна, 18, Київ"


def main() -> None:
    args = [a for a in sys.argv[1:] if a not in ("--json", "--verbose", "-v")]
    use_json = "--json" in sys.argv
    verbose = "--verbose" in sys.argv or "-v" in sys.argv

    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
    )

    if len(args) < 1:
        print("Usage: python run_optimizer.py <csv_path> [office_address] [--json] [-v]")
        print("  office_address defaults to:", repr(DEFAULT_OFFICE))
        print("  --json       output route as JSON (order_id, eta, position_in_route)")
        print("  -v, --verbose  enable debug logging (API calls, solver)")
        sys.exit(1)

    csv_path = args[0]
    office_address = args[1] if len(args) > 1 else DEFAULT_OFFICE

    if not use_json:
        print("Pipeline: CSV → Geocode → Matrix → Solver")
        print("-" * 40)

    # 1. Read CSV
    orders = read_orders(csv_path)
    if not use_json:
        print(f"Read {len(orders)} orders from {csv_path}")

    if not orders:
        logger.error("No orders to optimize")
        if use_json:
            print(json.dumps({"route": [], "error": "No orders to optimize"}))
        else:
            print("No orders to optimize.")
        sys.exit(0)

    # 2. Geocode addresses
    geocoder = GeocodingService()
    office_coords = geocoder.geocode(office_address)
    if not office_coords:
        logger.error("Could not geocode office: %s", office_address)
        if use_json:
            print(json.dumps({"route": [], "error": f"Could not geocode office: {office_address}"}))
        else:
            print(f"Error: Could not geocode office address: {office_address}")
        sys.exit(1)

    for order in orders:
        addr = f"{order.city}, {order.address} {order.house}"
        if coords := geocoder.geocode(addr):
            order.lat, order.lng = coords
        elif not use_json:
            print(f"Warning: Could not geocode order {order.id}: {addr}")

    geocoded = [o for o in orders if o.lat is not None]
    if not use_json and len(geocoded) < len(orders):
        print(f"Skipping {len(orders) - len(geocoded)} orders that could not be geocoded")
    if not geocoded:
        logger.error("No geocoded orders to optimize")
        if use_json:
            print(json.dumps({"route": [], "error": "No geocoded orders to optimize"}))
        else:
            print("No geocoded orders to optimize.")
        sys.exit(1)

    # 3. Build matrix [office, order1, order2, ...]
    coords = [office_coords] + [(o.lat, o.lng) for o in geocoded]
    try:
        time_matrix = build_time_matrix(coords)
    except Exception as e:
        logger.exception("Failed to build time matrix: %s", e)
        raise
    if not use_json:
        print(f"Built {len(time_matrix)}x{len(time_matrix)} time matrix")

    # 3b. Build time windows (seconds since midnight)
    SECONDS_PER_DAY = 24 * 60 * 60
    time_windows: list[tuple[int, int]] = [(0, SECONDS_PER_DAY)]  # depot: full day
    for order in geocoded:
        start_sec = parse_time_to_seconds(order.time_start)
        end_sec = parse_time_to_seconds(order.time_end)
        if start_sec is not None and end_sec is not None and start_sec <= end_sec:
            time_windows.append((start_sec, end_sec))
        else:
            time_windows.append((0, SECONDS_PER_DAY))  # no constraint

    # 4. Run solver (VRPTW with time windows)
    route_indices, etas = solve_vrptw(time_matrix, time_windows, depot=0)
    if not route_indices:
        logger.error("Solver found no solution")
        if use_json:
            print(json.dumps({"route": [], "error": "Solver found no solution"}))
        else:
            print("Solver found no solution.")
        sys.exit(1)

    # 5. Output route
    if use_json:
        route_json = [
            {
                "order_id": geocoded[idx - 1].id,
                "eta": seconds_to_time(eta_sec),
                "position_in_route": i,
            }
            for i, (idx, eta_sec) in enumerate(zip(route_indices, etas), 1)
        ]
        print(json.dumps({"route": route_json}, indent=2, ensure_ascii=False))
    else:
        print("-" * 40)
        print("Optimal route (office → deliveries → office):")
        print(f"  Start: {office_address}")
        for i, (idx, eta_sec) in enumerate(zip(route_indices, etas), 1):
            order = geocoded[idx - 1]
            eta_str = seconds_to_time(eta_sec)
            print(f"  {i}. Order {order.id}: {order.city}, {order.address} {order.house}  ETA: {eta_str}")
        print(f"  End: {office_address}")


if __name__ == "__main__":
    main()
