# Flower Route Optimizer

Delivery route optimization tool for a flower business. Uploads a CSV of orders → geocodes addresses → builds a real-road travel-time matrix → finds the optimal multi-courier route respecting time windows and vehicle capacity → displays results on an interactive map.

---

## Quick start (Docker)

```bash
# Copy and fill in your secrets
cp .env.example .env          # add GOOGLE_MAPS_API_KEY if you have one

docker compose up --build
```

| Service | URL |
|---------|-----|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:8000 |
| Swagger | http://localhost:8000/docs |

> On first run Docker builds all images (~5 min). Subsequent starts are fast.

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

## API

### `POST /api/optimize`

multipart/form-data:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `file` | CSV | required | Orders file |
| `start_time` | string | `09:00` | Courier shift start `HH:MM` |
| `num_couriers` | integer | `1` | Number of couriers |
| `capacity` | integer | unlimited | Max packages per courier |

### `POST /api/recalculate`

Re-computes ETAs for a manually reordered route without re-running the solver.

### `GET /api/health`

Returns `{"status": "ok"}` — used by Docker health checks and CI.

---

## Project structure

```
flower_route_optimizer/
│
├── main.py                     # FastAPI server
├── requirements.txt            # all deps (dev + prod)
├── requirements-prod.txt       # runtime deps only (used in Docker)
│
├── Dockerfile                  # backend image (python:3.12-slim)
├── docker-compose.yml          # backend + frontend + Redis
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
│   └── matrix_service.py       # coordinates → time/distance matrix via OSRM
│
├── solver/
│   └── vrptw_solver.py         # OR-Tools VRPTW (KMeans++ + SAVINGS strategy)
│
├── models/order.py             # Order Pydantic model
├── utils/time_parser.py        # HH:MM ↔ seconds helpers
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
| `Impossible: N × M = K slots, but P orders` | Not enough courier slots | Increase couriers or capacity |
| `OSRM error` | OSRM public server unreachable | Check internet connection |
| `Warning: Could not geocode order N` | Address not found — order skipped | Fix the address in the CSV |
