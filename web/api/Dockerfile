# syntax=docker/dockerfile:1.7
# API image for pseint-judge (todo 36).
#
# Build context is the repo root (so the engine/, judge/, infra/worker/ and
# web/api/ dirs are visible).  Install engine + judge + api + uvicorn +
# a thin ``infra.worker.jobs`` shim that the API uses to enqueue RQ jobs
# to the worker subprocess by module path.  alembic migrations run from
# /app/web/api on first boot.
#
# Hardening contract (matches plan §Admin):
#   * python:3.11-slim — small base, no extras
#   * USER 65534:65534 — non-root
#   * NO Docker socket (plan §Admin / M9) — only the worker container may
#     spawn per-submission engine containers; the API just enqueues run_ids
#     onto the RQ ``runs`` queue and serves REST + WebSocket.

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install engine, judge, api packages.  The ``infra.worker.jobs`` shim
# is NOT installed as a package — only its source files are copied into
# ``/app/infra/`` so the api container can ``import`` them at runtime.
# ``rq.Queue.enqueue("infra.worker.jobs.process_run", ...)`` needs the
# worker subprocess + the api to share the same import path; we set
# ``PYTHONPATH=/app`` in the runtime ENV so the import works without
# a real install of ``infra``.
COPY engine/ /app/engine/
COPY judge/ /app/judge/
COPY web/api/ /app/web/api/
COPY infra/ /app/infra/
COPY scripts/ /app/scripts/

ENV PYTHONPATH=/app
ENV RUN_SANDBOXED=/app/scripts/run_sandboxed.py

RUN pip install --no-cache-dir \
        /app/engine \
        /app/judge \
        /app/web/api \
        "uvicorn[standard]>=0.27" \
        "rq>=1.16" \
    && rm -rf /app/engine /app/judge /app/web/api /root/.cache
# Note: ``/app/infra`` and ``/app/scripts`` are NOT removed — the api
# needs ``infra.worker.jobs`` on PYTHONPATH (to enqueue RQ jobs by string
# path) and ``scripts.run_sandboxed`` is referenced by
# ``infra.worker.worker`` (which the api imports transitively via the
# jobs shim; the wrapper import path is resolved via
# ``importlib.util.spec_from_file_location`` at module import time).

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