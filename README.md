# Flower Route Optimizer

Delivery route optimization tool for a flower business. Uploads a CSV of orders → geocodes addresses → builds a real-road travel-time matrix → finds the optimal multi-courier route respecting time windows and vehicle capacity → displays results on an interactive map.

---

## First-time setup

```bash
# Python deps
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Frontend deps
cd frontend && npm install && cd ..
```

---

## Running

### 1 — Backend

```bash
# From the project root
source venv/bin/activate
uvicorn main:app --reload --port 8000
```

API: `http://localhost:8000` · Swagger: `http://localhost:8000/docs`

### 2 — Frontend

```bash
# Second terminal, from the project root
cd frontend
npm run dev
```

Open **http://localhost:3000**

> If the backend is not running, the UI switches to demo mode with mock data automatically.

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
| `city` | yes | City name |
| `address` | yes | Street name |
| `house` | yes | House number (e.g. `12а`) |
| `time_start` | no | Earliest delivery time `HH:MM` |
| `time_end` | no | Latest delivery time `HH:MM` |

Empty `time_start` / `time_end` = flexible, no window constraint.

---

## API

`POST /api/optimize` — multipart/form-data:

| Field | Type | Default | Description |
|---|---|---|---|
| `file` | CSV | required | Orders file |
| `start_time` | string | `09:00` | Courier shift start `HH:MM` |
| `num_couriers` | integer | `1` | Number of couriers |
| `capacity` | integer | unlimited | Max packages per courier |

---

## Project structure

```
flower_route_optimizer/
│
├── main.py                     # FastAPI server (POST /api/optimize)
├── requirements.txt
│
├── frontend/                   # Next.js dashboard
│   └── src/
│       ├── app/page.tsx        # main page, state machine
│       ├── components/         # Header, OptimizationPanel, ProgressUI,
│       │                       # ResultsDashboard, StatsPanel, CourierCard,
│       │                       # RouteMap, RouteMapClient
│       ├── lib/api.ts          # fetch wrapper with mock fallback
│       └── types/index.ts      # shared TypeScript types
│
├── services/
│   ├── csv_service.py          # read orders from CSV
│   ├── geocoding_service.py    # address → (lat, lng) via Nominatim + cache
│   └── matrix_service.py       # coordinates → time/distance matrix via OSRM
│
├── solver/
│   └── vrptw_solver.py         # OR-Tools VRPTW solver
│
├── models/order.py             # Order Pydantic model
├── utils/time_parser.py        # HH:MM ↔ seconds helpers
├── scripts/run_optimizer.py    # CLI entry point
└── data/orders.csv             # sample orders
```

---

## Common errors

| Error | Cause | Fix |
|---|---|---|
| `Could not geocode office address` | Nominatim can't find the depot | Check spelling; include the city |
| `Solver found no solution` | Time windows too tight or capacity too low | Widen windows, add couriers, or increase capacity |
| `Impossible: N × M = K slots, but P orders` | Not enough courier slots | Increase couriers or capacity |
| `OSRM error` | OSRM public server unreachable | Check internet connection |
| `Warning: Could not geocode order N` | Address not found — order skipped | Fix the address in the CSV |
