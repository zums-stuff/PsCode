# syntax=docker/dockerfile:1.7
# API image for pseint-judge (todo 36).
#
# Build context is the repo root (so the engine/, judge/, and web/api/ dirs
# are visible).  Install engine + judge + api + the uvicorn ASGI server;
# alembic migrations run from /app/web/api on first boot.
#
# Hardening contract (matches plan §Admin):
#   * python:3.11-slim — small base, no extras
#   * USER 65534:65534 — non-root
#   * NO Docker socket (plan §Admin / M9) — only the worker container may
#     spawn per-submission engine containers; the API just enqueues run_ids
#     onto the Redis ``pseint:runs`` list and serves REST + WebSocket.

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install engine, judge, and api packages in one layer.
# psycopg is already in web/api/pyproject deps; uvicorn is added here because
# the api package only lists runtime deps and uvicorn is the ASGI server.
COPY engine/ /app/engine/
COPY judge/ /app/judge/
COPY web/api/ /app/web/api/

RUN pip install --no-cache-dir \
        /app/engine \
        /app/judge \
        /app/web/api \
        "uvicorn[standard]>=0.27" \
    && pip cache purge \
    && rm -rf /app/engine /app/judge /app/web/api /root/.cache

# Non-root user (UID matches the engine sandbox image so the two share the
# same numeric identity on shared volumes / log inspection).
RUN useradd --create-home --uid 65534 pseint || true \
    && chown -R 65534:65534 /app
USER 65534:65534

WORKDIR /home/pseint

EXPOSE 8000

# uvicorn[standard] includes the ``uvicorn`` console script.  The API is a
# factory (``create_app``), so we use ``--factory`` so uvicorn imports the
# module and calls the function — no module-level app needed.
CMD ["uvicorn", "pseint_api.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]