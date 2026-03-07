"""FastAPI server for the flower delivery route optimizer."""

import logging
import sys
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

sys.path.insert(0, str(Path(__file__).resolve().parent))

from services.csv_service import read_orders
from services.geocoding_service import GeocodingService
from services.matrix_service import build_time_matrix
from solver.vrptw_solver import solve_vrptw, MINUTES_PER_DAY
from utils.time_parser import parse_time_to_seconds, seconds_to_time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

DEPOT_ADDRESS = "вулиця Нагірна, 18, Київ"
SERVICE_TIME_PER_STOP = 3  # minutes


def _parse_minutes(time_str: str | None) -> int | None:
    s = parse_time_to_seconds(time_str)
    return s // 60 if s is not None else None


def _fmt_time(minutes: int) -> str:
    return seconds_to_time(minutes * 60)


app = FastAPI(title="Kvitkova Povnya Route Optimizer")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/optimize")
async def optimize(
    file: UploadFile = File(...),
    start_time: str = Form("09:00"),
    num_couriers: int = Form(1),
    capacity: int = Form(None),
):
    # --- 1. Parse CSV (write to temp file because read_orders needs a path) ---
    raw = await file.read()
    try:
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="wb") as tmp:
            tmp.write(raw)
            tmp_path = tmp.name
        orders = read_orders(tmp_path)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"CSV parse error: {exc}") from exc

    if not orders:
        raise HTTPException(status_code=400, detail="No orders found in CSV")

    courier_start_min = _parse_minutes(start_time)
    if courier_start_min is None:
        raise HTTPException(status_code=400, detail=f"Invalid start_time: {start_time!r}")

    if capacity and capacity * num_couriers < len(orders):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Impossible: {num_couriers} courier(s) × {capacity} packages = "
                f"{num_couriers * capacity} slots, but {len(orders)} orders to deliver."
            ),
        )

    # --- 2. Geocode ---
    geocoder = GeocodingService()

    office_coords = geocoder.geocode(DEPOT_ADDRESS)
    if not office_coords:
        raise HTTPException(status_code=500, detail=f"Could not geocode depot: {DEPOT_ADDRESS}")

    for order in orders:
        addr = f"{order.city}, {order.address} {order.house}"
        coords = geocoder.geocode(addr)
        if coords:
            order.lat, order.lng = coords
        else:
            logger.warning("Could not geocode order %s: %s", order.id, addr)

    geocoded = [o for o in orders if o.lat is not None]
    if not geocoded:
        raise HTTPException(status_code=500, detail="No orders could be geocoded")

    # --- 3. Build time/distance matrices ---
    coords = [office_coords] + [(o.lat, o.lng) for o in geocoded]
    try:
        time_matrix, distance_matrix = build_time_matrix(coords)
    except Exception as exc:
        logger.exception("Matrix build failed")
        raise HTTPException(status_code=500, detail=f"Matrix build failed: {exc}") from exc

    # --- 4. Time windows ---
    time_windows: list[tuple[int, int]] = [(courier_start_min, MINUTES_PER_DAY)]
    for order in geocoded:
        tw_s = _parse_minutes(order.time_start)
        tw_e = _parse_minutes(order.time_end)
        if tw_s is not None and tw_e is not None and tw_s <= tw_e:
            time_windows.append((tw_s, tw_e))
        else:
            time_windows.append((0, MINUTES_PER_DAY))

    # --- 5. Solve ---
    routes, _ = solve_vrptw(
        time_matrix,
        time_windows,
        depot=0,
        courier_start_time=courier_start_min,
        service_time_per_stop=SERVICE_TIME_PER_STOP,
        num_couriers=num_couriers,
        capacity=capacity,
    )

    if all(len(r) == 0 for r in routes):
        raise HTTPException(status_code=500, detail="Solver found no feasible solution")

    # --- 6. Build response in the shape the frontend OptimizationResult expects ---
    result_routes = []
    total_deliveries = 0
    total_drive_min = 0
    total_distance_km = 0.0

    for v, route_nodes in enumerate(routes):
        if not route_nodes:
            continue  # courier has no deliveries — skip from results

        stops = []
        current_time = courier_start_min
        prev_node = 0

        prev_chain = [0] + list(route_nodes)
        route_distance_m = sum(
            distance_matrix[prev_chain[i]][route_nodes[i]]
            for i in range(len(route_nodes))
        ) + distance_matrix[route_nodes[-1]][0]

        for node in route_nodes:
            order = geocoded[node - 1]
            drive_min = int(round(time_matrix[prev_node][node] / 60))
            natural_arrival = current_time + drive_min

            tw_s = _parse_minutes(order.time_start)
            tw_e = _parse_minutes(order.time_end)
            has_window = tw_s is not None and tw_e is not None

            if has_window and natural_arrival < tw_s:
                wait_min = tw_s - natural_arrival
                eta_min = tw_s
            else:
                wait_min = 0
                eta_min = natural_arrival

            stops.append({
                "address": f"{order.city}, {order.address} {order.house}",
                "eta": _fmt_time(eta_min),
                "driveMin": drive_min,
                "waitMin": wait_min,
                "lat": order.lat,
                "lng": order.lng,
            })

            current_time = eta_min + SERVICE_TIME_PER_STOP
            prev_node = node

        return_min = int(round(time_matrix[route_nodes[-1]][0] / 60))
        route_drive_min = sum(s["driveMin"] for s in stops) + return_min
        route_distance_km = route_distance_m / 1000

        result_routes.append({
            "courierId": v + 1,
            "stops": stops,
            "totalDriveMin": route_drive_min,
            "totalDistanceKm": round(route_distance_km, 2),
        })

        total_deliveries += len(stops)
        total_drive_min += route_drive_min
        total_distance_km += route_distance_km

    return {
        "routes": result_routes,
        "stats": {
            "totalDeliveries": total_deliveries,
            "totalDriveMin": total_drive_min,
            "totalDistanceKm": round(total_distance_km, 2),
            "numCouriers": len(result_routes),
        },
        "depot": {
            "lat": office_coords[0],
            "lng": office_coords[1],
        },
    }
