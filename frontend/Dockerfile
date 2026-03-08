# syntax=docker/dockerfile:1

# ── Stage 1: install all node_modules ────────────────────────────────────────
FROM node:20-alpine AS deps
WORKDIR /app

COPY package.json package-lock.json ./
# `npm ci` guarantees an exact, reproducible install from the lock file
RUN npm ci --ignore-scripts

# ── Stage 2: build Next.js app ────────────────────────────────────────────────
FROM node:20-alpine AS builder
WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY . .

# Build-time arg injected by docker-compose; sets the API rewrite target
ARG BACKEND_URL=http://localhost:8000
ENV BACKEND_URL=$BACKEND_URL
ENV NEXT_TELEMETRY_DISABLED=1
ENV NODE_ENV=production

# Ensure public/ exists so the COPY in the runner stage never fails
RUN mkdir -p /app/public && npm run build

# ── Stage 3: minimal production runner ───────────────────────────────────────
# output: "standalone" in next.config.mjs emits a self-contained server.js
# that does NOT need the full node_modules directory.
FROM node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

RUN addgroup --system nodejs \
    && adduser --system --ingroup nodejs nextjs

# Standalone server + static assets
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static   ./.next/static
COPY --from=builder --chown=nextjs:nodejs /app/public          ./public

USER nextjs

EXPOSE 3000

ENV PORT=3000
ENV HOSTNAME=0.0.0.0

CMD ["node", "server.js"]
