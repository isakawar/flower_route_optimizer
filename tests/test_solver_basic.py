"""
Solver basic invariants.

Rules: every stop must be visited exactly once; no duplicates;
total visited == input count.  We never assert route order or exact ETAs.
"""

import pytest
from solver.vrptw_solver import solve_vrptw, MINUTES_PER_DAY
from tests.conftest import make_matrix

# Unconstrained time windows — solver is free to assign any order.
NO_WINDOW = (0, MINUTES_PER_DAY)
START = 540  # 09:00 in minutes


def _all_stops(routes: list[list[int]]) -> list[int]:
    return [node for route in routes for node in route]


def _unconstrained_windows(n: int) -> list[tuple[int, int]]:
    return [NO_WINDOW] * n


# ---------------------------------------------------------------------------
# Single courier
# ---------------------------------------------------------------------------

class TestSingleCourier:
    N = 5  # depot + 4 stops

    @pytest.fixture(autouse=True)
    def setup(self):
        self.t, self.d = make_matrix(self.N)
        self.tw = _unconstrained_windows(self.N)
        self.n_stops = self.N - 1  # nodes 1..4

    def _solve(self, **kwargs):
        defaults = dict(
            time_matrix=self.t,
            time_windows=self.tw,
            depot=0,
            courier_start_time=START,
            service_time_per_stop=3,
            num_couriers=1,
        )
        defaults.update(kwargs)
        return solve_vrptw(**defaults)

    def test_all_stops_visited(self):
        routes, _ = self._solve()
        stops = _all_stops(routes)
        assert sorted(stops) == list(range(1, self.n_stops + 1))

    def test_no_duplicate_stops(self):
        routes, _ = self._solve()
        stops = _all_stops(routes)
        assert len(stops) == len(set(stops))

    def test_total_stops_equals_input(self):
        routes, _ = self._solve()
        assert sum(len(r) for r in routes) == self.n_stops

    def test_etas_length_matches_route(self):
        routes, etas = self._solve()
        for route, eta in zip(routes, etas):
            assert len(route) == len(eta)

    def test_etas_are_non_decreasing(self):
        """Courier can only move forward in time."""
        routes, etas = self._solve()
        for route, eta in zip(routes, etas):
            for i in range(1, len(eta)):
                assert eta[i] >= eta[i - 1]

    def test_etas_not_before_start(self):
        routes, etas = self._solve()
        for eta in etas:
            for t in eta:
                assert t >= START


# ---------------------------------------------------------------------------
# Multiple couriers
# ---------------------------------------------------------------------------

class TestMultipleCouriers:
    N = 7  # depot + 6 stops

    @pytest.fixture(autouse=True)
    def setup(self):
        self.t, self.d = make_matrix(self.N)
        self.tw = _unconstrained_windows(self.N)
        self.n_stops = self.N - 1

    def _solve(self, n_couriers: int, **kwargs):
        return solve_vrptw(
            time_matrix=self.t,
            time_windows=self.tw,
            depot=0,
            courier_start_time=START,
            service_time_per_stop=3,
            num_couriers=n_couriers,
            **kwargs,
        )

    def test_all_stops_visited_two_couriers(self):
        routes, _ = self._solve(2)
        stops = _all_stops(routes)
        assert sorted(stops) == list(range(1, self.n_stops + 1))

    def test_no_overlap_between_couriers(self):
        routes, _ = self._solve(2)
        stops = _all_stops(routes)
        assert len(stops) == len(set(stops))

    def test_three_couriers_cover_all(self):
        routes, _ = self._solve(3)
        stops = _all_stops(routes)
        assert sorted(stops) == list(range(1, self.n_stops + 1))

    def test_more_couriers_than_stops_still_valid(self):
        """When couriers > stops, some couriers get empty routes — that's fine."""
        routes, _ = self._solve(self.n_stops + 2)
        stops = _all_stops(routes)
        assert sorted(stops) == list(range(1, self.n_stops + 1))

    def test_result_has_exactly_n_courier_slots(self):
        n = 3
        routes, etas = self._solve(n)
        assert len(routes) == n
        assert len(etas) == n


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_single_stop(self):
        n = 2  # depot + 1 stop
        t, d = make_matrix(n)
        tw = _unconstrained_windows(n)
        routes, etas = solve_vrptw(t, tw, courier_start_time=START, num_couriers=1)
        stops = _all_stops(routes)
        assert stops == [1]

    def test_with_distance_matrix(self):
        """Passing distance_matrix should still produce a valid solution."""
        n = 5
        t, d = make_matrix(n)
        tw = _unconstrained_windows(n)
        routes, _ = solve_vrptw(
            t, tw, courier_start_time=START, num_couriers=1, distance_matrix=d
        )
        stops = _all_stops(routes)
        assert sorted(stops) == list(range(1, n))

    def test_with_initial_routes_hint(self):
        """Initial routes hint must still produce a valid (or better) solution."""
        n = 5
        t, d = make_matrix(n)
        tw = _unconstrained_windows(n)
        # Hint: give all stops to courier 0
        initial = [list(range(1, n)), []]
        routes, _ = solve_vrptw(
            t, tw, courier_start_time=START, num_couriers=2, initial_routes=initial
        )
        stops = _all_stops(routes)
        assert sorted(stops) == list(range(1, n))
        assert len(stops) == len(set(stops))
