# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base

# Disable .pyc files and force stdout/stderr flushing
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# OR-Tools requires libgomp (OpenMP runtime); pandas may need libgfortran on some archs
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# ── dependency layer (cached unless requirements.txt changes) ─────────────────
COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# ── application source ────────────────────────────────────────────────────────
# .dockerignore excludes venv/, tests/, frontend/, __pycache__, .git, etc.
COPY . .

# Drop root privileges
RUN addgroup --system app \
    && adduser --system --ingroup app --no-create-home app \
    && chown -R app:app /app

USER app

EXPOSE 8000

# Single worker: OR-Tools is memory-heavy; scale horizontally via replicas instead
CMD ["uvicorn", "main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1", \
     "--log-level", "info"]
