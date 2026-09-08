# syntax=docker/dockerfile:1.7
# Frontend image for pseint-judge (todo 36).
#
# Multi-stage build: stage 1 installs deps + runs the Vite build; stage 2
# emits just the ``dist/`` directory.  Caddy in the compose stack mounts
# ``/srv`` from this image as its static root.
#
# The frontend package (``@pseint-judge/frontend``) is currently a Vite SPA
# with no SSR; ``npm run build`` writes to ``dist/`` by default.  We rely
# on the Caddyfile (todo 36) to handle SPA fallback for client-side routes
# (``/``, ``/login``, ``/problem/:id``, etc.).

FROM node:20-slim AS builder

WORKDIR /app

# Install deps first (separate layer for cache reuse).
COPY web/frontend/package.json web/frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund

# Copy source and build.
COPY web/frontend/ ./
# ``VITE_API_URL`` is baked into the static bundle at build time.  The
# default (empty string) makes the API client use **relative** URLs
# (e.g. ``/api/login``), which the browser resolves against the current
# origin and Caddy proxies to the api container.  This is the LOCAL-FIRST
# rule (plan §Success Criteria) — same-origin, no CORS dance.
#
# For an environment where the API lives on a different host (e.g. deploy
# behind a CDN), override at build time: ``docker compose build
# --build-arg VITE_API_URL=https://api.example.com`` and the bundle will
# emit absolute URLs to that origin.
ARG VITE_API_URL=""
ENV VITE_API_URL=${VITE_API_URL}
RUN npm run build

# --- Runtime stage ----------------------------------------------------------
FROM node:20-slim AS runtime

WORKDIR /srv

# Copy only the build output + the lang package (the @/ alias in vite.config
# resolves to web/frontend/src/lang, which is symlinked at build time; for a
# plain static deploy we just keep dist/).
COPY --from=builder /app/dist/ /srv/

# Non-root serving user.  We do NOT expose a port here — Caddy in the
# compose stack serves /srv on behalf of this image via a shared volume
# (see infra/docker-compose.yml).
RUN useradd --create-home --uid 65534 pseint || true \
    && chown -R 65534:65534 /srv
USER 65534:65534

# Default CMD is a no-op so `docker run` of this image alone is harmless;
# compose never runs the frontend container directly — Caddy reads /srv.
CMD ["sh", "-c", "echo 'frontend: static build, served by caddy' && sleep infinity"]