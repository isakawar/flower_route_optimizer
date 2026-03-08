"""
Solver time-window invariants.

Invariant: if a stop has a time window [tw_start, tw_end], its ETA must satisfy
    tw_start <= ETA <= tw_end
The courier is allowed to arrive early and wait.

We never assert exact ETA values — only that the window is respected.
"""

import pytest
from solver.vrptw_solver import solve_vrptw, MINUTES_PER_DAY
from tests.conftest import make_matrix

START = 540   # 09:00 in minutes
NO_WINDOW = (0, MINUTES_PER_DAY)


def _all_stops_etas(routes, etas):
    """Flatten (node, eta) pairs from all couriers."""
    return [(node, eta) for route, eta_list in zip(routes, etas) for node, eta in zip(route, eta_list)]


# ---------------------------------------------------------------------------
# Core window-adherence tests
# ---------------------------------------------------------------------------

class TestTimeWindowAdherence:
    """Solver must respect every time window, regardless of route order."""

    def _make_problem(self, n: int, windows: list[tuple[int, int]], n_couriers: int = 1):
        t, d = make_matrix(n)
        return solve_vrptw(
            time_matrix=t,
            time_windows=windows,
            depot=0,
            courier_start_time=START,
            service_time_per_stop=3,
            num_couriers=n_couriers,
        )

    def test_single_window_respected(self):
        """One stop with a tight window [10:00, 11:00]."""
        n = 3  # depot + 2 stops
        # Node 1: window 10:00–11:00 (600–660 min), Node 2: unconstrained
        windows = [NO_WINDOW, (600, 660), NO_WINDOW]
        routes, etas = self._make_problem(n, windows)

        node_eta = dict(_all_stops_etas(routes, etas))
        assert 600 <= node_eta[1] <= 660

    def test_multiple_windows_all_respected(self):
        """Four stops each with distinct windows; all must be satisfied."""
        n = 5  # depot + 4 stops
        windows = [
            NO_WINDOW,           # depot
            (600, 720),          # node 1: 10:00–12:00
            (660, 780),          # node 2: 11:00–13:00
            (780, 900),          # node 3: 13:00–15:00
            (840, 960),          # node 4: 14:00–16:00
        ]
        routes, etas = self._make_problem(n, windows, n_couriers=2)

        node_eta = dict(_all_stops_etas(routes, etas))
        for node, (tw_start, tw_end) in enumerate(windows):
            if node == 0:
                continue
            assert tw_start <= node_eta[node] <= tw_end, (
                f"Node {node}: ETA {node_eta[node]} not in [{tw_start}, {tw_end}]"
            )

    def test_courier_waits_when_arriving_early(self):
        """If a courier arrives before the window opens, it must wait.
        The ETA in that case must equal tw_start, not the raw arrival time.
        """
        n = 2  # depot + 1 stop
        # Start at 09:00, window opens at 12:00 — courier must wait ~3h
        windows = [NO_WINDOW, (720, 840)]  # 12:00–14:00
        routes, etas = self._make_problem(n, windows)

        node_eta = dict(_all_stops_etas(routes, etas))
        # ETA must be >= 720 (window open) even if travel takes only 10 min
        assert node_eta[1] >= 720

    def test_unconstrained_windows_always_satisfied(self):
        """Wide (0, 1440) windows impose no constraint — solver must always succeed."""
        n = 6
        windows = [NO_WINDOW] * n
        routes, etas = self._make_problem(n, windows, n_couriers=2)
        stops = [node for route in routes for node in route]
        assert sorted(stops) == list(range(1, n))

    def test_windows_after_start_time_satisfied(self):
        """Windows that open after courier start time must still be met."""
        n = 4
        windows = [
            (START, MINUTES_PER_DAY),  # depot
            (START + 120, START + 180),  # node 1: 2h after start
            (START + 180, START + 240),  # node 2: 3h after start
            (START + 60, START + 120),   # node 3: 1h after start
        ]
        routes, etas = self._make_problem(n, windows, n_couriers=1)
        node_eta = dict(_all_stops_etas(routes, etas))

        for node in [1, 2, 3]:
            tw_start, tw_end = windows[node]
            assert tw_start <= node_eta[node] <= tw_end


# ---------------------------------------------------------------------------
# Multi-courier window distribution
# ---------------------------------------------------------------------------

class TestMultiCourierWindows:
    def test_two_couriers_windows_all_met(self):
        """With two couriers and compatible windows, all windows satisfied."""
        n = 5
        windows = [
            NO_WINDOW,
            (600, 700),    # early group
            (620, 720),
            (840, 960),    # late group
            (860, 980),
        ]
        t, d = make_matrix(n)
        routes, etas = solve_vrptw(
            time_matrix=t,
            time_windows=windows,
            depot=0,
            courier_start_time=START,
            service_time_per_stop=3,
            num_couriers=2,
        )
        node_eta = dict(_all_stops_etas(routes, etas))
        for node in [1, 2, 3, 4]:
            tw_s, tw_e = windows[node]
            assert tw_s <= node_eta[node] <= tw_e
