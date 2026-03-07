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
        time_matrix, distance_matrix = build_time_matrix(coords)
    except Exception as e:
        logger.exception("Failed to build time matrix: %s", e)
        raise
    if not use_json:
        print(f"Built {len(time_matrix)}x{len(time_matrix)} time and distance matrices")

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

    # 5. Route statistics: full sequence is depot -> r0 -> r1 -> ... -> depot
    def safe_float(x):
        return float(x) if x is not None else 0.0

    full_route = [0] + list(route_indices) + [0]
    total_travel_time_sec = sum(
        safe_float(time_matrix[full_route[i]][full_route[i + 1]])
        for i in range(len(full_route) - 1)
    )
    total_distance_m = sum(
        safe_float(distance_matrix[full_route[i]][full_route[i + 1]])
        for i in range(len(full_route) - 1)
    )
    segment_times_sec = [
        safe_float(time_matrix[full_route[i]][full_route[i + 1]])
        for i in range(len(full_route) - 1)
    ]

    def format_duration(sec: float) -> str:
        m = int(sec // 60)
        s = int(sec % 60)
        if m >= 60:
            return f"{m // 60}h {m % 60}min"
        return f"{m} min" if s == 0 else f"{m} min {s}s"

    def format_distance(m: float) -> str:
        if m >= 1000:
            return f"{m / 1000:.1f} km"
        return f"{int(m)} m"

    # 6. Output route
    if use_json:
        route_json = [
            {
                "order_id": geocoded[idx - 1].id,
                "eta": seconds_to_time(eta_sec),
                "position_in_route": i,
                "travel_time_from_previous_sec": int(segment_times_sec[i - 1]),
            }
            for i, (idx, eta_sec) in enumerate(zip(route_indices, etas), 1)
        ]
        print(
            json.dumps(
                {
                    "route": route_json,
                    "statistics": {
                        "total_travel_time_sec": int(total_travel_time_sec),
                        "total_travel_time": format_duration(total_travel_time_sec),
                        "total_distance_m": int(total_distance_m),
                        "total_distance": format_distance(total_distance_m),
                        "segment_travel_times_sec": [int(t) for t in segment_times_sec],
                        "segment_travel_times": [format_duration(t) for t in segment_times_sec],
                    },
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        print("-" * 40)
        print("Optimal route (office → deliveries → office):")
        print(f"  Start: {office_address}")
        for i, (idx, eta_sec) in enumerate(zip(route_indices, etas), 1):
            order = geocoded[idx - 1]
            eta_str = seconds_to_time(eta_sec)
            seg = format_duration(segment_times_sec[i])  # segment into this stop
            print(f"  {i}. Order {order.id}: {order.city}, {order.address} {order.house}  ETA: {eta_str}  (drive: {seg})")
        print(f"  End: {office_address}")
        # Last segment: last stop → office
        print("-" * 40)
        print("Route statistics:")
        print(f"  Total travel time: {format_duration(total_travel_time_sec)}")
        print(f"  Total distance:   {format_distance(total_distance_m)}")
        print("  Travel time between stops:")
        print(f"    Office → Order {geocoded[route_indices[0] - 1].id}: {format_duration(segment_times_sec[0])}")
        for i in range(1, len(route_indices)):
            from_id = geocoded[route_indices[i - 1] - 1].id
            to_id = geocoded[route_indices[i] - 1].id
            print(f"    Order {from_id} → Order {to_id}: {format_duration(segment_times_sec[i])}")
        print(f"    Order {geocoded[route_indices[-1] - 1].id} → Office: {format_duration(segment_times_sec[-1])}")


if __name__ == "__main__":
    main()
