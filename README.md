
# Flower Delivery Route Optimizer

This project is a **route optimization tool for a flower delivery business**.

Goal: build a program that receives a **CSV file with delivery addresses** and calculates
the **optimal delivery route**.

The system will be developed in **two versions**.

---

# Version 1 (MVP)

Program flow:

CSV → Geocoding → Distance Matrix → Route Optimization → Optimal Route

Features:

- Read CSV file with addresses
- Convert addresses to coordinates using Geocoding API
- Build distance matrix
- Solve Traveling Salesman Problem (TSP)
- Print optimal route

---

# Version 2

Adds support for **delivery time windows**.

CSV → Geocode → Matrix → VRPTW Solver → Route with ETA

Features:

- customer preferred delivery time
- ETA calculation
- constraint-based optimization

---

# Example CSV

id,city,address,house,time_start,time_end
1,Kyiv,Khreshchatyk,1,10:00,11:00
2,Kyiv,Lesi Ukrainky,10,11:00,13:00
3,Kyiv,Obolon Avenue,5,,

---

# Project Structure

route_optimizer/

services/
- csv_service.py
- geocoding_service.py
- matrix_service.py

solver/
- tsp_solver.py
- vrptw_solver.py

models/
- order.py

utils/
- cache.py
- time_parser.py

scripts/
- run_optimizer.py

docs/
- cursor_prompts.md

## Module roles

| Module   | Role |
|----------|------|
| **models**  | Data structures and domain entities: orders, stops, routes, config. Single source of truth for types used by the rest of the app. |
| **utils**   | Shared helpers and pure functions: distance/time math, formatting, caching, file I/O. No business logic; reusable across services and solver. |
| **solver**  | Optimization logic: constraints, objective (e.g. minimize distance), and the algorithm (TSP, VRPTW). Uses models for I/O and utils for calculations. |
| **services**| Orchestration: load data (CSV, geocoding, matrix), call the solver, return or save results. Glues models, solver, and utils into one flow. |

---

# APIs Used

Geocoding:

OpenStreetMap Nominatim

https://nominatim.openstreetmap.org

Routing:

OSRM

http://router.project-osrm.org

---

# Running the project

Install dependencies

pip install -r requirements.txt

Run

python scripts/run_optimizer.py data/orders.csv
