#!/usr/bin/env python3
"""CLI: read CSV → geocode → build matrix → run solver → print route."""

import argparse
import json
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.csv_service import read_orders
from services.geocoding_service import GeocodingService
from services.matrix_service import build_time_matrix
from solver.vrptw_solver import solve_vrptw, MINUTES_PER_DAY
from utils.time_parser import parse_time_to_seconds, seconds_to_time

logger = logging.getLogger(__name__)
DEFAULT_OFFICE = "вулиця Нагірна, 18, Київ"
DEFAULT_START_TIME = "08:00"
SERVICE_TIME_PER_STOP = 3  # minutes

# Node 0 in the matrix is always the depot (office).
# Orders occupy nodes 1..N.
DEPOT_NODE = 0


def node_to_order_index(node: int) -> int:
    """Convert a solver node index (1-based delivery nodes) to geocoded[] index."""
    assert node != DEPOT_NODE, f"Depot node {DEPOT_NODE} must not appear as a delivery stop"
    return node - 1


def parse_time_to_minutes(time_str: str | None) -> int | None:
    """Parse 'HH:MM' to minutes since midnight, or None if invalid."""
    seconds = parse_time_to_seconds(time_str)
    return seconds // 60 if seconds is not None else None


def minutes_to_time(minutes: int) -> str:
    """Format minutes since midnight as 'HH:MM'."""
    return seconds_to_time(minutes * 60)


def format_duration(minutes: float) -> str:
    m = int(minutes)
    if m >= 60:
        return f"{m // 60}h {m % 60}min"
    return f"{m} min"


def format_distance(m: float) -> str:
    if m >= 1000:
        return f"{m / 1000:.1f} km"
    return f"{int(m)} m"


def build_courier_stops(
    route_nodes: list[int],
    geocoded: list,
    time_matrix: list[list[float]],
    courier_start_min: int,
) -> list[dict]:
    """
    Walk a single courier's route and compute arrival, waiting, and ETA per stop.

    Returns a list of stop dicts ready for display / JSON output.
    """
    stops = []
    current_time = courier_start_min
    prev_node = DEPOT_NODE

    for node in route_nodes:
        order = geocoded[node_to_order_index(node)]
        drive_min = int(round(time_matrix[prev_node][node] / 60))
        natural_arrival = current_time + drive_min

        tw_start = parse_time_to_minutes(order.time_start)
        tw_end = parse_time_to_minutes(order.time_end)
        has_window = tw_start is not None and tw_end is not None

        if has_window and natural_arrival < tw_start:
            waiting_min = tw_start - natural_arrival
            eta_min = tw_start
        else:
            waiting_min = 0
            eta_min = natural_arrival

        stops.append({
            "order_id": order.id,
            "order": order,
            "node": node,
            "drive_min": drive_min,
            "natural_arrival": natural_arrival,
            "waiting_min": waiting_min,
            "eta_min": eta_min,
            "tw_start": tw_start,
            "tw_end": tw_end,
            "has_window": has_window,
        })

        current_time = eta_min + SERVICE_TIME_PER_STOP
        prev_node = node

    return stops


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="run_optimizer.py",
        description="Optimize flower delivery routes.",
    )
    parser.add_argument("csv_path", help="Path to orders CSV file")
    parser.add_argument(
        "office_address",
        nargs="?",
        default=DEFAULT_OFFICE,
        help=f"Depot/office address (default: {DEFAULT_OFFICE!r})",
    )
    parser.add_argument(
        "--start-time",
        default=DEFAULT_START_TIME,
        metavar="HH:MM",
        help="Courier shift start time (default: 08:00)",
    )
    parser.add_argument(
        "--couriers",
        type=int,
        default=1,
        metavar="N",
        help="Number of couriers / vehicles (default: 1)",
    )
    parser.add_argument(
        "--capacity",
        type=int,
        default=None,
        metavar="N",
        help="Max packages per courier (default: unlimited)",
    )
    parser.add_argument("--json", action="store_true", help="Output route as JSON")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")

    parsed = parser.parse_args()
    csv_path = parsed.csv_path
    office_address = parsed.office_address
    use_json = parsed.json
    verbose = parsed.verbose
    start_time_str = parsed.start_time
    num_couriers = parsed.couriers
    capacity = parsed.capacity

    if num_couriers < 1:
        print("Error: --couriers must be >= 1")
        sys.exit(1)
    if capacity is not None and capacity < 1:
        print("Error: --capacity must be >= 1")
        sys.exit(1)

    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
    )

    courier_start_min = parse_time_to_minutes(start_time_str)
    if courier_start_min is None:
        print(f"Error: invalid --start-time value: {start_time_str!r} (expected HH:MM)")
        sys.exit(1)

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
            print(json.dumps({"couriers": [], "error": "No orders to optimize"}))
        else:
            print("No orders to optimize.")
        sys.exit(0)

    # 2. Geocode addresses
    geocoder = GeocodingService()
    if office_address.strip() == DEFAULT_OFFICE:
        office_coords = geocoder.geocode(office_address, city="Kyiv", country="UA")
    else:
        office_coords = geocoder.geocode(office_address)
    if not office_coords:
        logger.error("Could not geocode office: %s", office_address)
        if use_json:
            print(json.dumps({"couriers": [], "error": f"Could not geocode office: {office_address}"}))
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
            print(json.dumps({"couriers": [], "error": "No geocoded orders to optimize"}))
        else:
            print("No geocoded orders to optimize.")
        sys.exit(1)

    # Warn if capacity * couriers < orders (mathematically impossible to serve all)
    if capacity is not None and capacity * num_couriers < len(geocoded):
        msg = (
            f"Impossible: {num_couriers} courier(s) × {capacity} packages = "
            f"{num_couriers * capacity} slots, but {len(geocoded)} orders to deliver."
        )
        if use_json:
            print(json.dumps({"couriers": [], "error": msg}))
        else:
            print(f"Error: {msg}")
        sys.exit(1)

    # 3. Build matrix: node 0 = office (depot), nodes 1..N = delivery orders
    coords = [office_coords] + [(o.lat, o.lng) for o in geocoded]
    try:
        time_matrix, distance_matrix = build_time_matrix(coords)
    except Exception as e:
        logger.exception("Failed to build time matrix: %s", e)
        raise
    if not use_json:
        print(f"Built {len(time_matrix)}x{len(time_matrix)} time and distance matrices")

    # 3b. Build time windows in minutes since midnight
    # Depot window anchors start time; delivery orders use their own windows or full day.
    time_windows: list[tuple[int, int]] = [(courier_start_min, MINUTES_PER_DAY)]
    for order in geocoded:
        tw_start = parse_time_to_minutes(order.time_start)
        tw_end = parse_time_to_minutes(order.time_end)
        if tw_start is not None and tw_end is not None and tw_start <= tw_end:
            time_windows.append((tw_start, tw_end))
        else:
            time_windows.append((0, MINUTES_PER_DAY))

    # 4. Run solver
    routes, _, _, _ = solve_vrptw(
        time_matrix,
        time_windows,
        depot=DEPOT_NODE,
        courier_start_time=courier_start_min,
        service_time_per_stop=SERVICE_TIME_PER_STOP,
        num_couriers=num_couriers,
        capacity=capacity,
    )

    if all(len(r) == 0 for r in routes):
        logger.error("Solver found no solution")
        if use_json:
            print(json.dumps({"couriers": [], "error": "Solver found no solution"}))
        else:
            print("Solver found no solution.")
        sys.exit(1)

    # 5. Post-process each courier's route
    courier_data = []
    for v, route_nodes in enumerate(routes):
        stops = build_courier_stops(route_nodes, geocoded, time_matrix, courier_start_min)

        last_node = route_nodes[-1] if route_nodes else DEPOT_NODE
        return_drive_min = int(round(time_matrix[last_node][DEPOT_NODE] / 60))

        prev_nodes = [DEPOT_NODE] + list(route_nodes)
        total_distance_m = sum(
            distance_matrix[prev_nodes[i]][route_nodes[i]]
            for i in range(len(route_nodes))
        ) + distance_matrix[last_node][DEPOT_NODE]
        total_drive_min = sum(s["drive_min"] for s in stops) + return_drive_min

        courier_data.append({
            "courier_id": v + 1,
            "stops": stops,
            "return_drive_min": return_drive_min,
            "total_drive_min": total_drive_min,
            "total_distance_m": total_distance_m,
        })

    # 6. Output
    if use_json:
        couriers_json = []
        for cd in courier_data:
            route_json = [
                {
                    "order_id": s["order_id"],
                    "eta": minutes_to_time(s["eta_min"]),
                    "drive_time_min": s["drive_min"],
                    "waiting_time_min": s["waiting_min"],
                    "time_window": (
                        f"{minutes_to_time(s['tw_start'])}-{minutes_to_time(s['tw_end'])}"
                        if s["has_window"]
                        else None
                    ),
                    "position_in_route": i + 1,
                }
                for i, s in enumerate(cd["stops"])
            ]
            couriers_json.append({
                "courier_id": cd["courier_id"],
                "route": route_json,
                "statistics": {
                    "total_drive_time_min": cd["total_drive_min"],
                    "total_drive_time": format_duration(cd["total_drive_min"]),
                    "total_distance_m": int(cd["total_distance_m"]),
                    "total_distance": format_distance(cd["total_distance_m"]),
                },
            })

        grand_drive = sum(cd["total_drive_min"] for cd in courier_data)
        grand_dist = sum(cd["total_distance_m"] for cd in courier_data)
        print(
            json.dumps(
                {
                    "courier_start": minutes_to_time(courier_start_min),
                    "num_couriers": num_couriers,
                    "capacity": capacity,
                    "couriers": couriers_json,
                    "statistics": {
                        "total_drive_time_min": grand_drive,
                        "total_drive_time": format_duration(grand_drive),
                        "total_distance_m": int(grand_dist),
                        "total_distance": format_distance(grand_dist),
                    },
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        for cd in courier_data:
            stops = cd["stops"]
            print()
            print(f"Courier {cd['courier_id']}")
            print("-" * 40)
            if not stops:
                print("  (no deliveries assigned)")
                continue
            print(f"Start: {minutes_to_time(courier_start_min)}  Office ({office_address})")
            print()
            for i, s in enumerate(stops, 1):
                o = s["order"]
                addr = f"{o.city}, {o.address} {o.house}"
                print(f"  {i}. Order {s['order_id']}  —  {addr}")
                if s["has_window"] and s["waiting_min"] > 0:
                    print(f"     Arrival: {minutes_to_time(s['natural_arrival'])}")
                    print(f"     Window:  {minutes_to_time(s['tw_start'])}–{minutes_to_time(s['tw_end'])}")
                    print(f"     Wait:    {format_duration(s['waiting_min'])}")
                    print(f"     ETA:     {minutes_to_time(s['eta_min'])}")
                else:
                    print(f"     ETA:     {minutes_to_time(s['eta_min'])}")
                print(f"     Drive:   {format_duration(s['drive_min'])}")
                print()
            print(f"Return to depot.  ({format_duration(cd['return_drive_min'])})")
            print()
            print(f"  Drive total: {format_duration(cd['total_drive_min'])}")
            print(f"  Distance:    {format_distance(cd['total_distance_m'])}")

        print()
        print("=" * 40)
        print("Summary:")
        print(f"  Couriers:    {num_couriers}")
        if capacity is not None:
            print(f"  Capacity:    {capacity} packages/courier")
        print(f"  Start time:  {minutes_to_time(courier_start_min)}")
        total_orders = sum(len(cd["stops"]) for cd in courier_data)
        print(f"  Orders:      {total_orders} delivered")
        grand_drive = sum(cd["total_drive_min"] for cd in courier_data)
        grand_dist = sum(cd["total_distance_m"] for cd in courier_data)
        print(f"  Total drive: {format_duration(grand_drive)}")
        print(f"  Total dist:  {format_distance(grand_dist)}")


if __name__ == "__main__":
    main()
