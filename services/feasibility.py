"""Pre-solve feasibility analysis for VRPTW."""

import logging
import math

logger = logging.getLogger(__name__)

MINUTES_PER_DAY = 24 * 60


def capacity_minimum_couriers(total_orders: int, capacity: int) -> int:
    """Minimum couriers needed purely to satisfy the per-courier capacity limit."""
    if capacity <= 0:
        return 1
    return math.ceil(total_orders / capacity)


def estimate_minimum_couriers(
    time_windows: list[tuple[int, int]],
    time_matrix: list[list[float]],
    service_time: int,
    courier_start: int,
    depot_idx: int = 0,
    max_route_duration_min: int | None = None,
) -> int:
    """
    Greedy Earliest-Deadline-First estimate of the minimum couriers required
    to satisfy all time windows and (optionally) a maximum route duration.

    When max_route_duration_min is set, courier state also tracks elapsed time
    (travel + wait + service since depot departure) so that no route exceeds
    the cap. Unconstrained stops are also assigned greedily to fill remaining
    capacity. This means clustered stops (short inter-stop travel) need fewer
    couriers than a global-average formula would predict.

    Returns at least 1.
    """
    constrained = [
        (i, tw_s, tw_e)
        for i, (tw_s, tw_e) in enumerate(time_windows)
        if i != depot_idx and not (tw_s == 0 and tw_e == MINUTES_PER_DAY)
    ]
    unconstrained = [
        i for i, (tw_s, tw_e) in enumerate(time_windows)
        if i != depot_idx and tw_s == 0 and tw_e == MINUTES_PER_DAY
    ]

    if not constrained and (not unconstrained or max_route_duration_min is None):
        return 1  # no real constraints

    # EDF: tightest deadline first; break ties by tightest window
    constrained.sort(key=lambda x: (x[2], x[2] - x[1]))

    # Courier state: (current_node, current_time, elapsed_min)
    # elapsed_min = time spent since leaving depot (travel + wait + service)
    couriers: list[tuple[int, int, int]] = []

    for node, tw_start, tw_end in constrained:
        best_idx = -1
        best_arrival = MINUTES_PER_DAY + 1

        for i, (cur_node, cur_time, elapsed) in enumerate(couriers):
            travel_min = int(round(time_matrix[cur_node][node] / 60))
            arrival = cur_time + travel_min
            if arrival > tw_end:
                continue
            actual_arrival = max(arrival, tw_start)
            projected_elapsed = elapsed + (actual_arrival - cur_time) + service_time
            if max_route_duration_min and projected_elapsed > max_route_duration_min:
                continue
            if arrival < best_arrival:
                best_idx = i
                best_arrival = arrival

        if best_idx >= 0:
            cur_node, cur_time, elapsed = couriers[best_idx]
            travel_min = int(round(time_matrix[cur_node][node] / 60))
            actual_arrival = max(cur_time + travel_min, tw_start)
            new_elapsed = elapsed + (actual_arrival - cur_time) + service_time
            couriers[best_idx] = (node, actual_arrival + service_time, new_elapsed)
        else:
            travel_min = int(round(time_matrix[depot_idx][node] / 60))
            arrival_from_depot = courier_start + travel_min
            actual_arrival = max(arrival_from_depot, tw_start)
            elapsed = (actual_arrival - courier_start) + service_time
            couriers.append((node, actual_arrival + service_time, elapsed))

    # Assign unconstrained stops greedily by remaining duration capacity
    if max_route_duration_min is not None:
        for node in unconstrained:
            best_idx, best_remaining = -1, -1
            for i, (cur_node, cur_time, elapsed) in enumerate(couriers):
                travel_min = int(round(time_matrix[cur_node][node] / 60))
                new_elapsed = elapsed + travel_min + service_time
                remaining = max_route_duration_min - new_elapsed
                if remaining >= 0 and remaining > best_remaining:
                    best_idx, best_remaining = i, remaining
            if best_idx >= 0:
                cur_node, cur_time, elapsed = couriers[best_idx]
                travel_min = int(round(time_matrix[cur_node][node] / 60))
                couriers[best_idx] = (
                    node,
                    cur_time + travel_min + service_time,
                    elapsed + travel_min + service_time,
                )
            else:
                travel_min = int(round(time_matrix[depot_idx][node] / 60))
                couriers.append((
                    node,
                    courier_start + travel_min + service_time,
                    travel_min + service_time,
                ))

    estimated = max(1, len(couriers))
    logger.info("Feasibility check: estimated minimum couriers = %d", estimated)
    return estimated
