"""FastAPI server for the flower delivery route optimizer."""

import asyncio
import logging
import math
import os
import random
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parent))

from services.csv_service import read_orders
from services.feasibility import capacity_minimum_couriers, estimate_minimum_couriers
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

DEPOT_ADDRESS = "вулиця Нагірна, 18, Київ, Ukraine"
SERVICE_TIME_PER_STOP = 3  # minutes
OSRM_ROUTE_URL = os.getenv("OSRM_URL", "http://router.project-osrm.org/table/v1/driving").replace(
    "/table/v1/", "/route/v1/"
)

# Set to False to skip OSRM road geometry requests entirely (faster, draws straight lines)
ENABLE_ROUTE_GEOMETRY = True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _kmeans_cluster(
    points: list[tuple[float, float]],
    k: int,
    max_iter: int = 100,
    seed: int = 42,
) -> list[int]:
    rng = random.Random(seed)
    n = len(points)
    if k >= n:
        return list(range(n))

    centroids: list[tuple[float, float]] = [rng.choice(points)]
    for _ in range(k - 1):
        dists = [
            min((p[0] - c[0]) ** 2 + (p[1] - c[1]) ** 2 for c in centroids)
            for p in points
        ]
        total = sum(dists)
        if total == 0:
            centroids.append(rng.choice(points))
            continue
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
        new_assignments = [
            min(range(k), key=lambda ci, p=p: (p[0] - centroids[ci][0]) ** 2 + (p[1] - centroids[ci][1]) ** 2)
            for p in points
        ]
        if new_assignments == assignments:
            break
        assignments = new_assignments
        for ci in range(k):
            cluster_pts = [points[i] for i in range(n) if assignments[i] == ci]
            if cluster_pts:
                centroids[ci] = (
                    sum(p[0] for p in cluster_pts) / len(cluster_pts),
                    sum(p[1] for p in cluster_pts) / len(cluster_pts),
                )

    return assignments


def fetch_route_geometry(coords: list[tuple[float, float]]) -> list[list[float]] | None:
    """Call OSRM Route API; returns None on any failure (caller draws straight lines)."""
    if not ENABLE_ROUTE_GEOMETRY or len(coords) < 2:
        return None
    coord_str = ";".join(f"{lng},{lat}" for lat, lng in coords)
    try:
        resp = requests.get(
            f"{OSRM_ROUTE_URL}/{coord_str}",
            params={"overview": "full", "geometries": "geojson"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != "Ok":
            logger.warning("OSRM route: unexpected code %s", data.get("code"))
            return None
        return [[lat, lng] for lng, lat in data["routes"][0]["geometry"]["coordinates"]]
    except Exception as exc:
        logger.warning("OSRM route geometry fetch failed: %s", exc)
        return None


def _parse_minutes(time_str: str | None) -> int | None:
    s = parse_time_to_seconds(time_str)
    return s // 60 if s is not None else None


def _fmt_time(minutes: int) -> str:
    return seconds_to_time(minutes * 60)


# ---------------------------------------------------------------------------
# Synchronous optimization pipeline (runs in a thread pool via asyncio.to_thread)
# ---------------------------------------------------------------------------

def _optimize_sync(
    raw: bytes,
    start_time: str,
    num_couriers: int,
    capacity: int | None,
) -> dict:
    """
    Full blocking pipeline: CSV → geocode → matrix → solve → build response.
    Must NOT be called directly from an async context — use asyncio.to_thread().
    """
    t_start = time.monotonic()
    logger.info(
        "Optimization pipeline started: couriers=%d, start_time=%s, capacity=%s",
        num_couriers, start_time, capacity,
    )

    # 1. Parse CSV
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

    # 2. Geocode
    geocoder = GeocodingService()

    try:
        office_coords = geocoder.geocode(DEPOT_ADDRESS)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Geocoding error: {exc}") from exc
    if not office_coords:
        raise HTTPException(status_code=500, detail=f"Could not geocode depot: {DEPOT_ADDRESS}")

    dropped_orders = 0
    for order in orders:
        addr = f"{order.city}, {order.address} {order.house}, Ukraine"
        try:
            coords = geocoder.geocode(addr)
        except Exception as exc:
            logger.warning("Order %s geocoding exception: %s — dropping", order.id, exc)
            dropped_orders += 1
            continue
        if coords:
            order.lat, order.lng = coords
        else:
            logger.warning("Order %s dropped due to geocoding failure: %s", order.id, addr)
            dropped_orders += 1

    geocoded = [o for o in orders if o.lat is not None]
    if not geocoded:
        raise HTTPException(status_code=500, detail="No orders could be geocoded")

    if dropped_orders:
        logger.warning("%d order(s) dropped due to geocoding failures", dropped_orders)

    depot_lat, depot_lng = office_coords
    geocoded.sort(key=lambda o: math.atan2(o.lat - depot_lat, o.lng - depot_lng))

    # 3. Build matrices (called exactly once)
    coords = [office_coords] + [(o.lat, o.lng) for o in geocoded]
    logger.info("Building OSRM matrix for %d coordinates", len(coords))
    try:
        time_matrix, distance_matrix = build_time_matrix(coords)
    except Exception as exc:
        logger.exception("Matrix build failed")
        raise HTTPException(status_code=500, detail=f"Matrix build failed: {exc}") from exc

    # 4. Time windows
    time_windows: list[tuple[int, int]] = [(courier_start_min, MINUTES_PER_DAY)]
    for order in geocoded:
        tw_s = _parse_minutes(order.time_start)
        tw_e = _parse_minutes(order.time_end)
        if tw_s is not None and tw_e is not None and tw_s <= tw_e:
            time_windows.append((tw_s, tw_e))
        else:
            time_windows.append((0, MINUTES_PER_DAY))

    # 5. Feasibility check
    cap_required = capacity_minimum_couriers(len(geocoded), capacity) if capacity else 1
    tw_required = estimate_minimum_couriers(
        time_windows, time_matrix, SERVICE_TIME_PER_STOP, courier_start_min
    )
    minimum_required = max(cap_required, tw_required)

    if num_couriers < minimum_required:
        reason = "capacity_constraint" if cap_required >= tw_required else "time_window_constraint"
        # Return a special sentinel so the async wrapper can return a JSONResponse
        return {
            "__infeasible__": True,
            "error": "INFEASIBLE",
            "message": (
                f"Неможливо виконати маршрут з {num_couriers} кур'єром(-ами). "
                f"Потрібно мінімум {minimum_required}."
            ),
            "minimum_couriers_required": minimum_required,
            "reason": reason,
        }

    # 6. KMeans pre-clustering → initial_routes hint
    stop_coords = [(o.lat, o.lng) for o in geocoded]
    cluster_assignments = _kmeans_cluster(stop_coords, k=num_couriers)

    initial_routes: list[list[int]] = [[] for _ in range(num_couriers)]
    for stop_idx, cluster_id in enumerate(cluster_assignments):
        initial_routes[cluster_id].append(stop_idx + 1)

    for ci, r in enumerate(initial_routes):
        logger.info("KMeans cluster %d: %d stops — nodes %s", ci + 1, len(r), r)

    # 7. Solve
    try:
        routes, _ = solve_vrptw(
            time_matrix,
            time_windows,
            depot=0,
            courier_start_time=courier_start_min,
            service_time_per_stop=SERVICE_TIME_PER_STOP,
            num_couriers=num_couriers,
            capacity=capacity,
            initial_routes=initial_routes,
            distance_matrix=distance_matrix,
        )
    except Exception as exc:
        logger.exception("Solver crashed")
        raise HTTPException(status_code=500, detail=f"Solver error: {exc}") from exc

    if all(len(r) == 0 for r in routes):
        raise HTTPException(status_code=500, detail="Solver found no feasible solution")

    # 8. Build response (geometry fetched in parallel after the main loop)
    result_routes = []
    geo_coords_per_route: list[list[tuple[float, float]]] = []
    total_deliveries = 0
    total_drive_min = 0
    total_distance_km = 0.0

    for v, route_nodes in enumerate(routes):
        if not route_nodes:
            continue

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
                "timeStart": order.time_start,
                "timeEnd": order.time_end,
            })

            current_time = eta_min + SERVICE_TIME_PER_STOP
            prev_node = node

        route_drive_min = sum(s["driveMin"] for s in stops)
        route_distance_km = route_distance_m / 1000

        geo_coords = (
            [office_coords]
            + [(geocoded[n - 1].lat, geocoded[n - 1].lng) for n in route_nodes]
        )
        geo_coords_per_route.append(geo_coords)

        result_routes.append({
            "courierId": v + 1,
            "stops": stops,
            "totalDriveMin": route_drive_min,
            "totalDistanceKm": round(route_distance_km, 2),
            "geometry": None,  # filled below
        })

        total_deliveries += len(stops)
        total_drive_min += route_drive_min
        total_distance_km += route_distance_km

    # Fetch all route geometries in parallel — was sequential (n × 5 s), now max 5 s total.
    if geo_coords_per_route:
        with ThreadPoolExecutor(max_workers=len(geo_coords_per_route)) as executor:
            geometries = list(executor.map(fetch_route_geometry, geo_coords_per_route))
        for i, geom in enumerate(geometries):
            result_routes[i]["geometry"] = geom

    elapsed = time.monotonic() - t_start
    logger.info(
        "Optimization finished in %.2fs — %d routes, %d deliveries, %d dropped",
        elapsed, len(result_routes), total_deliveries, dropped_orders,
    )

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
        "droppedOrders": dropped_orders,
    }


def _recalculate_sync(
    body_routes: list,
    depot_coords: tuple[float, float],
    courier_start_min: int,
) -> dict:
    """Blocking recalculate pipeline — run via asyncio.to_thread()."""
    depot_lat, depot_lng = depot_coords
    result_routes = []
    total_deliveries = 0
    total_drive_min = 0
    total_distance_km = 0.0

    for route in body_routes:
        if not route.stops:
            continue

        courier_stops = route.stops
        courier_coords = [depot_coords] + [(s.lat, s.lng) for s in courier_stops]

        logger.info("Building OSRM matrix for %d coordinates", len(courier_coords))
        try:
            time_matrix, distance_matrix = build_time_matrix(courier_coords)
        except Exception as exc:
            logger.exception("Matrix build failed for courier %d", route.courierId)
            raise HTTPException(status_code=500, detail=f"Matrix build failed: {exc}") from exc

        stops_out = []
        current_time = courier_start_min
        route_distance_m = 0.0

        for i, stop in enumerate(courier_stops):
            from_node = i
            to_node = i + 1
            drive_min = int(round(time_matrix[from_node][to_node] / 60))
            route_distance_m += distance_matrix[from_node][to_node]
            natural_arrival = current_time + drive_min

            tw_s = _parse_minutes(stop.timeStart)
            tw_e = _parse_minutes(stop.timeEnd)
            has_window = tw_s is not None and tw_e is not None

            if has_window and natural_arrival < tw_s:
                wait_min = tw_s - natural_arrival
                eta_min = tw_s
            else:
                wait_min = 0
                eta_min = natural_arrival

            stops_out.append({
                "address": stop.address,
                "eta": _fmt_time(eta_min),
                "driveMin": drive_min,
                "waitMin": wait_min,
                "lat": stop.lat,
                "lng": stop.lng,
                "timeStart": stop.timeStart,
                "timeEnd": stop.timeEnd,
            })

            current_time = eta_min + SERVICE_TIME_PER_STOP

        route_drive_min = sum(s["driveMin"] for s in stops_out)
        route_distance_km = route_distance_m / 1000

        geo_coords = [depot_coords] + [(s.lat, s.lng) for s in courier_stops]
        geometry = fetch_route_geometry(geo_coords)

        result_routes.append({
            "courierId": route.courierId,
            "stops": stops_out,
            "totalDriveMin": route_drive_min,
            "totalDistanceKm": round(route_distance_km, 2),
            "geometry": geometry,
        })

        total_deliveries += len(stops_out)
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
        "depot": {"lat": depot_lat, "lng": depot_lng},
    }


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="Kvitkova Povnya Route Optimizer")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal server error: {exc}"},
    )


class RecalculateStop(BaseModel):
    lat: float
    lng: float
    address: str
    timeStart: str | None = None
    timeEnd: str | None = None


class RecalculateRoute(BaseModel):
    courierId: int
    stops: list[RecalculateStop]


class RecalculateRequest(BaseModel):
    routes: list[RecalculateRoute]
    depot: dict  # {"lat": float, "lng": float}
    startTime: str = "09:00"


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/optimize")
async def optimize(
    file: UploadFile = File(...),
    start_time: str = Form("09:00"),
    num_couriers: int = Form(1),
    capacity: int | None = Form(None),
):
    # Read file content here (async-safe); everything else runs in a thread.
    raw = await file.read()
    try:
        result = await asyncio.to_thread(_optimize_sync, raw, start_time, num_couriers, capacity)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unexpected error in optimization thread")
        raise HTTPException(status_code=500, detail=f"Internal error: {exc}") from exc

    if result.get("__infeasible__"):
        return JSONResponse(status_code=422, content={k: v for k, v in result.items() if k != "__infeasible__"})

    return result


@app.post("/api/recalculate")
async def recalculate_routes(body: RecalculateRequest):
    if not body.routes or all(len(r.stops) == 0 for r in body.routes):
        raise HTTPException(status_code=400, detail="No stops provided")

    courier_start_min = _parse_minutes(body.startTime)
    if courier_start_min is None:
        raise HTTPException(status_code=400, detail=f"Invalid startTime: {body.startTime!r}")

    depot_lat = body.depot.get("lat")
    depot_lng = body.depot.get("lng")
    if depot_lat is None or depot_lng is None:
        raise HTTPException(status_code=400, detail="depot must have lat and lng")

    try:
        result = await asyncio.to_thread(
            _recalculate_sync, body.routes, (depot_lat, depot_lng), courier_start_min
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unexpected error in recalculate thread")
        raise HTTPException(status_code=500, detail=f"Internal error: {exc}") from exc

    return result
