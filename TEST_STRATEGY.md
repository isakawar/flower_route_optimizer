# TEST_STRATEGY.md

## Purpose

This document defines the testing strategy for the Flower Delivery Route
Optimizer.

The goal is to ensure that the routing engine behaves correctly as the
project evolves. Tests must verify **system behavior and invariants**,
not implementation details.

This ensures that future refactors or algorithm improvements do not
break the system.

------------------------------------------------------------------------

# Testing Philosophy

Tests should validate **what must always be true**, regardless of how
the algorithm is implemented.

Avoid tests like:

-   checking exact route order
-   checking exact ETA values
-   asserting specific solver strategies

These are **fragile tests**.

Instead test **invariants**.

------------------------------------------------------------------------

# Core System Invariants

The following must always be true for every optimization result.

## 1. All Deliveries Are Served

Every order from the input CSV must appear exactly once in the final
routes.

Constraints:

-   no missing deliveries
-   no duplicate deliveries

Example check:

Total returned stops == number of geocoded orders

------------------------------------------------------------------------

## 2. No Duplicate Deliveries

Each order ID may appear **only once** across all courier routes.

Example invariant:

set(all_stops) == list(all_stops)

------------------------------------------------------------------------

## 3. Time Windows Are Respected

If a delivery has:

time_start time_end

Then:

ETA \>= time_start\
ETA \<= time_end

If the courier arrives earlier, waiting is allowed.

------------------------------------------------------------------------

## 4. Courier Capacity Is Respected

If capacity is defined:

number_of_stops_per_courier \<= capacity

------------------------------------------------------------------------

## 5. Routes Contain Valid Coordinates

Each stop must contain:

lat lng

Coordinates must be valid floats.

------------------------------------------------------------------------

## 6. API Responses Are Valid

For `/api/optimize` responses:

Required fields:

routes stats depot

Each route must contain:

courierId stops totalDriveMin totalDistanceKm

------------------------------------------------------------------------

## 7. Recalculate Endpoint Must Preserve Order

The endpoint `/api/recalculate` must:

-   keep the same stop order
-   only recompute ETA and drive time

------------------------------------------------------------------------

# Types of Tests

## Unit Tests

Test individual components:

solver matrix builder time parsing geocoding cache

------------------------------------------------------------------------

## Integration Tests

Test the full optimization pipeline:

CSV -\> API -\> routes

------------------------------------------------------------------------

## Property Tests

Generate random problem instances and validate invariants.

Examples:

-   no duplicates
-   all stops visited
-   routes valid

------------------------------------------------------------------------

## Edge Case Tests

Important edge cases:

single delivery large number of deliveries impossible time windows no
geocodable addresses

------------------------------------------------------------------------

# Fixtures

Fixtures should simulate realistic delivery data.

Recommended fixtures:

small_orders.csv (5 deliveries)

time_windows_orders.csv (strict windows)

infeasible_orders.csv (impossible constraints)

------------------------------------------------------------------------

# Regression Tests

Regression tests ensure that future algorithm changes do not degrade
performance.

Metrics to track:

-   total route distance
-   total drive time
-   number of couriers used

Example:

Total distance must not increase by more than 30% after code changes.

------------------------------------------------------------------------

# CI Strategy

Tests should run automatically on:

-   every commit
-   every pull request

Recommended command:

pytest

------------------------------------------------------------------------

# Testing Goals

Ensure:

Correctness of routes\
API stability\
Solver reliability\
Future-safe refactoring
