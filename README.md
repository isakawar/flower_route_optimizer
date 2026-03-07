# Flower Route Optimizer

Route optimization tool for a flower delivery business.
Reads a CSV of delivery orders, geocodes addresses, builds a real-road travel-time matrix, and finds the optimal multi-courier route respecting delivery time windows and vehicle capacity.

---

## Pipeline

```
CSV file
   │
   ▼
Geocode addresses          ← OpenStreetMap Nominatim (with JSON cache)
   │
   ▼
Build travel-time matrix   ← OSRM Table API (real driving times)
   │
   ▼
VRPTW solver               ← Google OR-Tools
   │
   ▼
Print route with ETA
```

---

## Features

| Feature | Details |
|---|---|
| Time windows | Per-order earliest/latest delivery constraints |
| Courier start time | Configurable shift start; all couriers depart together |
| Service time | Fixed 3 min stop per delivery, built into solver cost |
| Waiting penalty | Solver prefers arriving close to window start, not hours early |
| Multiple couriers | Automatic order distribution across N vehicles |
| Capacity limits | Max packages per courier enforced as a hard constraint |
| Geocode cache | Results saved to `geocode_cache.json`; never calls Nominatim twice for the same address |
| JSON output | Machine-readable output via `--json` for integration with other tools |
| Test data generator | Built-in script for generating realistic Kyiv delivery orders |

---

## Installation

```bash
python -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

**Dependencies** (`requirements.txt`):

```
requests
pandas
pydantic
ortools
```

---

## Quick start

```bash
# Single courier, default office address
python scripts/run_optimizer.py data/orders.csv

# Custom office, 10:00 start
python scripts/run_optimizer.py data/orders.csv "Kyiv, Nahorna 18" --start-time 10:00

# Two couriers, 5 packages each
python scripts/run_optimizer.py data/orders.csv "Kyiv, Nahorna 18" \
    --start-time 10:00 --couriers 2 --capacity 5

# JSON output
python scripts/run_optimizer.py data/orders.csv --json
```

---

## CLI reference

```
python scripts/run_optimizer.py <csv_path> [office_address] [options]
```

| Argument | Type | Default | Description |
|---|---|---|---|
| `csv_path` | positional | — | Path to the orders CSV file |
| `office_address` | positional (optional) | `вулиця Нагірна, 18, Київ` | Depot address; geocoded separately and placed at node 0 |
| `--start-time HH:MM` | option | `08:00` | Courier shift start — all couriers depart at this time |
| `--couriers N` | option | `1` | Number of couriers / vehicles |
| `--capacity N` | option | unlimited | Max packages per courier |
| `--json` | flag | off | Output route as JSON instead of human-readable text |
| `-v`, `--verbose` | flag | off | Enable debug logging (API calls, solver internals) |

---

## Orders CSV format

```
id,city,address,house,time_start,time_end
1,Kyiv,Khreshchatyk,1,10:00,11:00
2,Kyiv,Lesi Ukrainky,10,11:00,13:00
3,Kyiv,Obolon Avenue,5,,
4,Brovary,Kyivska,28,,
```

| Column | Required | Description |
|---|---|---|
| `id` | yes | Unique integer order ID |
| `city` | yes | City name (used when geocoding) |
| `address` | yes | Street name |
| `house` | yes | House number (may include letter suffix, e.g. `12а`) |
| `time_start` | no | Earliest acceptable delivery time `HH:MM` |
| `time_end` | no | Latest acceptable delivery time `HH:MM` |

Orders with empty `time_start` / `time_end` are treated as **flexible** — the solver can deliver them at any time.

---

## Output examples

### Text output (single courier)

```
Courier 1
----------------------------------------
Start: 10:00  Office (Kyiv, Nahorna 18)

  1. Order 3  —  Kyiv, Obolon Avenue 5
     ETA:     10:14
     Drive:   14 min

  2. Order 1  —  Kyiv, Khreshchatyk 1
     Arrival: 10:40
     Window:  11:00–12:00
     Wait:    20 min
     ETA:     11:00
     Drive:   26 min

  3. Order 2  —  Kyiv, Lesi Ukrainky 10
     ETA:     11:22
     Drive:   19 min

Return to depot.  (18 min)

  Drive total: 1h 17min
  Distance:    24.3 km

========================================
Summary:
  Couriers:    1
  Start time:  10:00
  Orders:      3 delivered
  Total drive: 1h 17min
  Total dist:  24.3 km
```

**Output fields:**

| Field | Description |
|---|---|
| **ETA** | Time the courier arrives and begins service |
| **Drive** | Travel time from the previous stop |
| **Arrival** | Natural arrival time before waiting for the window to open |
| **Window** | Required delivery time window |
| **Wait** | Time the courier waits before the window opens |

### Text output (multi-courier)

```
Courier 1
----------------------------------------
Start: 10:00  Office (Kyiv, Nahorna 18)

  1. Order 4  —  Kyiv, Podil 12
     ETA:     10:15
     Drive:   15 min

  2. Order 7  —  Kyiv, Obolon 5
     ETA:     10:32
     Drive:   17 min

Return to depot.  (22 min)

Courier 2
----------------------------------------
Start: 10:00  Office (Kyiv, Nahorna 18)

  1. Order 1  —  Kyiv, Khreshchatyk 1
     ETA:     10:10
     Drive:   10 min

  2. Order 3  —  Kyiv, Pechersk 4
     ETA:     10:25
     Drive:   15 min

Return to depot.  (20 min)

========================================
Summary:
  Couriers:    2
  Capacity:    5 packages/courier
  Start time:  10:00
  Orders:      4 delivered
  Total drive: 1h 24min
  Total dist:  31.1 km
```

### JSON output schema

```json
{
  "courier_start": "10:00",
  "num_couriers": 2,
  "capacity": 5,
  "couriers": [
    {
      "courier_id": 1,
      "route": [
        {
          "order_id": 4,
          "eta": "10:15",
          "drive_time_min": 15,
          "waiting_time_min": 0,
          "time_window": null,
          "position_in_route": 1
        }
      ],
      "statistics": {
        "total_drive_time_min": 54,
        "total_drive_time": "54 min",
        "total_distance_m": 18400,
        "total_distance": "18.4 km"
      }
    }
  ],
  "statistics": {
    "total_drive_time_min": 98,
    "total_drive_time": "1h 38min",
    "total_distance_m": 34200,
    "total_distance": "34.2 km"
  }
}
```

---

## Test data generator

Generates a realistic CSV of Kyiv delivery orders for testing.

```bash
# 20 orders, fixed seed for reproducibility
python scripts/generate_test_orders.py --orders 20 --seed 42

# Custom output path
python scripts/generate_test_orders.py --orders 30 --output data/big_test.csv
```

Writes to `data/test_orders.csv` by default.

| Flag | Default | Description |
|---|---|---|
| `--orders N` | `10` | Number of orders to generate |
| `--seed N` | random | Fixed seed for reproducible output |
| `--output PATH` | `data/test_orders.csv` | Output CSV path |

**Geographic distribution:**

| Zone | Weight | Areas |
|---|---|---|
| Centre | 35 % | Khreshchatyk, Pechersk, Shevchenkivskyi |
| Right bank | 25 % | Obolon, Podil, Syrets |
| Left bank | 25 % | Darnytsia, Dniprovskyi, Desna |
| Outskirts | 15 % | Brovary, Vyshneve, Irpin, Bucha |

30 % of generated orders receive a 1–2 hour delivery window; 70 % are flexible.

---

## Project structure

```
flower_route_optimizer/
│
├── data/
│   ├── orders.csv              # your delivery orders
│   └── test_orders.csv         # generated test data
│
├── models/
│   └── order.py                # Order Pydantic model
│
├── services/
│   ├── csv_service.py          # read orders from CSV
│   ├── geocoding_service.py    # address → (lat, lng) via Nominatim + cache
│   └── matrix_service.py       # (lat, lng)[] → time/distance matrix via OSRM
│
├── solver/
│   └── vrptw_solver.py         # OR-Tools VRPTW solver (multi-courier, capacity)
│
├── utils/
│   └── time_parser.py          # "HH:MM" ↔ seconds/minutes conversion
│
├── scripts/
│   ├── run_optimizer.py        # main CLI entry point
│   └── generate_test_orders.py # synthetic order generator
│
├── geocode_cache.json          # Nominatim result cache (auto-created)
└── requirements.txt
```

### Module roles

| Module | Role |
|---|---|
| `models` | Pydantic data classes — `Order` is the single source of truth for field names and types used by all other modules |
| `utils` | Pure helpers — time string parsing and formatting. No side effects, no business logic |
| `services` | I/O layer — reads CSV, calls external APIs (Nominatim, OSRM), returns typed results |
| `solver` | Optimization core — builds the OR-Tools model, adds dimensions and constraints, extracts the solution |
| `scripts` | CLI entry points — orchestrates the pipeline and handles all user-facing output |

---

## Solver design

### Time dimension

All times are in **minutes since midnight**.

- **Transit callback**: `transit(i → j) = service_time[i] + travel_time[i][j]`
  Service time at the depot is 0; at every delivery stop it is 3 minutes.
- `CumulVar(node)` represents the **arrival time** at that node.
- The depot start is pinned to exactly `courier_start_time` for every vehicle via `SetRange(t, t)`.
- Delivery stop time windows are enforced with `CumulVar.SetRange(tw_start, tw_end)`.

### Waiting penalty

`SetSpanCostCoefficientForAllVehicles(1)` is set on the time dimension.

```
span = end_cumul − start_cumul = travel + service + waiting
```

Arc cost already covers travel and service, so the span coefficient adds exactly **1 unit of cost per minute of waiting**. The solver therefore prefers arriving close to a window's start rather than early and idling.

### Capacity dimension

When `--capacity` is provided:

```python
demands = [0] + [1] * num_orders          # depot = 0, each order = 1 package
vehicle_capacities = [capacity] * num_couriers

routing.AddDimensionWithVehicleCapacity(
    demand_callback_index,
    0,                   # no slack
    vehicle_capacities,
    True,                # cumul starts at zero
    "Capacity",
)
```

This is a **hard constraint** — the solver cannot assign more than `capacity` orders to any single courier.

### Search strategy

| Parameter | Value |
|---|---|
| First solution | `PATH_CHEAPEST_ARC` |
| Local search | `GUIDED_LOCAL_SEARCH` (GLS) |
| Time limit | 15 seconds |

---

## External APIs

### OpenStreetMap Nominatim

Converts address strings to GPS coordinates.

- Endpoint: `https://nominatim.openstreetmap.org/search`
- Rate limit: respect Nominatim's 1 req/s usage policy
- Results cached in `geocode_cache.json` — each unique address string is only looked up once
- User-Agent: `FlowerRouteOptimizer/1.0`

### OSRM

Builds travel-time and distance matrix using real road network data.

- Endpoint: `http://router.project-osrm.org/table/v1/driving`
- Returns `durations[i][j]` in seconds and `distances[i][j]` in metres
- A single API call covers the full N×N matrix for all locations

---

## Common errors

| Error | Cause | Fix |
|---|---|---|
| `Could not geocode office address` | Nominatim could not find the depot | Check spelling; add the city name to the address |
| `Solver found no solution` | Time windows too tight or capacity too low | Widen windows, add couriers, or increase `--capacity` |
| `Impossible: N × M = K slots, but P orders` | Not enough courier slots for all orders | Increase `--couriers` or `--capacity` |
| `OSRM error` | OSRM public instance unreachable | Check internet connection; retry after a few seconds |
| `Warning: Could not geocode order N` | Nominatim found no match for that address | Fix the address in the CSV; the order is skipped |
