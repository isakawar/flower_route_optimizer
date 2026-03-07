"""Vehicle Routing Problem with Time Windows solver using Google OR-Tools."""

import logging

from ortools.constraint_solver import pywrapcp
from ortools.constraint_solver import routing_enums_pb2

logger = logging.getLogger(__name__)
MINUTES_PER_DAY = 24 * 60


def solve_vrptw(
    time_matrix: list[list[float]],
    time_windows: list[tuple[int, int]],
    depot: int = 0,
    courier_start_time: int = 480,
    service_time_per_stop: int = 3,
    num_couriers: int = 1,
    capacity: int | None = None,
) -> tuple[list[list[int]], list[list[int]]]:
    """
    Solve VRPTW: one or more couriers, all starting at depot at courier_start_time.

    Args:
        time_matrix: Square matrix of travel times in seconds (from OSRM).
                     Index 0 = depot.
        time_windows: For each location i, (earliest, latest) in minutes since midnight.
                      Use (0, MINUTES_PER_DAY) for no constraint.
        depot: Index of depot (must be 0).
        courier_start_time: Shift start in minutes since midnight (e.g. 600 = 10:00).
        service_time_per_stop: Fixed service duration in minutes per delivery stop.
        num_couriers: Number of vehicles / couriers.
        capacity: Max packages per courier. None means unlimited.

    Returns:
        (routes, etas): routes[v] = ordered node indices for courier v (depot excluded);
                        etas[v]   = arrival times in minutes since midnight per stop.
        ([[], ...], [[], ...]) if no feasible solution found.
    """
    if not time_matrix or not time_windows:
        logger.warning("VRPTW: empty input")
        return [[] for _ in range(num_couriers)], [[] for _ in range(num_couriers)]

    num_locations = len(time_matrix)
    if len(time_windows) != num_locations:
        raise ValueError("time_windows length must match time_matrix")
    if depot != 0:
        raise ValueError("Depot must be node 0")
    if num_couriers < 1:
        raise ValueError("num_couriers must be >= 1")

    # Allow waiting up to 4 hours at any stop
    slack_max = 4 * 60

    def travel_minutes(i: int, j: int) -> int:
        return int(round(time_matrix[i][j] / 60))

    def service_minutes(node: int) -> int:
        return 0 if node == depot else service_time_per_stop

    # All vehicles share the same depot (node 0), start and end there.
    manager = pywrapcp.RoutingIndexManager(num_locations, num_couriers, depot)
    routing = pywrapcp.RoutingModel(manager)

    # --- Time callback: service at origin + travel to destination ---
    def time_callback(from_index: int, to_index: int) -> int:
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return service_minutes(from_node) + travel_minutes(from_node, to_node)

    transit_callback_index = routing.RegisterTransitCallback(time_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

    # --- Time dimension ---
    routing.AddDimension(
        transit_callback_index,
        slack_max,
        MINUTES_PER_DAY,
        False,  # do not force start cumul to zero
        "Time",
    )
    time_dimension = routing.GetDimensionOrDie("Time")

    # Fix every courier's departure from depot to exactly courier_start_time
    for v in range(num_couriers):
        start_index = routing.Start(v)
        time_dimension.CumulVar(start_index).SetRange(
            courier_start_time, courier_start_time
        )

    # Apply time windows to delivery stops (shared across all couriers)
    for location_idx in range(num_locations):
        if location_idx == depot:
            continue
        tw_min, tw_max = time_windows[location_idx]
        index = manager.NodeToIndex(location_idx)
        time_dimension.CumulVar(index).SetRange(tw_min, tw_max)

    # Penalise waiting: span cost adds 1 unit/minute of waiting to the objective.
    # Span = travel + service + wait; arc cost already covers travel + service,
    # so the net effect is penalising idle time at each stop.
    time_dimension.SetSpanCostCoefficientForAllVehicles(1)

    # Finaliser: minimise return-to-depot time for each courier (tie-breaker)
    for v in range(num_couriers):
        routing.AddVariableMinimizedByFinalizer(
            time_dimension.CumulVar(routing.End(v))
        )

    # --- Capacity dimension (optional) ---
    if capacity is not None:
        # Depot has demand 0; every delivery stop has demand 1 (one package).
        demands = [0] + [1] * (num_locations - 1)

        def demand_callback(from_index: int) -> int:
            return demands[manager.IndexToNode(from_index)]

        demand_callback_index = routing.RegisterUnaryTransitCallback(demand_callback)
        routing.AddDimensionWithVehicleCapacity(
            demand_callback_index,
            0,                              # no slack on capacity
            [capacity] * num_couriers,      # same limit for every courier
            True,                           # start cumul at zero
            "Capacity",
        )

    # --- Search parameters ---
    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    )
    search_parameters.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )
    search_parameters.time_limit.seconds = 15  # extra time for multi-vehicle search

    logger.info(
        "VRPTW solver: %d locations, %d couriers, depot=%d, start=%02d:%02d, "
        "service=%dmin, capacity=%s",
        num_locations,
        num_couriers,
        depot,
        courier_start_time // 60,
        courier_start_time % 60,
        service_time_per_stop,
        str(capacity) if capacity is not None else "unlimited",
    )

    solution = routing.SolveWithParameters(search_parameters)
    if not solution:
        logger.error("VRPTW: no feasible solution found")
        return [[] for _ in range(num_couriers)], [[] for _ in range(num_couriers)]

    routes: list[list[int]] = []
    etas: list[list[int]] = []

    for v in range(num_couriers):
        v_route: list[int] = []
        v_etas: list[int] = []
        index = routing.Start(v)
        while not routing.IsEnd(index):
            node = manager.IndexToNode(index)
            if node != depot:
                v_route.append(node)
                v_etas.append(solution.Min(time_dimension.CumulVar(index)))
            index = solution.Value(routing.NextVar(index))
        routes.append(v_route)
        etas.append(v_etas)
        logger.info("VRPTW: courier %d — %d stops", v + 1, len(v_route))

    return routes, etas
