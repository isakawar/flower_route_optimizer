"""FastAPI server for the flower delivery route optimizer."""

import asyncio
import csv as _csv
import io
import json as _json
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

from fastapi import FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

try:
    from redis import Redis as _SyncRedis
    from rq import Queue as _RQueue, get_current_job as _get_current_job
    from rq.job import Job as _Job, NoSuchJobError as _NoSuchJobError

    _REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
    _rq_redis = _SyncRedis.from_url(_REDIS_URL, socket_connect_timeout=2)
    _rq_queue: "_RQueue | None" = _RQueue(connection=_rq_redis)
except Exception as _rq_err:
    _rq_queue = None
    _rq_redis = None
    _get_current_job = lambda: None  # type: ignore[assignment]
    logging.getLogger(__name__).warning("RQ unavailable, will run synchronously: %s", _rq_err)

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
SERVICE_TIME_PER_STOP = 15  # minutes (drive to door, hand over, sign)
MAX_ROUTE_DURATION_MIN = 3 * 60  # 3h max per route — flower freshness + courier shift
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
# RQ progress helper
# ---------------------------------------------------------------------------

def _report_step(step_id: str) -> None:
    """Store current progress step in RQ job meta (no-op when not in a worker)."""
    try:
        job = _get_current_job()
        if job:
            job.meta["currentStep"] = step_id
            job.save_meta()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Synchronous optimization pipeline (runs in a thread pool via asyncio.to_thread)
# ---------------------------------------------------------------------------

def _optimize_sync(
    raw: bytes,
    start_time: str,
    num_couriers: int | None,
    capacity: int | None,
    time_buffer_min: int = 0,
) -> dict:
    """
    Full blocking pipeline: CSV → geocode → matrix → solve → build response.
    Must NOT be called directly from an async context — use asyncio.to_thread().

    num_couriers=None → auto-calculate minimum required couriers.
    time_buffer_min   → subtract this many minutes from every delivery window end
                        so the solver never plans a delivery that arrives too close
                        to the deadline (e.g. 17:55 when window closes at 18:00).
    """
    t_start = time.monotonic()
    logger.info(
        "Optimization pipeline started: couriers=%s, start_time=%s, capacity=%s, buffer=%dmin",
        num_couriers, start_time, capacity, time_buffer_min,
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
    _report_step("geocode")
    geocoder = GeocodingService()

    try:
        office_coords = geocoder.geocode(
            DEPOT_ADDRESS,
            city="Kyiv",
            country="UA",
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Geocoding error: {exc}") from exc
    if not office_coords:
        raise HTTPException(status_code=500, detail=f"Could not geocode depot: {DEPOT_ADDRESS}")

    def _geocode_order(order):
        addr = f"{order.city}, {order.address} {order.house}, Ukraine"
        try:
            return geocoder.geocode(addr)
        except Exception as exc:
            logger.warning("Order %s geocoding exception: %s — dropping", order.id, exc)
            return None

    with ThreadPoolExecutor(max_workers=min(10, len(orders))) as ex:
        geo_results = list(ex.map(_geocode_order, orders))

    dropped_orders = 0
    for order, coords in zip(orders, geo_results):
        if coords:
            order.lat, order.lng = coords
        else:
            logger.warning("Order %s dropped due to geocoding failure", order.id)
            dropped_orders += 1

    geocoded = [o for o in orders if o.lat is not None]
    if not geocoded:
        raise HTTPException(status_code=500, detail="No orders could be geocoded")

    if dropped_orders:
        logger.warning("%d order(s) dropped due to geocoding failures", dropped_orders)

    depot_lat, depot_lng = office_coords
    geocoded.sort(key=lambda o: math.atan2(o.lat - depot_lat, o.lng - depot_lng))

    # 3. Build matrices (called exactly once)
    _report_step("matrix")
    coords = [office_coords] + [(o.lat, o.lng) for o in geocoded]
    logger.info("Building OSRM matrix for %d coordinates", len(coords))
    try:
        time_matrix, distance_matrix = build_time_matrix(coords)
    except Exception as exc:
        logger.exception("Matrix build failed")
        raise HTTPException(status_code=500, detail=f"Matrix build failed: {exc}") from exc

    # 4. Time windows (apply buffer: shorten window end by time_buffer_min)
    time_windows: list[tuple[int, int]] = [(courier_start_min, MINUTES_PER_DAY)]
    for order in geocoded:
        tw_s = _parse_minutes(order.time_start)
        tw_e = _parse_minutes(order.time_end)
        if tw_s is not None and tw_e is not None and tw_s <= tw_e:
            tw_e_effective = tw_e - time_buffer_min
            if tw_e_effective <= tw_s:
                tw_e_effective = tw_e  # buffer too large — ignore it for this stop
            time_windows.append((tw_s, tw_e_effective))
        else:
            time_windows.append((0, MINUTES_PER_DAY))

    # 5. Feasibility check + auto num_couriers
    cap_required = capacity_minimum_couriers(len(geocoded), capacity) if capacity else 1
    tw_required = estimate_minimum_couriers(
        time_windows, time_matrix, SERVICE_TIME_PER_STOP, courier_start_min,
        max_route_duration_min=MAX_ROUTE_DURATION_MIN,
    )
    minimum_required = max(cap_required, tw_required)

    auto_couriers = num_couriers is None
    if auto_couriers:
        num_couriers = minimum_required
        logger.info(
            "Auto num_couriers = %d (cap=%d, tw_or_duration=%d)",
            num_couriers, cap_required, tw_required,
        )
    elif num_couriers < minimum_required:
        reason = "capacity_constraint" if cap_required >= tw_required else "time_window_constraint"
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
    _report_step("optimize")
    try:
        routes, solver_etas, dropped_nodes, solver_departures = solve_vrptw(
            time_matrix,
            time_windows,
            depot=0,
            courier_start_time=courier_start_min,
            service_time_per_stop=SERVICE_TIME_PER_STOP,
            num_couriers=num_couriers,
            capacity=capacity,
            initial_routes=initial_routes,
            distance_matrix=distance_matrix,
            max_wait_min=20,
            max_route_duration_min=MAX_ROUTE_DURATION_MIN,
        )
    except Exception as exc:
        logger.exception("Solver crashed")
        raise HTTPException(status_code=500, detail=f"Solver error: {exc}") from exc

    if all(len(r) == 0 for r in routes) and not dropped_nodes:
        raise HTTPException(status_code=500, detail="Solver found no feasible solution")

    # Dropped stops: each gets a dedicated solo courier (departs exactly when needed)
    for node in dropped_nodes:
        routes.append([node])
    if dropped_nodes:
        logger.info(
            "%d stop(s) could not be scheduled without >15 min wait → assigned as solo couriers",
            len(dropped_nodes),
        )

    # 8. Build response (geometry fetched in parallel after the main loop)
    _report_step("finalize")
    result_routes = []
    geo_coords_per_route: list[list[tuple[float, float]]] = []
    total_deliveries = 0
    total_drive_min = 0
    total_distance_km = 0.0

    for v, route_nodes in enumerate(routes):
        if not route_nodes:
            continue

        stops = []
        prev_node = 0

        # Use actual departure time from solver when available (v < num solver couriers).
        # Dropped solo couriers are appended after the solver routes, so derive their
        # departure from the time window of their single stop.
        if v < len(solver_departures):
            departure_min = solver_departures[v]
            v_etas = solver_etas[v]
        else:
            node = route_nodes[0]
            order = geocoded[node - 1]
            drive_from_depot = int(round(time_matrix[0][node] / 60))
            tw_s = _parse_minutes(order.time_start)
            eta_solo = max(courier_start_min + drive_from_depot, tw_s or 0)
            departure_min = eta_solo - drive_from_depot
            v_etas = [eta_solo]

        current_time = departure_min

        prev_chain = [0] + list(route_nodes)
        route_distance_m = sum(
            distance_matrix[prev_chain[i]][route_nodes[i]]
            for i in range(len(route_nodes))
        ) + distance_matrix[route_nodes[-1]][0]

        for idx, node in enumerate(route_nodes):
            order = geocoded[node - 1]
            drive_min = int(round(time_matrix[prev_node][node] / 60))

            # natural_arrival = departure from prev stop (after 15-min service) + drive time.
            # This is the minimum ETA that correctly accounts for service time at every stop.
            # The solver ETA (v_etas) is used as-is when it is >= natural_arrival
            # (e.g. courier waits for a time window to open).
            # If the solver ETA is earlier than natural_arrival it means OR-Tools did not
            # fully propagate the service-time transit for unconstrained stops — in that
            # case we fall back to natural_arrival so service time is never skipped.
            natural_arrival = current_time + drive_min
            tw_s = _parse_minutes(order.time_start)

            if idx < len(v_etas):
                eta_min = max(v_etas[idx], natural_arrival)
            else:
                eta_min = max(natural_arrival, tw_s) if tw_s else natural_arrival

            # If the time window hasn't opened yet, wait until it does.
            if tw_s and eta_min < tw_s:
                eta_min = tw_s

            arrival = natural_arrival
            wait_min = max(0, eta_min - arrival)

            stops.append({
                "address": f"{order.city}, {order.address} {order.house}",
                "eta": _fmt_time(eta_min),
                "driveMin": drive_min,
                "serviceMin": SERVICE_TIME_PER_STOP,
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

        suggested_departure = _fmt_time(departure_min)

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
            "suggestedDepartureTime": suggested_departure,
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
            "autoCouriers": auto_couriers,
            "serviceTimePerStop": SERVICE_TIME_PER_STOP,
            "timeBufferMin": time_buffer_min,
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

    # Build ONE matrix for all unique coords across all couriers (was N matrices).
    all_coords: list[tuple[float, float]] = [depot_coords]
    for route in body_routes:
        for s in route.stops:
            coord = (s.lat, s.lng)
            if coord not in all_coords:
                all_coords.append(coord)

    coord_to_idx = {c: i for i, c in enumerate(all_coords)}

    logger.info("Building single OSRM matrix for %d coordinates (all couriers)", len(all_coords))
    try:
        time_matrix, distance_matrix = build_time_matrix(all_coords)
    except Exception as exc:
        logger.exception("Matrix build failed")
        raise HTTPException(
            status_code=503,
            detail={"error": "OSRM_UNAVAILABLE", "message": f"OSRM matrix build failed: {exc}"},
        ) from exc

    geo_coords_per_route: list[list[tuple[float, float]]] = []

    for route in body_routes:
        if not route.stops:
            continue

        courier_stops = route.stops
        stops_out = []
        current_time = courier_start_min
        route_distance_m = 0.0
        prev_coord = depot_coords

        for stop in courier_stops:
            stop_coord = (stop.lat, stop.lng)
            from_idx = coord_to_idx[prev_coord]
            to_idx = coord_to_idx.get(stop_coord)

            if to_idx is None:
                logger.warning("Stop coord %s not found in matrix — skipping", stop_coord)
                continue

            drive_min = int(round(time_matrix[from_idx][to_idx] / 60))
            route_distance_m += distance_matrix[from_idx][to_idx]
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
                "serviceMin": SERVICE_TIME_PER_STOP,
                "waitMin": wait_min,
                "lat": stop.lat,
                "lng": stop.lng,
                "timeStart": stop.timeStart,
                "timeEnd": stop.timeEnd,
            })

            current_time = eta_min + SERVICE_TIME_PER_STOP
            prev_coord = stop_coord

        route_drive_min = sum(s["driveMin"] for s in stops_out)
        route_distance_km = route_distance_m / 1000

        geo_coords_per_route.append([depot_coords] + [(s.lat, s.lng) for s in courier_stops])

        result_routes.append({
            "courierId": route.courierId,
            "stops": stops_out,
            "totalDriveMin": route_drive_min,
            "totalDistanceKm": round(route_distance_km, 2),
            "geometry": None,  # filled below
        })

        total_deliveries += len(stops_out)
        total_drive_min += route_drive_min
        total_distance_km += route_distance_km

    # Fetch all geometries in parallel (was sequential per courier).
    if geo_coords_per_route:
        with ThreadPoolExecutor(max_workers=len(geo_coords_per_route)) as executor:
            geometries = list(executor.map(fetch_route_geometry, geo_coords_per_route))
        for i, geom in enumerate(geometries):
            result_routes[i]["geometry"] = geom

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
# Distribute helpers
# ---------------------------------------------------------------------------

def _check_insertion(
    stops: list,
    pos: int,
    new_coord: tuple[float, float],
    new_tw_s: int | None,
    new_tw_e: int | None,
    departure_min: int,
    depot_idx: int,
    coord_to_idx: dict,
    time_matrix: list,
    max_wait_min: int = 15,
) -> tuple[float, bool]:
    """
    Check feasibility of inserting a new stop at position `pos` in `stops`.

    Simulates the full ETA chain from departure through all stops (prefix + new + suffix),
    checking time-window-end violations and max_wait_min at every stop.

    Returns (extra_drive_cost_minutes, is_feasible).
    extra_drive_cost = time(prev→new) + time(new→next) - time(prev→next).
    """
    new_idx = coord_to_idx[new_coord]

    # Simulate prefix (stops 0..pos-1): check tw_e + wait for each
    current_time = departure_min
    prev_idx = depot_idx
    for i in range(pos):
        s = stops[i]
        s_idx = coord_to_idx[(s.lat, s.lng)]
        drive = int(round(time_matrix[prev_idx][s_idx] / 60))
        natural = current_time + drive
        tw_s = _parse_minutes(s.delivery_window_start)
        tw_e = _parse_minutes(s.delivery_window_end)
        eta = max(natural, tw_s) if tw_s else natural
        if tw_e is not None and eta > tw_e:
            return float("inf"), False
        if (eta - natural) > max_wait_min:
            return float("inf"), False
        current_time = eta + SERVICE_TIME_PER_STOP
        prev_idx = s_idx

    # Insertion cost = extra drive time added to route
    drive_to_new = int(round(time_matrix[prev_idx][new_idx] / 60))
    if pos < len(stops):
        nxt_idx = coord_to_idx[(stops[pos].lat, stops[pos].lng)]
        extra_cost = (
            drive_to_new
            + int(round(time_matrix[new_idx][nxt_idx] / 60))
            - int(round(time_matrix[prev_idx][nxt_idx] / 60))
        )
    else:
        extra_cost = drive_to_new

    # Check new stop's time window and wait
    natural_new = current_time + drive_to_new
    eta_new = max(natural_new, new_tw_s) if new_tw_s else natural_new
    if new_tw_e is not None and eta_new > new_tw_e:
        return float("inf"), False
    if (eta_new - natural_new) > max_wait_min:
        return float("inf"), False

    current_time = eta_new + SERVICE_TIME_PER_STOP
    prev_idx = new_idx

    # Check all remaining existing stops: tw_e + wait
    for s in stops[pos:]:
        s_idx = coord_to_idx[(s.lat, s.lng)]
        drive = int(round(time_matrix[prev_idx][s_idx] / 60))
        natural = current_time + drive
        tw_s = _parse_minutes(s.delivery_window_start)
        tw_e = _parse_minutes(s.delivery_window_end)
        eta = max(natural, tw_s) if tw_s else natural
        if tw_e is not None and eta > tw_e:
            return float("inf"), False
        if (eta - natural) > max_wait_min:
            return float("inf"), False
        current_time = eta + SERVICE_TIME_PER_STOP
        prev_idx = s_idx

    # Check total route duration
    if (current_time - departure_min) > MAX_ROUTE_DURATION_MIN + SERVICE_TIME_PER_STOP:
        return float("inf"), False

    return float(extra_cost), True


def _compute_adjusted_departure(
    stops: list,
    pos: int,
    new_coord: tuple[float, float],
    new_tw_s: int | None,
    new_tw_e: int | None,
    orig_dep_min: int,
    earliest_dep_min: int,
    depot_idx: int,
    coord_to_idx: dict,
    time_matrix: list,
    max_wait_min: int,
) -> tuple[int | None, float]:
    """
    Find the minimum departure time > orig_dep_min (and >= earliest_dep_min)
    that makes the insertion feasible given max_wait_min constraints.

    Strategy: compute pure travel time from depot to new stop (drive + service per prefix
    stop, no waits), then back-calculate the departure that puts the courier at the new
    stop exactly max_wait_min before new_tw_s opens.  Verify with full _check_insertion.

    Returns (adjusted_dep_min, extra_drive_cost) or (None, inf) if not possible.
    """
    if new_tw_s is None:
        return None, float("inf")  # no window start → no target to aim for

    new_idx = coord_to_idx[new_coord]

    # Pure travel time: sum of drives + service time at each prefix stop
    pure_time = 0
    prev_idx = depot_idx
    for i in range(pos):
        s = stops[i]
        s_idx = coord_to_idx[(s.lat, s.lng)]
        pure_time += int(round(time_matrix[prev_idx][s_idx] / 60)) + SERVICE_TIME_PER_STOP
        prev_idx = s_idx
    pure_time += int(round(time_matrix[prev_idx][new_idx] / 60))

    # Departure so courier arrives exactly (max_wait_min) before window opens
    dep_lo = new_tw_s - max_wait_min - pure_time
    candidate_dep = max(earliest_dep_min, dep_lo)

    # Only consider forward adjustments (later departure reduces wait)
    if candidate_dep <= orig_dep_min:
        return None, float("inf")

    cost, feasible = _check_insertion(
        stops, pos, new_coord, new_tw_s, new_tw_e,
        candidate_dep, depot_idx, coord_to_idx, time_matrix, max_wait_min,
    )
    if feasible:
        return candidate_dep, cost
    return None, float("inf")


def _distribute_sync(
    existing_routes: list,
    new_orders: list,
    depot_coords: tuple[float, float],
    time_buffer_min: int = 15,
    max_wait_min: int = 15,
    allow_departure_adjustment: bool = False,
    earliest_dep_min: int = 480,  # 08:00 default
) -> dict:
    """
    Blocking distribute pipeline:
    1. Geocode missing coords for existing stops and new orders.
    2. Build a single OSRM matrix covering all coords.
    3. For each new order (EDF order), find the cheapest feasible insertion
       across all existing routes (with optional departure adjustment).
       Unfit orders go to new routes solved by VRPTW.
    4. Recalculate all ETAs and fetch geometries.
    """
    t_start = time.monotonic()
    geocoder = GeocodingService()

    # --- 1. Geocode existing stops that lack coordinates ---
    stops_need_geocode = [
        s for route in existing_routes for s in route.stops
        if s.lat is None or s.lng is None
    ]
    if stops_need_geocode:
        def _geocode_exist(stop):
            addr = f"{stop.city}, {stop.address} {stop.house}, Ukraine"
            try:
                return stop, geocoder.geocode(addr)
            except Exception as exc:
                logger.warning("Existing stop %s geocoding error: %s", stop.id, exc)
                return stop, None

        with ThreadPoolExecutor(max_workers=min(10, len(stops_need_geocode))) as ex:
            for stop, coords in ex.map(_geocode_exist, stops_need_geocode):
                if coords:
                    stop.lat, stop.lng = coords
                else:
                    raise HTTPException(
                        status_code=422,
                        detail={
                            "error": "GEOCODING_FAILED",
                            "message": (
                                f"Cannot geocode existing stop id={stop.id}: "
                                f"{stop.city}, {stop.address} {stop.house}"
                            ),
                        },
                    )

    # --- 2. Geocode new orders ---
    order_coords: dict = {}  # order_key -> (lat, lng)

    def _order_key(o, idx: int):
        return o.id if o.id is not None else f"__new_{idx}"

    def _geocode_new(args):
        idx, order = args
        addr = f"{order.city}, {order.address} {order.house}, Ukraine"
        try:
            return _order_key(order, idx), geocoder.geocode(addr)
        except Exception as exc:
            logger.warning("New order %s geocoding error: %s", _order_key(order, idx), exc)
            return _order_key(order, idx), None

    if new_orders:
        with ThreadPoolExecutor(max_workers=min(10, len(new_orders))) as ex:
            for key, coords in ex.map(_geocode_new, enumerate(new_orders)):
                if coords:
                    order_coords[key] = coords
                else:
                    logger.warning("New order %s could not be geocoded — will be unassigned", key)

    # --- 3. Build unified OSRM matrix ---
    all_coords: list[tuple[float, float]] = [depot_coords]
    for route in existing_routes:
        for s in route.stops:
            c = (s.lat, s.lng)
            if c not in all_coords:
                all_coords.append(c)
    for idx, order in enumerate(new_orders):
        key = _order_key(order, idx)
        if key in order_coords:
            c = order_coords[key]
            if c not in all_coords:
                all_coords.append(c)

    coord_to_idx = {c: i for i, c in enumerate(all_coords)}
    depot_idx = coord_to_idx[depot_coords]

    logger.info("Building OSRM matrix for %d coordinates (distribute)", len(all_coords))
    try:
        time_matrix, distance_matrix = build_time_matrix(all_coords)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Matrix build failed: {exc}") from exc

    # --- 4. Cheapest feasible insertion (Earliest Deadline First) ---
    def _urgency(args):
        _, o = args
        tw_e = _parse_minutes(o.delivery_window_end)
        return tw_e if tw_e is not None else MINUTES_PER_DAY

    sorted_orders = sorted(enumerate(new_orders), key=_urgency)

    # Mutable per-route stop lists (shallow copies; inserting new DistributeStop objects)
    route_stop_lists: list[list] = [list(route.stops) for route in existing_routes]
    # Effective departure per route — may be shifted forward by departure adjustment
    route_effective_dep: list[int] = [
        _parse_minutes(r.departureTime) or 540 for r in existing_routes
    ]
    route_departure_adjusted: list[bool] = [False] * len(existing_routes)
    unassigned: list[tuple[int, object]] = []  # (original_idx, order)

    # Penalty per minute of departure delay (used to compare adjusted vs non-adjusted)
    _DEP_DELAY_PENALTY = 1.0

    for orig_idx, order in sorted_orders:
        key = _order_key(order, orig_idx)
        if key not in order_coords:
            unassigned.append((orig_idx, order))
            continue

        new_coord = order_coords[key]
        new_tw_s = _parse_minutes(order.delivery_window_start)
        new_tw_e = _parse_minutes(order.delivery_window_end)
        effective_tw_e = (
            max(new_tw_s or 0, new_tw_e - time_buffer_min)
            if new_tw_e is not None else None
        )

        # best = (penalized_cost, r_idx, pos, dep_min, is_adjusted)
        best: tuple = (float("inf"), None, None, None, False)

        for r_idx, (route, stops) in enumerate(zip(existing_routes, route_stop_lists)):
            dep_min = route_effective_dep[r_idx]

            for pos in range(len(stops) + 1):
                # --- Try with current effective departure ---
                cost, feasible = _check_insertion(
                    stops, pos, new_coord, new_tw_s, effective_tw_e,
                    dep_min, depot_idx, coord_to_idx, time_matrix, max_wait_min,
                )
                if feasible and cost < best[0]:
                    best = (cost, r_idx, pos, dep_min, False)

                # --- Try departure adjustment if enabled and not yet feasible ---
                if not feasible and allow_departure_adjustment:
                    adj_dep, adj_cost = _compute_adjusted_departure(
                        stops, pos, new_coord, new_tw_s, effective_tw_e,
                        dep_min, earliest_dep_min,
                        depot_idx, coord_to_idx, time_matrix, max_wait_min,
                    )
                    if adj_dep is not None:
                        penalized = adj_cost + _DEP_DELAY_PENALTY * (adj_dep - dep_min)
                        if penalized < best[0]:
                            best = (penalized, r_idx, pos, adj_dep, True)

        penalized_cost, best_route_idx, best_pos, best_dep, is_adjusted = best

        if best_route_idx is not None:
            new_stop = DistributeStop(
                id=order.id,
                city=order.city,
                address=order.address,
                house=order.house,
                delivery_window_start=order.delivery_window_start,
                delivery_window_end=order.delivery_window_end,
                lat=new_coord[0],
                lng=new_coord[1],
            )
            route_stop_lists[best_route_idx].insert(best_pos, new_stop)
            if is_adjusted:
                route_effective_dep[best_route_idx] = max(
                    route_effective_dep[best_route_idx], best_dep
                )
                route_departure_adjusted[best_route_idx] = True
            logger.info(
                "Order %s → route %s pos %d (cost +%d min%s)",
                key, existing_routes[best_route_idx].courierId, best_pos,
                int(penalized_cost),
                f", dep adjusted to {_fmt_time(best_dep)}" if is_adjusted else "",
            )
        else:
            unassigned.append((orig_idx, order))
            logger.info("Order %s → unassigned (no feasible slot found)", key)

    # --- 5. Recalculate ETAs for all (possibly modified) existing routes ---
    result_routes: list[dict] = []
    geo_coords_per_route: list[list[tuple[float, float]]] = []

    for r_idx, (route, stops) in enumerate(zip(existing_routes, route_stop_lists)):
        dep_min = route_effective_dep[r_idx]
        stops_out = []
        current_time = dep_min
        prev_idx = depot_idx
        total_drive_min = 0
        total_dist_m = 0.0

        for i, s in enumerate(stops):
            s_idx = coord_to_idx[(s.lat, s.lng)]
            drive_min = int(round(time_matrix[prev_idx][s_idx] / 60))
            dist_m = distance_matrix[prev_idx][s_idx]
            natural = current_time + drive_min
            tw_s = _parse_minutes(s.delivery_window_start)
            eta = max(natural, tw_s) if tw_s else natural
            wait_min = max(0, eta - natural)

            stops_out.append({
                "id": s.id,
                "stopOrder": i + 1,
                "address": f"{s.city}, {s.address} {s.house}",
                "eta": _fmt_time(eta),
                "driveMin": drive_min,
                "serviceMin": SERVICE_TIME_PER_STOP,
                "waitMin": wait_min,
                "lat": s.lat,
                "lng": s.lng,
                "delivery_window_start": s.delivery_window_start,
                "delivery_window_end": s.delivery_window_end,
            })

            current_time = eta + SERVICE_TIME_PER_STOP
            prev_idx = s_idx
            total_drive_min += drive_min
            total_dist_m += dist_m

        geo_coords_per_route.append(
            [depot_coords] + [(s.lat, s.lng) for s in stops] if stops else []
        )
        result_routes.append({
            "courierId": route.courierId,
            "routeDbId": route.routeDbId,
            "departureTime": _fmt_time(dep_min),
            "departureAdjusted": route_departure_adjusted[r_idx],
            "stops": stops_out,
            "totalDriveMin": total_drive_min,
            "totalDistanceKm": round(total_dist_m / 1000, 2),
            "geometry": None,
        })

    # --- 6. Solve new routes for unassigned orders via VRPTW ---
    if unassigned:
        valid_unassigned = [
            (orig_idx, o) for orig_idx, o in unassigned
            if _order_key(o, orig_idx) in order_coords
        ]
        if valid_unassigned:
            ua_orders = [o for _, o in valid_unassigned]
            ua_orig_idxs = [i for i, _ in valid_unassigned]
            ua_coords = [order_coords[_order_key(o, i)] for i, o in valid_unassigned]

            sub_coords = [depot_coords] + ua_coords
            sub_idxs = [coord_to_idx[c] for c in sub_coords]
            n_sub = len(sub_coords)
            sub_time = [
                [time_matrix[sub_idxs[i]][sub_idxs[j]] for j in range(n_sub)]
                for i in range(n_sub)
            ]
            sub_dist = [
                [distance_matrix[sub_idxs[i]][sub_idxs[j]] for j in range(n_sub)]
                for i in range(n_sub)
            ]

            existing_dep_mins = [
                _parse_minutes(r.departureTime) for r in existing_routes if r.stops
            ]
            new_courier_start = min(
                (d for d in existing_dep_mins if d is not None), default=540
            )

            sub_time_windows: list[tuple[int, int]] = [(new_courier_start, MINUTES_PER_DAY)]
            for o in ua_orders:
                tw_s = _parse_minutes(o.delivery_window_start)
                tw_e = _parse_minutes(o.delivery_window_end)
                if tw_s is not None and tw_e is not None:
                    sub_time_windows.append((tw_s, max(tw_s, tw_e - time_buffer_min)))
                else:
                    sub_time_windows.append((0, MINUTES_PER_DAY))

            num_new = max(
                1,
                estimate_minimum_couriers(
                    sub_time_windows, sub_time, SERVICE_TIME_PER_STOP,
                    new_courier_start, max_route_duration_min=MAX_ROUTE_DURATION_MIN,
                ),
            )
            logger.info("Solving %d unassigned orders with %d new courier(s)", len(ua_orders), num_new)

            try:
                new_vrp_routes, new_etas, new_dropped, new_departures = solve_vrptw(
                    sub_time, sub_time_windows, depot=0,
                    courier_start_time=new_courier_start,
                    service_time_per_stop=SERVICE_TIME_PER_STOP,
                    num_couriers=num_new,
                    capacity=None,
                    initial_routes=None,
                    distance_matrix=sub_dist,
                    max_wait_min=20,
                    max_route_duration_min=MAX_ROUTE_DURATION_MIN,
                )
            except Exception as exc:
                logger.exception("Solver failed for unassigned orders")
                raise HTTPException(status_code=500, detail=f"New route solver error: {exc}") from exc

            for node in new_dropped:
                new_vrp_routes.append([node])

            for v, route_nodes in enumerate(new_vrp_routes):
                if not route_nodes:
                    continue

                dep_min = new_departures[v] if v < len(new_departures) else new_courier_start
                v_etas = new_etas[v] if v < len(new_etas) else []

                stops_out = []
                current_time = dep_min
                prev_sub_idx = 0
                total_drive = 0
                total_dist = 0.0

                for idx, node in enumerate(route_nodes):
                    order = ua_orders[node - 1]
                    o_coord = ua_coords[node - 1]

                    drive_min = int(round(sub_time[prev_sub_idx][node] / 60))
                    dist_m = sub_dist[prev_sub_idx][node]
                    natural = current_time + drive_min
                    tw_s = _parse_minutes(order.delivery_window_start)
                    solver_eta = v_etas[idx] if idx < len(v_etas) else None
                    eta_min = max(solver_eta, natural) if solver_eta is not None else natural
                    if tw_s and eta_min < tw_s:
                        eta_min = tw_s
                    wait_min = max(0, eta_min - natural)

                    stops_out.append({
                        "id": order.id,
                        "stopOrder": idx + 1,
                        "address": f"{order.city}, {order.address} {order.house}",
                        "eta": _fmt_time(eta_min),
                        "driveMin": drive_min,
                        "serviceMin": SERVICE_TIME_PER_STOP,
                        "waitMin": wait_min,
                        "lat": o_coord[0],
                        "lng": o_coord[1],
                        "delivery_window_start": order.delivery_window_start,
                        "delivery_window_end": order.delivery_window_end,
                    })

                    current_time = eta_min + SERVICE_TIME_PER_STOP
                    prev_sub_idx = node
                    total_drive += drive_min
                    total_dist += dist_m

                if stops_out:
                    geo_coords_per_route.append(
                        [depot_coords] + [ua_coords[n - 1] for n in route_nodes]
                    )
                    result_routes.append({
                        "courierId": None,
                        "routeDbId": None,
                        "departureTime": _fmt_time(dep_min),
                        "stops": stops_out,
                        "totalDriveMin": total_drive,
                        "totalDistanceKm": round(total_dist / 1000, 2),
                        "geometry": None,
                    })

    # --- 7. Fetch geometries in parallel ---
    non_empty_geo = [(i, c) for i, c in enumerate(geo_coords_per_route) if len(c) >= 2]
    if non_empty_geo:
        idxs, coord_lists = zip(*non_empty_geo)
        with ThreadPoolExecutor(max_workers=len(coord_lists)) as executor:
            geometries = list(executor.map(fetch_route_geometry, coord_lists))
        for i, geom in zip(idxs, geometries):
            result_routes[i]["geometry"] = geom

    elapsed = time.monotonic() - t_start
    total_deliveries = sum(len(r["stops"]) for r in result_routes)
    total_drive_min = sum(r["totalDriveMin"] for r in result_routes)
    total_dist_km = round(sum(r["totalDistanceKm"] for r in result_routes), 2)
    logger.info(
        "Distribute finished in %.2fs — %d routes, %d deliveries, %d unassigned",
        elapsed, len(result_routes), total_deliveries, len(unassigned),
    )

    return {
        "routes": result_routes,
        "stats": {
            "totalDeliveries": total_deliveries,
            "numCouriers": len(result_routes),
            "totalDistanceKm": total_dist_km,
            "totalDriveMin": total_drive_min,
        },
    }


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="Kvitkova Povnya Route Optimizer")

# CORS: comma-separated list of allowed origins, or "*" to allow all.
# Example: ALLOWED_ORIGINS=https://mycrm.com,https://app.mycrm.com
_raw_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000")
_allow_origins = [o.strip() for o in _raw_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allow_origins,
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

# Optional API key auth. Set API_KEY env var to enable; if empty — auth is disabled.
_API_KEY = os.getenv("API_KEY", "")


def _check_api_key(x_api_key: str | None) -> None:
    if _API_KEY and x_api_key != _API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal server error: {exc}"},
    )


class OrderInput(BaseModel):
    """A single delivery order for the JSON optimize endpoint."""
    id: int | None = None
    city: str
    address: str
    house: str
    delivery_window_start: str | None = None
    delivery_window_end: str | None = None


class OptimizeJsonRequest(BaseModel):
    orders: list[OrderInput]
    start_time: str = "09:00"
    num_couriers: int | None = None   # None = auto-calculate minimum required
    capacity: int | None = None
    time_buffer_min: int = 15         # minutes of buffer before window end (default 15)


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
    startTime: str = "09:00"


class DistributeStop(BaseModel):
    id: int | str | None = None
    stopOrder: int | None = None
    city: str
    address: str
    house: str
    eta: str | None = None
    delivery_window_start: str | None = None
    delivery_window_end: str | None = None
    lat: float | None = None   # optional — geocoded if missing
    lng: float | None = None


class DistributeRoute(BaseModel):
    courierId: str | int
    routeDbId: int | None = None
    departureTime: str = "09:00"
    stops: list[DistributeStop]


class DistributeRequest(BaseModel):
    existing_routes: list[DistributeRoute]
    new_orders: list[OrderInput]
    time_buffer_min: int = 15
    max_wait_min: int = 15
    allow_departure_adjustment: bool = False
    earliest_departure: str = "08:00"


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/optimize")
async def optimize(
    file: UploadFile = File(...),
    start_time: str = Form("09:00"),
    num_couriers: int | None = Form(None),
    capacity: int | None = Form(None),
    time_buffer_min: int = Form(15),
):
    raw = await file.read()

    if _rq_queue is not None:
        # Async path: enqueue job and return jobId immediately.
        job = _rq_queue.enqueue(
            _optimize_sync,
            raw, start_time, num_couriers, capacity, time_buffer_min,
            job_timeout=600,
            result_ttl=3600,
        )
        return {"jobId": job.id, "status": "pending"}

    # Sync fallback when Redis/RQ unavailable (local dev without Docker).
    try:
        result = await asyncio.to_thread(_optimize_sync, raw, start_time, num_couriers, capacity, time_buffer_min)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unexpected error in optimization thread")
        raise HTTPException(status_code=500, detail=f"Internal error: {exc}") from exc

    if result.get("__infeasible__"):
        return JSONResponse(status_code=422, content={k: v for k, v in result.items() if k != "__infeasible__"})

    # Wrap as a "done" job response so the frontend polling logic still works.
    return {"jobId": "sync", "status": "done", "result": result}


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str):
    if _rq_redis is None:
        raise HTTPException(status_code=503, detail="Job queue unavailable")

    try:
        job = _Job.fetch(job_id, connection=_rq_redis)
    except _NoSuchJobError:
        raise HTTPException(status_code=404, detail="Job not found")

    status = job.get_status()
    status_str = status.value if hasattr(status, "value") else str(status)

    if status_str == "finished":
        result = job.result
        if isinstance(result, dict) and result.get("__infeasible__"):
            return JSONResponse(
                status_code=422,
                content={k: v for k, v in result.items() if k != "__infeasible__"},
            )
        return {"status": "done", "result": result}

    if status_str == "failed":
        return JSONResponse(
            status_code=500,
            content={"status": "failed", "error": str(job.exc_info)},
        )

    step = job.meta.get("currentStep") if job.meta else None
    return {
        "status": "running" if status_str == "started" else "pending",
        "progress": {"currentStep": step} if step else None,
    }


@app.post("/api/optimize/json")
async def optimize_json(
    body: OptimizeJsonRequest,
    x_api_key: str | None = Header(default=None),
):
    """
    JSON alternative to POST /api/optimize.
    Accepts orders as a JSON array instead of a CSV file upload.
    Suitable for CRM / server-to-server integrations.
    """
    _check_api_key(x_api_key)

    if not body.orders:
        raise HTTPException(status_code=400, detail="No orders provided")

    # Convert OrderInput list → CSV bytes so the existing pipeline can process it
    buf = io.StringIO()
    writer = _csv.DictWriter(
        buf,
        fieldnames=["id", "city", "address", "house", "delivery_window_start", "delivery_window_end"],
    )
    writer.writeheader()
    for idx, o in enumerate(body.orders, start=1):
        writer.writerow({
            "id": o.id if o.id is not None else idx,
            "city": o.city,
            "address": o.address,
            "house": o.house,
            "delivery_window_start": o.delivery_window_start or "",
            "delivery_window_end": o.delivery_window_end or "",
        })
    raw = buf.getvalue().encode("utf-8")

    try:
        result = await asyncio.to_thread(
            _optimize_sync, raw, body.start_time, body.num_couriers, body.capacity, body.time_buffer_min
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unexpected error in optimization thread")
        raise HTTPException(status_code=500, detail=f"Internal error: {exc}") from exc

    if result.get("__infeasible__"):
        return JSONResponse(status_code=422, content={k: v for k, v in result.items() if k != "__infeasible__"})

    return result



@app.post("/api/recalculate")
async def recalculate_routes(
    body: RecalculateRequest,
    x_api_key: str | None = Header(default=None),
):
    _check_api_key(x_api_key)

    if not body.routes or all(len(r.stops) == 0 for r in body.routes):
        raise HTTPException(
            status_code=422,
            detail={"error": "INVALID_INPUT", "message": "routes array is empty or has no stops"},
        )

    courier_start_min = _parse_minutes(body.startTime)
    if courier_start_min is None:
        raise HTTPException(
            status_code=422,
            detail={"error": "INVALID_INPUT", "message": f"Invalid startTime: {body.startTime!r}"},
        )

    # Validate stops and drop those with missing coordinates
    for route in body.routes:
        invalid = [s for s in route.stops if s.lat is None or s.lng is None]
        if invalid:
            raise HTTPException(
                status_code=422,
                detail={"error": "INVALID_INPUT", "message": f"Courier {route.courierId}: {len(invalid)} stop(s) missing lat/lng"},
            )

    geocoder = GeocodingService()
    try:
        depot_coords = geocoder.geocode(DEPOT_ADDRESS, city="Kyiv", country="UA")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Geocoding error: {exc}") from exc
    if not depot_coords:
        raise HTTPException(status_code=500, detail=f"Could not geocode depot: {DEPOT_ADDRESS}")

    try:
        result = await asyncio.to_thread(
            _recalculate_sync, body.routes, depot_coords, courier_start_min
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unexpected error in recalculate thread")
        raise HTTPException(status_code=500, detail=f"Internal error: {exc}") from exc

    return result


@app.post("/api/distribute")
async def distribute_orders(
    body: DistributeRequest,
    x_api_key: str | None = Header(default=None),
):
    """
    Insert new deliveries into existing fixed routes.

    Existing stop order is immutable — only insertions between/after existing stops.
    Each new order is placed using cheapest-insertion heuristic (EDF priority).
    Orders that cannot fit any existing route are assigned to new routes via VRPTW.
    All ETAs are recalculated using real OSRM travel times.
    """
    _check_api_key(x_api_key)

    if not body.existing_routes:
        raise HTTPException(
            status_code=422,
            detail={"error": "INVALID_INPUT", "message": "existing_routes cannot be empty"},
        )
    if not body.new_orders:
        raise HTTPException(
            status_code=422,
            detail={"error": "INVALID_INPUT", "message": "new_orders cannot be empty"},
        )

    geocoder = GeocodingService()
    try:
        depot_coords = geocoder.geocode(DEPOT_ADDRESS, city="Kyiv", country="UA")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Geocoding error: {exc}") from exc
    if not depot_coords:
        raise HTTPException(status_code=500, detail=f"Could not geocode depot: {DEPOT_ADDRESS}")

    earliest_dep_min = _parse_minutes(body.earliest_departure)
    if earliest_dep_min is None:
        raise HTTPException(
            status_code=422,
            detail={"error": "INVALID_INPUT", "message": f"Invalid earliest_departure: {body.earliest_departure!r}"},
        )

    try:
        result = await asyncio.to_thread(
            _distribute_sync,
            body.existing_routes,
            body.new_orders,
            depot_coords,
            body.time_buffer_min,
            body.max_wait_min,
            body.allow_departure_adjustment,
            earliest_dep_min,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unexpected error in distribute thread")
        raise HTTPException(status_code=500, detail=f"Internal error: {exc}") from exc

    return result
