"""
Solver capacity invariants.

Invariant: if capacity=C, then every courier route must have at most C stops.
All deliveries must still be served.
"""

import pytest
from solver.vrptw_solver import solve_vrptw, MINUTES_PER_DAY
from tests.conftest import make_matrix

NO_WINDOW = (0, MINUTES_PER_DAY)
START = 540  # 09:00


def _all_stops(routes):
    return [n for r in routes for n in r]


def _solve(n_nodes: int, n_couriers: int, capacity: int | None, **kwargs):
    t, d = make_matrix(n_nodes)
    tw = [NO_WINDOW] * n_nodes
    return solve_vrptw(
        time_matrix=t,
        time_windows=tw,
        depot=0,
        courier_start_time=START,
        service_time_per_stop=3,
        num_couriers=n_couriers,
        capacity=capacity,
        **kwargs,
    )


class TestCapacityLimit:
    def test_each_courier_within_capacity(self):
        cap = 2
        routes, _ = _solve(n_nodes=5, n_couriers=3, capacity=cap)
        for route in routes:
            assert len(route) <= cap, f"Route has {len(route)} stops, limit is {cap}"

    def test_all_stops_still_served_with_capacity(self):
        n = 5  # depot + 4 stops
        routes, _ = _solve(n_nodes=n, n_couriers=2, capacity=2)
        stops = _all_stops(routes)
        assert sorted(stops) == list(range(1, n))

    def test_capacity_one_each_stop_gets_own_courier(self):
        """capacity=1 means every stop must be its own courier's only delivery."""
        n_stops = 4
        routes, _ = _solve(n_nodes=n_stops + 1, n_couriers=n_stops, capacity=1)
        for route in routes:
            assert len(route) <= 1
        stops = _all_stops(routes)
        assert sorted(stops) == list(range(1, n_stops + 1))

    def test_no_duplicates_with_capacity(self):
        routes, _ = _solve(n_nodes=6, n_couriers=3, capacity=2)
        stops = _all_stops(routes)
        assert len(stops) == len(set(stops))

    def test_higher_capacity_still_valid(self):
        """Large capacity is equivalent to unlimited — all stops still served."""
        n = 6
        routes, _ = _solve(n_nodes=n, n_couriers=1, capacity=100)
        stops = _all_stops(routes)
        assert sorted(stops) == list(range(1, n))


class TestUnlimitedCapacity:
    def test_none_capacity_works(self):
        n = 6
        routes, _ = _solve(n_nodes=n, n_couriers=2, capacity=None)
        stops = _all_stops(routes)
        assert sorted(stops) == list(range(1, n))
        assert len(stops) == len(set(stops))

    def test_none_capacity_no_per_route_limit(self):
        """With no capacity, a single courier may carry all stops."""
        n = 7
        routes, _ = _solve(n_nodes=n, n_couriers=1, capacity=None)
        stops = _all_stops(routes)
        assert sorted(stops) == list(range(1, n))


class TestCapacityWithDistanceMatrix:
    def test_capacity_respected_with_dist_matrix(self):
        """Capacity invariant holds when distance_matrix is used as arc cost."""
        n = 5
        cap = 2
        t, d = make_matrix(n)
        tw = [NO_WINDOW] * n
        routes, _ = solve_vrptw(
            time_matrix=t,
            time_windows=tw,
            depot=0,
            courier_start_time=START,
            service_time_per_stop=3,
            num_couriers=3,
            capacity=cap,
            distance_matrix=d,
        )
        for route in routes:
            assert len(route) <= cap
        stops = _all_stops(routes)
        assert sorted(stops) == list(range(1, n))
