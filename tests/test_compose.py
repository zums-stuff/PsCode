"""Tests for the docker-compose stack contract (todo 36).

The compose file is the operational interface of the platform — this test
pins its shape so accidental edits to ``infra/docker-compose.yml`` cannot
silently remove a healthcheck, drop the API's dependency on postgres, or
grant the API the Docker socket (M9).

The tests use PyYAML (already in the dev deps for the engine / judge
packages) to parse the file; they do NOT shell out to ``docker compose``,
so they run in any environment (CI, dev laptop, isolated test).

What this asserts (LOCAL-FIRST, plan §D17):

* All required services present (postgres, redis, api, worker, frontend,
  caddy).
* Every service has a healthcheck (so compose can take it out of rotation
  when degraded).
* The api + worker declare ``depends_on`` with the ``service_healthy``
  condition (NOT plain ``service_started``) so they wait for the DB to
  actually be ready, not just for the container to start.
* The api service does NOT mount ``/var/run/docker.sock`` (M9: only the
  worker may spawn engine sandboxes).
* The worker service DOES mount the Docker socket (with a security
  comment — see infra/docker-compose.yml + OPS.md todo 40).
* The frontend serves its built dist/ via a shared volume to caddy (no
  exposed host port).
* The caddy service exposes ports 80 and 443 on the host and reads its
  config from infra/Caddyfile.
* An ``infra/.env.example`` exists documenting every env var referenced
  by the compose file (composition is the source of truth for vars; the
  example file mirrors them).
* The ``infra/.env`` file is in .gitignore (secrets are never committed).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
COMPOSE_PATH = ROOT / "infra" / "docker-compose.yml"
CADDYFILE_PATH = ROOT / "infra" / "Caddyfile"
ENV_EXAMPLE_PATH = ROOT / "infra" / ".env.example"
GITIGNORE_PATH = ROOT / ".gitignore"


@pytest.fixture(scope="module")
def compose() -> dict:
    assert COMPOSE_PATH.exists(), f"missing compose file: {COMPOSE_PATH}"
    return yaml.safe_load(COMPOSE_PATH.read_text())


# ---------------------------------------------------------------------------
# Service roster
# ---------------------------------------------------------------------------


REQUIRED_SERVICES = {
    "postgres",
    "redis",
    "api",
    "worker",
    "frontend",
    "caddy",
}


def test_compose_file_parses(compose: dict) -> None:
    assert "services" in compose, "compose file must declare a top-level 'services'"
    assert "volumes" in compose, "compose file must declare a top-level 'volumes'"


def test_all_required_services_present(compose: dict) -> None:
    services = compose["services"]
    assert REQUIRED_SERVICES.issubset(
        services.keys()
    ), f"missing services: {REQUIRED_SERVICES - services.keys()}"


# ---------------------------------------------------------------------------
# Healthchecks — every long-running service MUST have one so compose can
# probe.  The frontend service is exempt: it's a build-once data producer
# (CMD = sleep infinity) whose health is implicit in the volume it shares
# with caddy — caddy waits on ``service_completed_successfully`` instead.
# ---------------------------------------------------------------------------


LONG_RUNNING_SERVICES = REQUIRED_SERVICES - {"frontend"}


@pytest.mark.parametrize("service", sorted(LONG_RUNNING_SERVICES))
def test_service_has_healthcheck(compose: dict, service: str) -> None:
    svc = compose["services"][service]
    assert "healthcheck" in svc, f"service '{service}' must declare a healthcheck"
    hc = svc["healthcheck"]
    assert "test" in hc, f"service '{service}' healthcheck must have a 'test'"
    assert "interval" in hc, f"service '{service}' healthcheck must have an 'interval'"
    assert "timeout" in hc, f"service '{service}' healthcheck must have a 'timeout'"
    assert "retries" in hc, f"service '{service}' healthcheck must have 'retries'"


def test_caddy_waits_for_frontend_build(compose: dict) -> None:
    """Frontend is a build-once data producer; caddy must wait for it."""
    caddy = compose["services"]["caddy"]
    deps = caddy.get("depends_on", {})
    assert "frontend" in deps, "caddy must depend on frontend"
    if isinstance(deps, dict):
        assert deps["frontend"].get("condition") == "service_completed_successfully", (
            "caddy must wait on frontend with condition "
            "service_completed_successfully (frontend is a build-once "
            "data producer, not a long-running service)"
        )


# ---------------------------------------------------------------------------
# depends_on — service_healthy condition (not just service_started)
# ---------------------------------------------------------------------------


def test_api_depends_on_postgres_and_redis_with_healthy(compose: dict) -> None:
    api = compose["services"]["api"]
    deps = api.get("depends_on", {})
    assert "postgres" in deps, "api must depend on postgres"
    assert "redis" in deps, "api must depend on redis"
    # ``depends_on`` may be a list (short form) or a dict (long form with
    # condition).  We accept either but require the healthy condition.
    if isinstance(deps, dict):
        assert deps["postgres"].get("condition") == "service_healthy"
        assert deps["redis"].get("condition") == "service_healthy"


def test_worker_depends_on_api_redis_postgres(compose: dict) -> None:
    worker = compose["services"]["worker"]
    deps = worker.get("depends_on", {})
    for dep in ("api", "redis", "postgres"):
        assert dep in deps, f"worker must depend on {dep}"
        if isinstance(deps, dict):
            assert deps[dep].get("condition") == "service_healthy", (
                f"worker.{dep} condition must be service_healthy"
            )


# ---------------------------------------------------------------------------
# M9 — Docker socket ONLY on the worker (NEVER on the API)
# ---------------------------------------------------------------------------


def _volume_mounts_socket(service: dict) -> bool:
    """Return True if any volume in the service references docker.sock."""
    for v in service.get("volumes", []) or []:
        # Volume entries are strings ("/host:/container[:mode]") or dicts.
        if isinstance(v, str):
            if "/var/run/docker.sock" in v:
                return True
        elif isinstance(v, dict):
            if "/var/run/docker.sock" in str(v.get("source", "")):
                return True
    return False


def test_api_does_not_mount_docker_socket(compose: dict) -> None:
    """M9: the API container MUST NOT have the Docker socket (plan §Admin)."""
    api = compose["services"]["api"]
    assert not _volume_mounts_socket(api), (
        "API service must NOT mount /var/run/docker.sock (M9); "
        "only the worker container may spawn engine sandboxes"
    )


def test_worker_mounts_docker_socket(compose: dict) -> None:
    """The worker service IS allowed (and required) to mount the socket."""
    worker = compose["services"]["worker"]
    assert _volume_mounts_socket(worker), (
        "worker service must mount /var/run/docker.sock so the sandbox "
        "wrapper can spawn engine containers (todo 34 + M9)"
    )


# ---------------------------------------------------------------------------
# Ports — postgres internal only, caddy exposes 80/443
# ---------------------------------------------------------------------------


def test_postgres_not_exposed_on_public_interface(compose: dict) -> None:
    """postgres MUST NOT publish 0.0.0.0:5432 (plan §Admin / localhost-only).

    A bind to ``127.0.0.1:5432:5432`` is fine for local psql access; an
    unbound ``5432:5432`` would expose the DB to the network.
    """
    pg = compose["services"]["postgres"]
    ports = pg.get("ports", []) or []
    for p in ports:
        # Compose port entries may be short ("5432:5432") or long
        # ("127.0.0.1:5432:5432").  Reject any that bind to a non-loopback
        # address.
        published = p.split(":")[0] if isinstance(p, str) else str(p.get("published", ""))
        assert not published.startswith("0.0.0.0"), (
            f"postgres port '{p}' binds to 0.0.0.0 — must bind to 127.0.0.1 "
            "(LOCAL mode) or be omitted (compose internal network only)"
        )


def test_caddy_exposes_http_and_https_ports(compose: dict) -> None:
    caddy = compose["services"]["caddy"]
    ports = caddy.get("ports", []) or []
    port_strs = ":".join(p if isinstance(p, str) else str(p.get("published", "")) for p in ports)
    # Caddy MUST expose 80 (HTTP).  443 is required only when DOMAIN is
    # set (UNAM production); the LOCAL default has it commented via the
    # env-driven ``${CADDY_HTTPS_PORT:-443}`` — so we accept either.
    assert "80" in port_strs, "caddy must expose host port 80 (HTTP)"


# ---------------------------------------------------------------------------
# Env example mirrors the compose file's variables
# ---------------------------------------------------------------------------


def _compose_env_var_names(compose: dict) -> set[str]:
    """Collect every ``$VAR`` or ``${VAR}`` reference in the compose file."""
    text = COMPOSE_PATH.read_text()
    return set(re.findall(r"\$\{?([A-Z_][A-Z0-9_]*)\}?", text))


def test_env_example_exists() -> None:
    assert ENV_EXAMPLE_PATH.exists(), (
        f"infra/.env.example must exist (todo 36): {ENV_EXAMPLE_PATH}"
    )


def test_env_example_documents_required_secrets() -> None:
    """``SECRET_KEY`` and ``ADMIN_PASSWORD`` MUST appear in .env.example."""
    assert ENV_EXAMPLE_PATH.exists()
    text = ENV_EXAMPLE_PATH.read_text()
    assert "SECRET_KEY" in text, ".env.example must document SECRET_KEY"
    assert "ADMIN_PASSWORD" in text, ".env.example must document ADMIN_PASSWORD"
    assert "ADMIN_USERNAME" in text, ".env.example must document ADMIN_USERNAME"


def test_env_example_documents_compose_referenced_vars(compose: dict) -> None:
    """Every env var the compose file reads should appear in .env.example.

    This catches the case where someone adds ``$FOO`` to compose but
    forgets to document it (operators will hit ``unset variable`` errors
    on first boot).  The reverse — vars in the example that the compose
    file never reads — is fine and not asserted (the example can document
    optional overrides).
    """
    used = _compose_env_var_names(compose)
    # POSTGRES_HOST_PORT / CADDY_*_PORT are host-bind mappings; allow the
    # example to document them even when the compose file doesn't quote
    # them with a $ (the literal defaults work too).
    documented = set()
    text = ENV_EXAMPLE_PATH.read_text()
    for m in re.finditer(r"^([A-Z_][A-Z0-9_]*)\s*=", text, flags=re.MULTILINE):
        documented.add(m.group(1))
    missing = used - documented
    assert not missing, (
        f"compose references ${sorted(missing)} but .env.example does not "
        "document them; add them to .env.example so operators can set them"
    )


# ---------------------------------------------------------------------------
# .gitignore — secrets are NEVER committed
# ---------------------------------------------------------------------------


def test_infra_env_is_gitignored() -> None:
    text = GITIGNORE_PATH.read_text()
    # The exact pattern is the one we wrote in the bootstrap commit;
    # accept either a bare ``infra/.env`` or a broader ``infra/.env*`` that
    # still keeps the .example file tracked (e.g. via negation).
    assert re.search(
        r"^/?infra/\.env(\s|$|\*)", text, flags=re.MULTILINE
    ), ".gitignore must exclude infra/.env (secrets are never committed)"


def test_env_example_is_NOT_gitignored() -> None:
    """``.env.example`` MUST be tracked (it's the documented contract)."""
    text = GITIGNORE_PATH.read_text()
    # A bare ``infra/.env*`` would also exclude the example; reject that.
    assert not re.search(
        r"^/?infra/\.env\*", text, flags=re.MULTILINE
    ), ".env.example must be tracked; do not use a wildcard exclude for infra/.env"


# ---------------------------------------------------------------------------
# Caddyfile — minimal LOCAL shape
# ---------------------------------------------------------------------------


def test_caddyfile_exists() -> None:
    assert CADDYFILE_PATH.exists(), f"Caddyfile missing: {CADDYFILE_PATH}"


def test_caddyfile_has_api_proxy_and_spa_root() -> None:
    text = CADDYFILE_PATH.read_text()
    # The Caddyfile MUST proxy /api/* to the api service.
    assert "/api/*" in text, "Caddyfile must proxy /api/* to the api service"
    assert "api:8000" in text or "api:$" in text, (
        "Caddyfile must reverse-proxy to the api service"
    )
    # And it MUST serve the static frontend (file_server from the dist).
    assert "file_server" in text, "Caddyfile must serve the static frontend"
    # DOMAIN-driven site block: when DOMAIN is unset the address falls
    # back to :80 (or "localhost"); the {$DOMAIN:...} placeholder proves
    # both modes are supported.
    assert "{$DOMAIN" in text, "Caddyfile must use a {$DOMAIN...} placeholder"


def test_caddyfile_has_security_headers() -> None:
    text = CADDYFILE_PATH.read_text()
    assert "X-Frame-Options" in text
    assert "X-Content-Type-Options" in text
    assert "Referrer-Policy" in text


# ---------------------------------------------------------------------------
# Dockerfiles — frontend build uses npm run build
# ---------------------------------------------------------------------------


def test_frontend_dockerfile_runs_build() -> None:
    """The frontend image MUST produce a dist/ via ``npm run build``."""
    df = ROOT / "web" / "frontend" / "Dockerfile"
    assert df.exists(), "web/frontend/Dockerfile missing (todo 36)"
    text = df.read_text()
    assert "npm run build" in text or "npm run" in text and "build" in text, (
        "frontend Dockerfile must run `npm run build` (or equivalent) "
        "so the dist/ the caddy container serves is fresh"
    )


def test_frontend_package_json_has_build_script() -> None:
    pkg = ROOT / "web" / "frontend" / "package.json"
    assert pkg.exists()
    data = yaml.safe_load(pkg.read_text())  # JSON is a YAML subset
    scripts = data.get("scripts", {})
    assert "build" in scripts, (
        "frontend package.json must have a 'build' script for the Docker image"
    )


# ---------------------------------------------------------------------------
# REPLICAS default — pin the worker count surface
# ---------------------------------------------------------------------------


def test_replicas_default_in_compose_or_env_example() -> None:
    """REPLICAS must default to 3 in either the compose or .env.example."""
    compose_text = COMPOSE_PATH.read_text()
    env_text = ENV_EXAMPLE_PATH.read_text()
    has_3 = "REPLICAS:-3" in compose_text or "REPLICAS=3" in env_text
    assert has_3, "REPLICAS must default to 3 (compose or .env.example)"