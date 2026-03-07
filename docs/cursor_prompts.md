
# Cursor Prompt Pack

Use these prompts **one by one in Cursor** to build the project.

---

## Prompt 1 — Project Setup

Create a Python project structure for a delivery route optimizer.

Modules:

services
solver
models
utils

Explain the role of each module.

---

## Prompt 2 — CSV Reader

Implement a Python module that reads delivery orders from a CSV file.

Columns:

id
city
address
house
time_start
time_end

Return list of Order objects.

---

## Prompt 3 — Order Model

Create a Pydantic model:

Order

Fields:

id
city
address
house
lat
lng
time_start
time_end

---

## Prompt 4 — Geocoding Service

Create a service that converts addresses to coordinates.

Use:

OpenStreetMap Nominatim API

Input:

address string

Output:

latitude and longitude

Add caching using JSON file.

---

## Prompt 5 — Distance Matrix

Implement a service that builds a distance/time matrix.

Use:

OSRM Table API

Input:

list of coordinates

Output:

matrix of travel times.

---

## Prompt 6 — TSP Solver

Implement a Traveling Salesman Problem solver using Google OR‑Tools.

Constraints:

single courier
start location = office

Return optimal order sequence.

---

## Prompt 7 — CLI Script

Create a CLI program:

scripts/run_optimizer.py

Flow:

read CSV
geocode addresses
build matrix
run solver
print route

---

## Prompt 8 — Time Window Support

Extend solver to support:

delivery time windows.

Use:

VRPTW solver in Google OR‑Tools.

---

## Prompt 9 — ETA Calculation

Add ETA calculation based on travel times.

---

## Prompt 10 — Output Format

Return route result as JSON:

order_id
eta
position_in_route

---

## Prompt 11 — Logging

Add logging for:

API calls
route solver
errors

---

## Prompt 12 — Simulation

Create script that generates 100 random delivery addresses
and tests route optimization.

---

## Prompt 13 — Map Visualization

Add simple route visualization using:

Leaflet or Mapbox.

---

## Prompt 14 — Batch Optimization

Add feature to recompute routes every 10 minutes
when new orders arrive.

---

## Prompt 15 — Scaling Plan

Suggest architecture improvements to support:

1000 deliveries per day.
