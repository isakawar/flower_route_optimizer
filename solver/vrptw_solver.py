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
) -> tuple[list[int], list[int]]:
    """
    Solve VRPTW: single courier, start at depot at courier_start_time.

    Args:
        time_matrix: Square matrix of travel times in seconds (from OSRM).
                     Index 0 = depot.
        time_windows: For each location i, (earliest, latest) in minutes since midnight.
                      Use (0, MINUTES_PER_DAY) for no constraint.
        depot: Index of depot (must be 0).
        courier_start_time: Shift start in minutes since midnight (e.g. 480 = 08:00).
        service_time_per_stop: Fixed service duration in minutes per delivery stop.

    Returns:
        (route, etas): route = ordered list of location indices (excluding depot);
                       etas = arrival time in minutes since midnight for each stop.
        ([], []) if no feasible solution.
    """
    if not time_matrix or not time_windows:
        logger.warning("VRPTW: empty input")
        return [], []

    num_locations = len(time_matrix)
    if len(time_windows) != num_locations:
        raise ValueError("time_windows length must match time_matrix")
    if depot != 0:
        raise ValueError("Depot must be node 0")

    num_vehicles = 1
    # Allow waiting up to 4 hours at any stop
    slack_max = 4 * 60

    def travel_minutes(i: int, j: int) -> int:
        return int(round(time_matrix[i][j] / 60))

    def service_minutes(node: int) -> int:
        return 0 if node == depot else service_time_per_stop

    manager = pywrapcp.RoutingIndexManager(num_locations, num_vehicles, depot)
    routing = pywrapcp.RoutingModel(manager)

    def time_callback(from_index: int, to_index: int) -> int:
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        # Transit = service time at origin + travel time to destination
        return service_minutes(from_node) + travel_minutes(from_node, to_node)

    transit_callback_index = routing.RegisterTransitCallback(time_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

    routing.AddDimension(
        transit_callback_index,
        slack_max,
        MINUTES_PER_DAY,
        False,  # do not force start cumul to zero
        "Time",
    )
    time_dimension = routing.GetDimensionOrDie("Time")

    # Fix courier departure from depot to exactly courier_start_time
    start_index = routing.Start(0)
    time_dimension.CumulVar(start_index).SetRange(courier_start_time, courier_start_time)

    # Apply time windows to delivery stops
    for location_idx in range(num_locations):
        if location_idx == depot:
            continue
        tw_min, tw_max = time_windows[location_idx]
        index = manager.NodeToIndex(location_idx)
        time_dimension.CumulVar(index).SetRange(tw_min, tw_max)

    # Penalise waiting time in the primary objective.
    # Span = end_cumul - start_cumul = travel + service + waiting.
    # Arc cost already covers travel + service, so the span coefficient
    # adds exactly 1 unit of cost per minute of waiting across the route.
    # This makes the solver prefer arriving close to the window start
    # rather than very early and idling.
    time_dimension.SetSpanCostCoefficientForAllVehicles(1)

    # Secondary: in case of ties, also minimise the absolute return time.
    routing.AddVariableMinimizedByFinalizer(time_dimension.CumulVar(routing.End(0)))

    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    )
    search_parameters.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )
    search_parameters.time_limit.seconds = 10

    logger.info(
        "VRPTW solver: %d locations, depot=%d, start=%02d:%02d, service=%dmin",
        num_locations,
        depot,
        courier_start_time // 60,
        courier_start_time % 60,
        service_time_per_stop,
    )
    solution = routing.SolveWithParameters(search_parameters)
    if not solution:
        logger.error("VRPTW: no feasible solution found")
        return [], []

    route: list[int] = []
    etas: list[int] = []
    index = routing.Start(0)
    while not routing.IsEnd(index):
        node = manager.IndexToNode(index)
        if node != depot:
            route.append(node)
            eta = solution.Min(time_dimension.CumulVar(index))
            etas.append(eta)
        index = solution.Value(routing.NextVar(index))

    logger.info("VRPTW: solution found, %d stops", len(route))
    return route, etas
