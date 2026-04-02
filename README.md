# Flower Route Optimizer

Delivery route optimization service for a flower business. Accepts orders via CSV upload or JSON API → geocodes addresses → builds a real-road travel-time matrix via OSRM → solves the multi-courier Vehicle Routing Problem with Time Windows (VRPTW) → returns optimized routes with per-stop ETAs.

---

## Quick start (Docker)

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running

### 1 — Clone and configure

```bash
git clone https://github.com/isakawar/flower_route_optimizer.git
cd flower_route_optimizer

# Create .env from the example (Google Maps key is optional)
cp .env.example .env
```

Edit `.env` and set `GOOGLE_MAPS_API_KEY` if you have one (falls back to free Nominatim geocoding otherwise).

### 2 — Build and start

```bash
docker compose up --build
```

First build takes ~5 min (downloads base images, installs OR-Tools). Subsequent starts are fast.

### 3 — Open the app

| Service | URL |
|---------|-----|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:8001 |
| Swagger docs | http://localhost:8001/docs |

### Useful commands

```bash
# Start in background
docker compose up -d --build

# View logs
docker compose logs -f

# View logs for one service
docker compose logs -f backend

# Stop everything
docker compose down

# Stop and delete volumes (clears Redis geocode cache)
docker compose down -v

# Rebuild a single service after code change
docker compose build backend
docker compose up -d backend
```

---

## Local development (without Docker)

```bash
# Python deps
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Frontend deps
cd frontend && npm install && cd ..
```

### Backend

```bash
source venv/bin/activate
uvicorn main:app --reload --port 8000
```

### Frontend

```bash
cd frontend && npm run dev
```

Open **http://localhost:3000**

> If the backend is not running, the UI switches to demo mode with mock data automatically.

---

## Environment variables

Create a `.env` file in the project root (optional — the app starts without it):

```env
# Google Maps Geocoding API key (falls back to Nominatim/OSM if not set)
GOOGLE_MAPS_API_KEY=your_key_here

# Redis URL (auto-configured in Docker; leave unset for local file-based cache)
# REDIS_URL=redis://localhost:6379

# Optional API key to protect JSON endpoints from unauthorized access
# API_KEY=your_secret_key

# Comma-separated list of allowed CORS origins (default: http://localhost:3000)
# ALLOWED_ORIGINS=https://yourcrm.com,https://app.yourcrm.com
```

---

## Orders CSV format

```
id,city,address,house,delivery_window_start,delivery_window_end
1,Київ,вул. Хрещатик,1,10:00,12:00
2,Київ,просп. Перемоги,26,11:00,13:00
3,Буча,вул. Вокзальна,10,,
4,Бровари,вул. Київська,20,,
```

| Column | Required | Description |
|--------|----------|-------------|
| `id` | no | Unique integer order ID (auto-generated if omitted) |
| `city` | yes | City name |
| `address` | yes | Street name |
| `house` | yes | House number (e.g. `12а`) |
| `delivery_window_start` | no | Earliest delivery time `HH:MM` |
| `delivery_window_end` | no | Latest delivery time `HH:MM` |

Empty window columns = flexible, no time constraint.

---

## API Reference

Base URL: `http://localhost:8001` (or your deployed server)

> **Note:** In Docker, the backend is exposed on port **8001** (host) → 8000 (container). Use port 8001 for all API calls from outside Docker (CRM, curl, etc.).

### Authentication

All JSON endpoints (`/api/optimize/json`, `/api/recalculate`) support optional API key authentication.

Set `API_KEY` in your `.env` to enable it. When enabled, pass the key in the `X-Api-Key` header:

```
X-Api-Key: your_secret_key
```

If `API_KEY` is not set, all requests are allowed without authentication.

---

### `GET /api/health`

Health check. Used by Docker health checks and uptime monitors.

**Response `200`:**
```json
{ "status": "ok" }
```

---

### `POST /api/optimize`

Upload a CSV file and run route optimization. Uses `multipart/form-data`.

**Request fields:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `file` | file (CSV) | required | Orders file |
| `start_time` | string | `09:00` | Courier shift start `HH:MM` |
| `num_couriers` | integer | auto | Number of couriers (omit to auto-calculate minimum) |
| `capacity` | integer | unlimited | Max packages per courier |
| `time_buffer_min` | integer | `15` | Minutes subtracted from each time window end to avoid last-minute arrivals |

**Example (curl):**

```bash
curl -X POST http://localhost:8000/api/optimize \
  -F "file=@orders.csv" \
  -F "start_time=09:00" \
  -F "num_couriers=2" \
  -F "capacity=10" \
  -F "time_buffer_min=15"
```

**Response** — when Redis/RQ is available, returns a job ID for async polling:
```json
{
  "jobId": "a3f2b1c4-...",
  "status": "pending"
}
```

Poll `GET /api/jobs/{jobId}` until `status` is `"done"` (see below).

**Response** — when Redis is unavailable (local dev), returns result directly:
```json
{
  "jobId": "sync",
  "status": "done",
  "result": { ... }
}
```

---

### `GET /api/jobs/{jobId}`

Poll the status and result of an async optimization job.

**Response — still running:**
```json
{
  "status": "running",
  "progress": { "currentStep": "matrix" }
}
```

Progress steps: `geocode` → `matrix` → `optimize` → `finalize`

**Response — done (`200`):**
```json
{
  "status": "done",
  "result": { ... }
}
```

The `result` object has the same shape as the `/api/optimize/json` response (see below).

**Response — infeasible (`422`):**
```json
{
  "error": "INFEASIBLE",
  "message": "Неможливо виконати маршрут з 1 кур'єром(-ами). Потрібно мінімум 3.",
  "minimum_couriers_required": 3,
  "reason": "time_window_constraint"
}
```

**Response — failed (`500`):**
```json
{
  "status": "failed",
  "error": "Traceback ..."
}
```

---

### `POST /api/optimize/json`

**The recommended endpoint for CRM and server-to-server integrations.**

Accepts orders as a JSON array instead of a CSV file. Returns the result synchronously (no polling needed).

Requires `Content-Type: application/json`. Optionally protected by `X-Api-Key`.

**Request body:**

```json
{
  "orders": [
    {
      "id": 1,
      "city": "Київ",
      "address": "вул. Хрещатик",
      "house": "1",
      "delivery_window_start": "10:00",
      "delivery_window_end": "12:00"
    },
    {
      "id": 2,
      "city": "Київ",
      "address": "просп. Перемоги",
      "house": "26",
      "delivery_window_start": "11:00",
      "delivery_window_end": "13:30"
    },
    {
      "id": 3,
      "city": "Буча",
      "address": "вул. Вокзальна",
      "house": "10"
    }
  ],
  "start_time": "09:00",
  "num_couriers": 2,
  "capacity": 10,
  "time_buffer_min": 15
}
```

**Request fields:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `orders` | array | required | List of orders (see order fields below) |
| `start_time` | string | `"09:00"` | Courier shift start `HH:MM` |
| `num_couriers` | integer\|null | `null` | Number of couriers; `null` = auto-calculate minimum |
| `capacity` | integer\|null | `null` | Max packages per courier; `null` = unlimited |
| `time_buffer_min` | integer | `15` | Minutes subtracted from each window end as a safety buffer |

**Order fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | integer\|null | no | Order ID (auto-assigned if omitted) |
| `city` | string | yes | City name |
| `address` | string | yes | Street name |
| `house` | string | yes | House number |
| `delivery_window_start` | string\|null | no | Earliest delivery `HH:MM` |
| `delivery_window_end` | string\|null | no | Latest delivery `HH:MM` |

**Example (curl):**

```bash
curl -X POST http://localhost:8000/api/optimize/json \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: your_secret_key" \
  -d '{
    "orders": [
      {"id": 1, "city": "Київ", "address": "вул. Хрещатик", "house": "1", "delivery_window_start": "10:00", "delivery_window_end": "12:00"},
      {"id": 2, "city": "Київ", "address": "просп. Перемоги", "house": "26", "delivery_window_start": "11:00", "delivery_window_end": "13:30"},
      {"id": 3, "city": "Буча", "address": "вул. Вокзальна", "house": "10"}
    ],
    "start_time": "09:00",
    "num_couriers": 2
  }'
```

**Successful response `200`:**

```json
{
  "routes": [
    {
      "courierId": 1,
      "suggestedDepartureTime": "09:05",
      "totalDriveMin": 47,
      "totalDistanceKm": 18.3,
      "stops": [
        {
          "address": "Київ, вул. Хрещатик 1",
          "eta": "09:22",
          "driveMin": 17,
          "serviceMin": 15,
          "waitMin": 0,
          "lat": 50.4501,
          "lng": 30.5234,
          "timeStart": "10:00",
          "timeEnd": "11:45"
        },
        {
          "address": "Київ, просп. Перемоги 26",
          "eta": "09:55",
          "driveMin": 18,
          "serviceMin": 15,
          "waitMin": 0,
          "lat": 50.4587,
          "lng": 30.4936,
          "timeStart": "11:00",
          "timeEnd": "13:30"
        }
      ],
      "geometry": [
        [50.4422, 30.5367],
        [50.4480, 30.5290],
        "..."
      ]
    },
    {
      "courierId": 2,
      "suggestedDepartureTime": "09:00",
      "totalDriveMin": 35,
      "totalDistanceKm": 22.1,
      "stops": [
        {
          "address": "Буча, вул. Вокзальна 10",
          "eta": "09:35",
          "driveMin": 35,
          "serviceMin": 15,
          "waitMin": 0,
          "lat": 50.5393,
          "lng": 30.2275,
          "timeStart": null,
          "timeEnd": null
        }
      ],
      "geometry": null
    }
  ],
  "stats": {
    "totalDeliveries": 3,
    "totalDriveMin": 82,
    "totalDistanceKm": 40.4,
    "numCouriers": 2,
    "autoCouriers": false,
    "serviceTimePerStop": 15,
    "timeBufferMin": 15
  },
  "depot": {
    "lat": 50.4422,
    "lng": 30.5367
  },
  "droppedOrders": 0
}
```

**Response fields explained:**

| Field | Description |
|-------|-------------|
| `routes[].courierId` | Courier number (1-based) |
| `routes[].suggestedDepartureTime` | Optimal departure time from depot `HH:MM` |
| `routes[].totalDriveMin` | Total driving time in minutes (excluding service time) |
| `routes[].totalDistanceKm` | Total distance in km |
| `routes[].stops[].eta` | Arrival time at this stop `HH:MM` — **already accounts for 15-min service at all previous stops** |
| `routes[].stops[].driveMin` | Driving time from the previous location (depot or previous stop) in minutes |
| `routes[].stops[].serviceMin` | Service time at this stop in minutes (15 min — hand-over, signature, etc.) |
| `routes[].stops[].waitMin` | Wait time at this stop before the time window opens (if courier arrives early) |
| `routes[].stops[].timeStart` | Time window start `HH:MM` (from the order), or `null` |
| `routes[].stops[].timeEnd` | Effective time window end `HH:MM` (already adjusted by `time_buffer_min`), or `null` |
| `routes[].geometry` | Array of `[lat, lng]` polyline points for map drawing (OSRM road geometry), or `null` if unavailable |
| `stats.autoCouriers` | `true` if `num_couriers` was auto-calculated |
| `stats.serviceTimePerStop` | Service time per stop in minutes (always 15) |
| `droppedOrders` | Orders dropped because geocoding failed |

**How to compute consecutive stop times in your CRM:**

```
ETA(stop N) = ETA(stop N-1) + serviceMin(stop N-1) + driveMin(stop N)
```

Example:
- Stop 1 ETA: `09:22` (arrives, spends 15 min service)
- Stop 2 ETA: `09:22 + 15 min service + 18 min drive = 09:55` ✓

**Infeasible response `422`:**

```json
{
  "error": "INFEASIBLE",
  "message": "Неможливо виконати маршрут з 1 кур'єром(-ами). Потрібно мінімум 3.",
  "minimum_couriers_required": 3,
  "reason": "time_window_constraint"
}
```

Possible `reason` values: `"time_window_constraint"`, `"capacity_constraint"`

---

### `POST /api/recalculate`

Re-computes ETAs for already-assigned routes after manual stop reordering — **without re-running the full solver**. Useful when a dispatcher manually changes the stop order in the CRM.

Requires `Content-Type: application/json`. Optionally protected by `X-Api-Key`.

**Request body:**

```json
{
  "routes": [
    {
      "courierId": 1,
      "stops": [
        {
          "lat": 50.4501,
          "lng": 30.5234,
          "address": "Київ, вул. Хрещатик 1",
          "timeStart": "10:00",
          "timeEnd": "12:00"
        },
        {
          "lat": 50.4587,
          "lng": 30.4936,
          "address": "Київ, просп. Перемоги 26",
          "timeStart": "11:00",
          "timeEnd": "13:30"
        }
      ]
    },
    {
      "courierId": 2,
      "stops": [
        {
          "lat": 50.5393,
          "lng": 30.2275,
          "address": "Буча, вул. Вокзальна 10",
          "timeStart": null,
          "timeEnd": null
        }
      ]
    }
  ],
  "depot": {
    "lat": 50.4422,
    "lng": 30.5367
  },
  "startTime": "09:00"
}
```

**Request fields:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `routes` | array | required | Array of courier routes with ordered stops |
| `routes[].courierId` | integer | required | Courier identifier |
| `routes[].stops` | array | required | Ordered list of stops (lat/lng required) |
| `routes[].stops[].lat` | float | required | Stop latitude |
| `routes[].stops[].lng` | float | required | Stop longitude |
| `routes[].stops[].address` | string | required | Display address |
| `routes[].stops[].timeStart` | string\|null | no | Time window start `HH:MM` |
| `routes[].stops[].timeEnd` | string\|null | no | Time window end `HH:MM` |
| `depot` | object\|null | Kyiv depot | Depot coordinates `{"lat": ..., "lng": ...}` |
| `startTime` | string | `"09:00"` | Courier shift start `HH:MM` |

**Example (curl):**

```bash
curl -X POST http://localhost:8000/api/recalculate \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: your_secret_key" \
  -d '{
    "routes": [
      {
        "courierId": 1,
        "stops": [
          {"lat": 50.4501, "lng": 30.5234, "address": "Київ, вул. Хрещатик 1", "timeStart": "10:00", "timeEnd": "12:00"},
          {"lat": 50.4587, "lng": 30.4936, "address": "Київ, просп. Перемоги 26", "timeStart": null, "timeEnd": null}
        ]
      }
    ],
    "depot": {"lat": 50.4422, "lng": 30.5367},
    "startTime": "09:00"
  }'
```

**Successful response `200`:**

```json
{
  "routes": [
    {
      "courierId": 1,
      "totalDriveMin": 35,
      "totalDistanceKm": 12.6,
      "stops": [
        {
          "address": "Київ, вул. Хрещатик 1",
          "eta": "09:17",
          "driveMin": 17,
          "serviceMin": 15,
          "waitMin": 43,
          "lat": 50.4501,
          "lng": 30.5234,
          "timeStart": "10:00",
          "timeEnd": "12:00"
        },
        {
          "address": "Київ, просп. Перемоги 26",
          "eta": "10:33",
          "driveMin": 18,
          "serviceMin": 15,
          "waitMin": 0,
          "lat": 50.4587,
          "lng": 30.4936,
          "timeStart": null,
          "timeEnd": null
        }
      ],
      "geometry": [[50.4422, 30.5367], "..."]
    }
  ],
  "stats": {
    "totalDeliveries": 2,
    "totalDriveMin": 35,
    "totalDistanceKm": 12.6,
    "numCouriers": 1
  },
  "depot": {
    "lat": 50.4422,
    "lng": 30.5367
  }
}
```

> Note: `waitMin` shows how long the courier waits if they arrive before the time window opens. In the example above, the courier arrives at 09:17 but the window opens at 10:00, so they wait 43 minutes.

**Error responses:**

| HTTP | `error` | Description |
|------|---------|-------------|
| `422` | `INVALID_INPUT` | Empty routes, missing lat/lng, or invalid `startTime` |
| `503` | `OSRM_UNAVAILABLE` | Could not build travel-time matrix (OSRM unreachable) |

---

## Service time logic

Every delivery stop has a fixed **15-minute service time** (handing over the order, getting a signature, etc.).

- The `eta` field shows when the courier **arrives** at the stop (before service begins)
- Service time at a stop is reflected in the `serviceMin` field
- The `eta` for the **next** stop already includes the 15 minutes spent at the current stop

**Formula:**
```
ETA(stop 2) = ETA(stop 1) + serviceMin + driveMin(stop 2)
ETA(stop 3) = ETA(stop 2) + serviceMin + driveMin(stop 3)
```

Service time starts from the **first** delivery (it affects when the courier can leave for the second stop). No service time is added at the depot.

---

## Project structure

```
flower_route_optimizer/
│
├── main.py                     # FastAPI server + all HTTP endpoints
├── requirements.txt            # all deps (dev + prod)
├── requirements-prod.txt       # runtime deps only (used in Docker)
│
├── Dockerfile                  # backend image (python:3.12-slim)
├── docker-compose.yml          # backend + frontend + Redis + OSRM worker
├── .dockerignore
│
├── frontend/                   # Next.js 14 dashboard
│   ├── Dockerfile              # 3-stage build → standalone image
│   ├── next.config.mjs         # output: standalone, API rewrite
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
│   ├── geocoding_service.py    # address → (lat, lng); Redis cache with file fallback
│   ├── matrix_service.py       # coordinates → time/distance matrix via OSRM
│   └── feasibility.py          # pre-solve minimum couriers estimate
│
├── solver/
│   └── vrptw_solver.py         # OR-Tools VRPTW (KMeans++ + SAVINGS strategy)
│
├── models/order.py             # Order Pydantic model
├── utils/time_parser.py        # HH:MM ↔ seconds helpers
│
├── scripts/
│   └── run_optimizer.py        # CLI: CSV → print optimized routes (dev tool)
│
├── tests/                      # 94 pytest tests (88 fast + 6 slow property tests)
│   ├── conftest.py
│   ├── fixtures/
│   ├── test_api_optimize.py
│   ├── test_api_recalculate.py
│   ├── test_geocoding_service.py
│   ├── test_matrix_service.py
│   ├── test_solver_basic.py
│   ├── test_solver_capacity.py
│   ├── test_solver_time_windows.py
│   └── test_property.py        # @pytest.mark.slow (Hypothesis + OR-Tools)
│
└── .github/workflows/
    ├── tests.yml               # CI: run tests on push / PR to main
    └── deploy.yml              # CD: test → SSH deploy to VPS on push to main
```

---

## CI / CD

| Workflow | Trigger | What it does |
|----------|---------|--------------|
| `tests.yml` | push / PR → `main` | Runs 88 fast pytest tests |
| `deploy.yml` | push → `main` | Tests pass → SSH into VPS → `git pull` → `docker compose build` → `docker compose up -d` |

Required GitHub secrets for deploy:

| Secret | Description |
|--------|-------------|
| `VPS_HOST` | VPS IP or hostname |
| `VPS_USER` | SSH user |
| `VPS_SSH_KEY` | Private SSH key (the public key must be in `~/.ssh/authorized_keys` on the VPS) |

---

## Running tests

```bash
# Fast tests only (~9 min, default)
pytest

# Include slow property tests (~20 min extra)
pytest -m slow
```

---

## Common errors

| Error | Cause | Fix |
|-------|-------|-----|
| `Could not geocode office address` | Nominatim can't find the depot | Check spelling; include the city |
| `Solver found no solution` | Time windows too tight or capacity too low | Widen windows, add couriers, or increase capacity |
| `INFEASIBLE` (422) | Not enough courier slots for given constraints | Increase `num_couriers`, widen time windows, or increase `capacity` |
| `OSRM_UNAVAILABLE` (503) | OSRM server unreachable | Check internet connection or self-hosted OSRM container |
| `Warning: Could not geocode order N` | Address not found — order skipped | Fix the address in the CSV or JSON request |
