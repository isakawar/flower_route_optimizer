"""Vehicle Routing Problem with Time Windows solver using Google OR-Tools."""

import logging

from ortools.constraint_solver import pywrapcp
from ortools.constraint_solver import routing_enums_pb2

logger = logging.getLogger(__name__)
SECONDS_PER_DAY = 24 * 60 * 60


def solve_vrptw(
    time_matrix: list[list[float]],
    time_windows: list[tuple[int, int]],
    depot: int = 0,
) -> tuple[list[int], list[int]]:
    """
    Solve VRPTW: single courier, start at depot, respect delivery time windows.

    Args:
        time_matrix: Square matrix of travel times in seconds.
                     time_matrix[i][j] = travel time from location i to j.
                     Index 0 = office (depot).
        time_windows: For each location i, (earliest, latest) in seconds since midnight.
                      time_windows[i] = (min_arrival_sec, max_arrival_sec).
                      Use (0, SECONDS_PER_DAY) for no constraint.
        depot: Index of depot/office (default 0).

    Returns:
        (route, etas): route = list of location indices (excluding depot);
                       etas = arrival time in seconds since midnight for each stop.
        ([], []) if no feasible solution.
    """
    if not time_matrix or not time_windows:
        logger.warning("VRPTW: empty input")
        return [], []

    num_locations = len(time_matrix)
    if len(time_windows) != num_locations:
        raise ValueError("time_windows length must match time_matrix")

    num_vehicles = 1
    slack_max = 3600  # allow 1h waiting
    vehicle_max = SECONDS_PER_DAY

    def to_int(x: float) -> int:
        if x is None:
            return 0
        return int(round(x))

    manager = pywrapcp.RoutingIndexManager(num_locations, num_vehicles, depot)
    routing = pywrapcp.RoutingModel(manager)

    def time_callback(from_index: int, to_index: int) -> int:
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return to_int(time_matrix[from_node][to_node])

    transit_callback_index = routing.RegisterTransitCallback(time_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

    routing.AddDimension(
        transit_callback_index,
        slack_max,
        vehicle_max,
        False,
        "Time",
    )
    time_dimension = routing.GetDimensionOrDie("Time")

    for location_idx, (tw_min, tw_max) in enumerate(time_windows):
        if location_idx == depot:
            continue
        index = manager.NodeToIndex(location_idx)
        time_dimension.CumulVar(index).SetRange(tw_min, tw_max)

    depot_tw_min, depot_tw_max = time_windows[depot]
    index = routing.Start(0)
    time_dimension.CumulVar(index).SetRange(depot_tw_min, depot_tw_max)

    routing.AddVariableMinimizedByFinalizer(time_dimension.CumulVar(routing.Start(0)))
    routing.AddVariableMinimizedByFinalizer(time_dimension.CumulVar(routing.End(0)))

    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    )

    logger.info("VRPTW solver: %d locations, depot=%d", num_locations, depot)
    solution = routing.SolveWithParameters(search_parameters)
    if not solution:
        logger.error("VRPTW: no feasible solution found")
        return [], []

    logger.info("VRPTW: solution found, %d stops", num_locations - 1)
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

    return route, etas
