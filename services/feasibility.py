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
) -> int:
    """
    Greedy Earliest-Deadline-First estimate of the minimum couriers required
    to satisfy all time windows.

    Algorithm:
    1. Collect stops that have real time windows (not unconstrained 0–1440).
    2. Sort by deadline (earliest deadline first) — most urgent stops first.
    3. For each stop, try to assign it to the courier that can arrive earliest
       while still making the deadline.
    4. If no existing courier can make the deadline, open a new one.

    Returns at least 1.
    """
    constrained = [
        (i, tw_s, tw_e)
        for i, (tw_s, tw_e) in enumerate(time_windows)
        if i != depot_idx and not (tw_s == 0 and tw_e == MINUTES_PER_DAY)
    ]

    if not constrained:
        return 1  # no real constraints — any courier count is feasible

    # EDF: tightest deadline first; break ties by latest start (tightest window)
    constrained.sort(key=lambda x: (x[2], x[2] - x[1]))

    # Each courier tracked as (current_node_idx, current_time_min)
    couriers: list[tuple[int, int]] = []

    for node, tw_start, tw_end in constrained:
        # Find the existing courier that arrives earliest at this node
        # and can still make the deadline
        best_idx = -1
        best_arrival = MINUTES_PER_DAY + 1

        for i, (cur_node, cur_time) in enumerate(couriers):
            travel_min = int(round(time_matrix[cur_node][node] / 60))
            arrival = cur_time + travel_min
            if arrival <= tw_end and arrival < best_arrival:
                best_idx = i
                best_arrival = arrival

        if best_idx >= 0:
            actual_arrival = max(best_arrival, tw_start)
            couriers[best_idx] = (node, actual_arrival + service_time)
        else:
            # Need a new courier dispatched from depot
            travel_min = int(round(time_matrix[depot_idx][node] / 60))
            arrival_from_depot = courier_start + travel_min
            actual_arrival = max(arrival_from_depot, tw_start)
            couriers.append((node, actual_arrival + service_time))

    estimated = max(1, len(couriers))
    logger.info("Feasibility check: estimated minimum couriers = %d", estimated)
    return estimated
