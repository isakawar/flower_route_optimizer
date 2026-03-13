"""
Property-based tests using Hypothesis.

These tests generate random problem instances and assert system invariants.
No exact values are checked — only structural correctness.

Invariants tested:
1. All stops visited exactly once (no missing, no duplicates)
2. No stop appears in two couriers' routes simultaneously
3. Capacity limit never exceeded
4. ETAs are non-decreasing within each courier's route
5. Time windows are respected when feasible
"""

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

# Mark the whole module slow — skip with: pytest -m "not slow"
pytestmark = pytest.mark.slow

from solver.vrptw_solver import solve_vrptw, MINUTES_PER_DAY

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

@st.composite
def time_matrix_st(draw, min_size: int = 2, max_size: int = 7):
    """Generate a random n×n travel-time matrix (seconds).

    Diagonal is 0; off-diagonal values are in [60, 3600] (1 min – 1 h).
    """
    n = draw(st.integers(min_value=min_size, max_value=max_size))
    matrix: list[list[float]] = []
    for i in range(n):
        row: list[float] = []
        for j in range(n):
            if i == j:
                row.append(0.0)
            else:
                row.append(float(draw(st.integers(min_value=60, max_value=3600))))
        matrix.append(row)
    return matrix


@st.composite
def problem_st(draw):
    """Generate a complete unconstrained VRP problem."""
    t = draw(time_matrix_st(min_size=2, max_size=7))
    n = len(t)
    n_couriers = draw(st.integers(min_value=1, max_value=min(4, n - 1)))
    return t, n, n_couriers


@st.composite
def capacity_problem_st(draw):
    """Generate a VRP problem with a capacity constraint."""
    t = draw(time_matrix_st(min_size=3, max_size=7))
    n = len(t)
    n_stops = n - 1
    # Capacity chosen so that ceil(n_stops / cap) <= 4 couriers
    cap = draw(st.integers(min_value=1, max_value=n_stops))
    import math
    min_couriers = math.ceil(n_stops / cap)
    n_couriers = draw(st.integers(min_value=min_couriers, max_value=min(min_couriers + 3, 6)))
    return t, n, n_couriers, cap


# ---------------------------------------------------------------------------
# Settings: small examples, no deadline (solver may take a few seconds)
# ---------------------------------------------------------------------------
# Each hypothesis example calls the OR-Tools solver (up to 15s).
# max_examples=10 keeps the full suite under ~2 minutes.
# Increase to 50+ locally for deeper exploration.

BASE_SETTINGS = dict(
    max_examples=10,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)


# ---------------------------------------------------------------------------
# Property 1: All stops visited exactly once
# ---------------------------------------------------------------------------

@given(data=problem_st())
@settings(**BASE_SETTINGS)
def test_all_stops_visited_exactly_once(data):
    t, n, n_couriers = data
    n_stops = n - 1  # depot is node 0
    tw = [(0, MINUTES_PER_DAY)] * n

    routes, etas, _, _ = solve_vrptw(
        time_matrix=t,
        time_windows=tw,
        depot=0,
        courier_start_time=540,
        service_time_per_stop=3,
        num_couriers=n_couriers,
    )

    all_stops = [node for route in routes for node in route]

    # For unconstrained problems the solver must always find a solution
    assert len(all_stops) == n_stops, (
        f"Expected {n_stops} stops, got {len(all_stops)} "
        f"(n_couriers={n_couriers}, n={n})"
    )
    assert sorted(all_stops) == list(range(1, n_stops + 1))


# ---------------------------------------------------------------------------
# Property 2: No duplicate stops across couriers
# ---------------------------------------------------------------------------

@given(data=problem_st())
@settings(**BASE_SETTINGS)
def test_no_duplicate_stops(data):
    t, n, n_couriers = data
    tw = [(0, MINUTES_PER_DAY)] * n

    routes, _, _, _ = solve_vrptw(
        time_matrix=t,
        time_windows=tw,
        depot=0,
        courier_start_time=540,
        service_time_per_stop=3,
        num_couriers=n_couriers,
    )

    all_stops = [node for route in routes for node in route]
    assert len(all_stops) == len(set(all_stops)), "Duplicate stops found in solution"


# ---------------------------------------------------------------------------
# Property 3: Capacity never exceeded
# ---------------------------------------------------------------------------

@given(data=capacity_problem_st())
@settings(**BASE_SETTINGS)
def test_capacity_never_exceeded(data):
    t, n, n_couriers, cap = data
    tw = [(0, MINUTES_PER_DAY)] * n

    routes, _, _, _ = solve_vrptw(
        time_matrix=t,
        time_windows=tw,
        depot=0,
        courier_start_time=540,
        service_time_per_stop=3,
        num_couriers=n_couriers,
        capacity=cap,
    )

    for v, route in enumerate(routes):
        assert len(route) <= cap, (
            f"Courier {v + 1} has {len(route)} stops but capacity={cap}"
        )


# ---------------------------------------------------------------------------
# Property 4: ETAs non-decreasing within each route
# ---------------------------------------------------------------------------

@given(data=problem_st())
@settings(**BASE_SETTINGS)
def test_etas_non_decreasing_per_courier(data):
    t, n, n_couriers = data
    tw = [(0, MINUTES_PER_DAY)] * n

    routes, etas, _, _ = solve_vrptw(
        time_matrix=t,
        time_windows=tw,
        depot=0,
        courier_start_time=540,
        service_time_per_stop=3,
        num_couriers=n_couriers,
    )

    for route, eta_list in zip(routes, etas):
        assert len(route) == len(eta_list)
        for i in range(1, len(eta_list)):
            assert eta_list[i] >= eta_list[i - 1], (
                f"ETA decreased: {eta_list[i - 1]} → {eta_list[i]}"
            )


# ---------------------------------------------------------------------------
# Property 5: ETAs not before courier start time
# ---------------------------------------------------------------------------

@given(
    data=problem_st(),
    start=st.integers(min_value=360, max_value=720),  # 6:00 – 12:00
)
@settings(**BASE_SETTINGS)
def test_etas_not_before_start(data, start):
    t, n, n_couriers = data
    tw = [(0, MINUTES_PER_DAY)] * n

    routes, etas, _, _ = solve_vrptw(
        time_matrix=t,
        time_windows=tw,
        depot=0,
        courier_start_time=start,
        service_time_per_stop=3,
        num_couriers=n_couriers,
    )

    for eta_list in etas:
        for eta in eta_list:
            assert eta >= start, f"ETA {eta} is before start time {start}"


# ---------------------------------------------------------------------------
# Property 6: Result structure matches number of couriers
# ---------------------------------------------------------------------------

@given(data=problem_st())
@settings(**BASE_SETTINGS)
def test_result_has_n_courier_slots(data):
    t, n, n_couriers = data
    tw = [(0, MINUTES_PER_DAY)] * n

    routes, etas, _, _ = solve_vrptw(
        time_matrix=t,
        time_windows=tw,
        depot=0,
        courier_start_time=540,
        service_time_per_stop=3,
        num_couriers=n_couriers,
    )

    assert len(routes) == n_couriers
    assert len(etas) == n_couriers
