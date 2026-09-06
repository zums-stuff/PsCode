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