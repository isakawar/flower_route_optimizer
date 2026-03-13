"""Vehicle Routing Problem with Time Windows solver using Google OR-Tools."""

import logging

from ortools.constraint_solver import pywrapcp
from ortools.constraint_solver import routing_enums_pb2

logger = logging.getLogger(__name__)
MINUTES_PER_DAY = 24 * 60


def _log_matrix_stats(
    time_matrix: list[list[float]],
    distance_matrix: list[list[float]] | None,
) -> None:
    n = len(time_matrix)
    if n == 0:
        return
    # Sample: fastest and slowest non-zero off-diagonal travel times
    times = [
        time_matrix[i][j]
        for i in range(n)
        for j in range(n)
        if i != j and time_matrix[i][j] > 0
    ]
    if times:
        logger.info(
            "Time matrix %dx%d — min %.0fs, max %.0fs, avg %.0fs",
            n, n, min(times), max(times), sum(times) / len(times),
        )
    if distance_matrix:
        dists = [
            distance_matrix[i][j]
            for i in range(n)
            for j in range(n)
            if i != j and distance_matrix[i][j] > 0
        ]
        if dists:
            logger.info(
                "Distance matrix %dx%d — min %.0fm, max %.0fm, avg %.0fm",
                n, n, min(dists), max(dists), sum(dists) / len(dists),
            )


def solve_vrptw(
    time_matrix: list[list[float]],
    time_windows: list[tuple[int, int]],
    depot: int = 0,
    courier_start_time: int = 480,
    service_time_per_stop: int = 3,
    num_couriers: int = 1,
    capacity: int | None = None,
    initial_routes: list[list[int]] | None = None,
    distance_matrix: list[list[float]] | None = None,
    max_wait_min: int = 15,
    max_route_duration_min: int | None = None,
) -> tuple[list[list[int]], list[list[int]], list[int]]:
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
        initial_routes: Optional per-vehicle node lists (original node numbers, depot
                        excluded).  When provided the provided order is used as the
                        initial solution; local search may then improve within/across.
        distance_matrix: Optional OSRM distances in meters. When provided, arc cost is
                         minimised in meters (geographic efficiency); otherwise falls
                         back to time-based arc cost.

    Returns:
        (routes, etas): routes[v] = ordered node indices for courier v (depot excluded);
                        etas[v]   = arrival times in minutes since midnight per stop.
        ([[], ...], [[], ...], []) if no feasible solution found.
    """
    if not time_matrix or not time_windows:
        logger.warning("VRPTW: empty input")
        return [[] for _ in range(num_couriers)], [[] for _ in range(num_couriers)], []

    num_locations = len(time_matrix)
    if len(time_windows) != num_locations:
        raise ValueError("time_windows length must match time_matrix")
    if depot != 0:
        raise ValueError("Depot must be node 0")
    if num_couriers < 1:
        raise ValueError("num_couriers must be >= 1")

    _log_matrix_stats(time_matrix, distance_matrix)

    # Max waiting time at any stop before service starts
    slack_max = max_wait_min

    # Open-route: add a virtual end node so couriers do not need to return to depot.
    # Travel cost from any node to dummy_end is 0 (no return leg in objective).
    dummy_end = num_locations
    extended_time = [row + [0] for row in time_matrix] + [[0] * (num_locations + 1)]

    extended_dist: list[list[float]] | None = None
    if distance_matrix:
        extended_dist = [row + [0] for row in distance_matrix] + [[0] * (num_locations + 1)]

    def travel_minutes(i: int, j: int) -> int:
        return int(round(extended_time[i][j] / 60))

    def service_minutes(node: int) -> int:
        return service_time_per_stop if node not in (depot, dummy_end) else 0

    starts = [depot] * num_couriers
    ends = [dummy_end] * num_couriers
    manager = pywrapcp.RoutingIndexManager(num_locations + 1, num_couriers, starts, ends)
    routing = pywrapcp.RoutingModel(manager)

    # --- Time callback: service at origin + travel to destination ---
    def time_callback(from_index: int, to_index: int) -> int:
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return service_minutes(from_node) + travel_minutes(from_node, to_node)

    transit_callback_index = routing.RegisterTransitCallback(time_callback)

    # --- Arc cost: distance in meters (geographic efficiency) or fallback to time ---
    if extended_dist is not None:
        def distance_callback(from_index: int, to_index: int) -> int:
            from_node = manager.IndexToNode(from_index)
            to_node = manager.IndexToNode(to_index)
            return int(round(extended_dist[from_node][to_node]))

        dist_callback_index = routing.RegisterTransitCallback(distance_callback)
        routing.SetArcCostEvaluatorOfAllVehicles(dist_callback_index)
        logger.info("VRPTW: using distance-based arc cost (meters)")
    else:
        routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)
        logger.info("VRPTW: using time-based arc cost (fallback)")

    # --- Time dimension ---
    routing.AddDimension(
        transit_callback_index,
        slack_max,
        MINUTES_PER_DAY,
        False,  # do not force start cumul to zero
        "Time",
    )
    time_dimension = routing.GetDimensionOrDie("Time")

    # Couriers may depart any time on or after courier_start_time.
    # The solver will choose the optimal departure per courier — one with only
    # a 15:00 stop will depart ~14:49 rather than waiting idle since 09:00.
    for v in range(num_couriers):
        start_index = routing.Start(v)
        time_dimension.CumulVar(start_index).SetRange(
            courier_start_time, MINUTES_PER_DAY
        )

    # Hard cap on total route duration (including service time at every stop)
    if max_route_duration_min is not None:
        for v in range(num_couriers):
            time_dimension.SetSpanUpperBoundForVehicle(max_route_duration_min, v)

    # Apply time windows to delivery stops (shared across all couriers)
    for location_idx in range(num_locations):
        if location_idx in (depot, dummy_end):
            continue
        tw_min, tw_max = time_windows[location_idx]
        index = manager.NodeToIndex(location_idx)
        time_dimension.CumulVar(index).SetRange(tw_min, tw_max)

    # Allow any stop to be dropped rather than violating max_wait_min.
    # High penalty ensures the solver only drops as a last resort.
    _DROP_PENALTY = 10_000_000
    for location_idx in range(1, num_locations):  # skip depot (0)
        routing.AddDisjunction(
            [manager.NodeToIndex(location_idx)],
            _DROP_PENALTY,
        )

    # Penalise waiting: slack = idle time at each node before service.
    time_dimension.SetSlackCostCoefficientForAllVehicles(5)

    # Finaliser: minimise both departure and finish time per courier.
    # Minimising start pushes early-window couriers to depart promptly;
    # minimising end gives a tiebreaker on route efficiency.
    for v in range(num_couriers):
        routing.AddVariableMinimizedByFinalizer(
            time_dimension.CumulVar(routing.Start(v))
        )
        routing.AddVariableMinimizedByFinalizer(
            time_dimension.CumulVar(routing.End(v))
        )

    # --- Capacity dimension (optional) ---
    if capacity is not None:
        demands = [0] + [1] * (num_locations - 1) + [0]

        def demand_callback(from_index: int) -> int:
            return demands[manager.IndexToNode(from_index)]

        demand_callback_index = routing.RegisterUnaryTransitCallback(demand_callback)
        routing.AddDimensionWithVehicleCapacity(
            demand_callback_index,
            0,
            [capacity] * num_couriers,
            True,
            "Capacity",
        )

    # --- Search parameters ---
    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )

    if initial_routes is not None:
        search_parameters.time_limit.seconds = 15
        logger.info("VRPTW: using initial_routes hint, time limit 15s")
    else:
        search_parameters.first_solution_strategy = (
            routing_enums_pb2.FirstSolutionStrategy.SAVINGS
        )
        search_parameters.time_limit.seconds = 15
        logger.info("VRPTW: SAVINGS first solution strategy, time limit 15s")

    logger.info(
        "VRPTW solver: %d locations, %d couriers, depot=%d, start=%02d:%02d, "
        "service=%dmin, capacity=%s, initial_routes=%s, dist_matrix=%s",
        num_locations,
        num_couriers,
        depot,
        courier_start_time // 60,
        courier_start_time % 60,
        service_time_per_stop,
        str(capacity) if capacity is not None else "unlimited",
        "yes" if initial_routes is not None else "no",
        "yes" if extended_dist is not None else "no",
    )

    if initial_routes is not None:
        initial_assignment = routing.ReadAssignmentFromRoutes(initial_routes, True)
        if initial_assignment:
            solution = routing.SolveFromAssignmentWithParameters(
                initial_assignment, search_parameters
            )
        else:
            logger.warning("VRPTW: initial assignment invalid, falling back to SAVINGS")
            search_parameters.first_solution_strategy = (
                routing_enums_pb2.FirstSolutionStrategy.SAVINGS
            )
            solution = routing.SolveWithParameters(search_parameters)
    else:
        solution = routing.SolveWithParameters(search_parameters)

    if not solution:
        logger.error("VRPTW: no feasible solution found")
        return [[] for _ in range(num_couriers)], [[] for _ in range(num_couriers)], [], []

    routes: list[list[int]] = []
    etas: list[list[int]] = []
    departures: list[int] = []  # actual departure time per courier (minutes since midnight)

    for v in range(num_couriers):
        v_route: list[int] = []
        v_etas: list[int] = []
        index = routing.Start(v)
        dep_time = solution.Min(time_dimension.CumulVar(index))
        departures.append(dep_time)
        total_dist_m = 0.0
        while not routing.IsEnd(index):
            node = manager.IndexToNode(index)
            next_index = solution.Value(routing.NextVar(index))
            next_node = manager.IndexToNode(next_index)
            if node not in (depot, dummy_end):
                v_route.append(node)
                v_etas.append(solution.Min(time_dimension.CumulVar(index)))
            if extended_dist is not None and not routing.IsEnd(next_index):
                total_dist_m += extended_dist[node][next_node]
            index = next_index
        routes.append(v_route)
        etas.append(v_etas)
        logger.info(
            "VRPTW: courier %d — departs %02d:%02d, %d stops, %.1f km",
            v + 1, dep_time // 60, dep_time % 60, len(v_route), total_dist_m / 1000,
        )

    # Collect nodes that were dropped (disjunction self-loop in solution)
    dropped_nodes: list[int] = []
    for location_idx in range(1, num_locations):
        index = manager.NodeToIndex(location_idx)
        if solution.Value(routing.NextVar(index)) == index:
            dropped_nodes.append(location_idx)
            logger.info("VRPTW: node %d dropped (wait constraint)", location_idx)

    return routes, etas, dropped_nodes, departures
