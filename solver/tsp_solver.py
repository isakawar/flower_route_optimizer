"""Traveling Salesman Problem solver using Google OR-Tools."""

from ortools.constraint_solver import pywrapcp
from ortools.constraint_solver import routing_enums_pb2


def solve_tsp(
    time_matrix: list[list[float]],
    depot: int = 0,
) -> list[int]:
    """
    Solve TSP: single courier, start at office (depot), minimize total travel time.

    Args:
        time_matrix: Square matrix of travel times in seconds.
                     time_matrix[i][j] = travel time from location i to j.
                     Index 0 = office (depot).
        depot: Index of depot/office (default 0). Start and end location.

    Returns:
        Optimal visit sequence as list of location indices.
        Excludes depot from the middle; full route is depot -> seq[0] -> seq[1] -> ... -> depot.
        E.g. [2, 1, 3] means visit 2, then 1, then 3 (starting and ending at depot).
    """
    if not time_matrix:
        return []

    num_locations = len(time_matrix)
    num_vehicles = 1

    # OR-Tools requires integer costs; convert seconds to int
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

    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    )

    solution = routing.SolveWithParameters(search_parameters)
    if not solution:
        return []

    # Extract visit sequence (exclude depot from result)
    route: list[int] = []
    index = routing.Start(0)
    while not routing.IsEnd(index):
        node = manager.IndexToNode(index)
        if node != depot:
            route.append(node)
        index = solution.Value(routing.NextVar(index))

    return route
