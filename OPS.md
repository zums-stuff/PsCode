# pseint-judge — Operations runbook (todo 40)

This runbook covers the operations the **plan does not automate** but an
operator (you, or whoever inherits the host) needs to know how to do.
Sections are intentionally copy-pasteable; commands assume `cwd = repo
root` and that `infra/.env` is populated.

The plan is **LOCAL-FIRST**: every section here is dry-runnable on a
developer laptop (`docker compose up -d` with DOMAIN unset → `http://localhost`).
UNAM production-only actions (real DOMAIN, ufw/fail2ban enforcement on a
public host, off-host backup cron, Caddy auto-renew confirmation) are
**documented here but never executed during the plan** — they go live when
the user provisions the production host (post-plan).

---

## 1. Deploy (fresh host)

```bash
# 1. clone
git clone <repo-url> pseint-judge && cd pseint-judge

# 2. populate infra/.env (NEVER commit)
cp infra/.env.example infra/.env
# Generate a real SECRET_KEY (>= 32 chars; the API refuses the example placeholder).
python -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(48))" >> infra/.env
# Set ADMIN_USERNAME + ADMIN_PASSWORD (used by bootstrap_admin on first migrate).
# Leave DOMAIN unset for LOCAL mode; set to e.g. judge.example.unam.mx for HTTPS.
$EDITOR infra/.env

# 3. build images (engine sandbox image first; the worker spawns it per submission)
docker build -f infra/Dockerfile.worker -t pseint-judge-worker:latest .
docker build -f web/api/Dockerfile -t pseint-judge-api:latest .
docker build -f web/frontend/Dockerfile -t pseint-judge-frontend:latest .

# 4. bring the stack up
cd infra && docker compose up -d && cd ..

# 5. run migrations (NOT automated in compose; see OPS.md §upgrade for the
#    "is it safe to run again?" rule)
docker compose -f infra/docker-compose.yml exec api alembic upgrade head

# 6. seed (admin + teacher + 1 class + 20 students + 4 problems + 1 contest)
python scripts/seed.py

# 7. probe
curl -sf http://localhost/healthz    # 200
curl -sf http://localhost/readyz     # 200 once DB + Redis are ready
```

After step 7 the platform is live. Visit `http://localhost` (LOCAL) or
`https://<DOMAIN>` (UNAM, when DOMAIN is set).

---

## 2. Upgrade (in-place)

```bash
# Pull the new code; rebuild the engine sandbox image first because the
# worker spawns it per submission.  If you skip this step, the worker
# spawns a stale engine image and `pseint-engine` invocations hit old code.
git pull
docker build -f infra/Dockerfile.worker -t pseint-judge-worker:latest .
docker build -f web/api/Dockerfile -t pseint-judge-api:latest .
docker build -f web/frontend/Dockerfile -t pseint-judge-frontend:latest .

# Recreate the api + worker + frontend containers so they pick up the new
# images.  Postgres + redis are NOT recreated (volume is preserved across
# container recreates).
cd infra
docker compose up -d --no-deps api worker frontend caddy

# Idempotent migrations: every migration is forward-only and writes its
# applied version to alembic_version.  Re-running on a fresh DB or after
# upgrade is safe; running on a downgraded version is NOT (alembic refuses).
docker compose exec api alembic upgrade head

# Probe.
curl -sf http://localhost/healthz
```

**Roll back** by checking out the previous tag and re-running the same
`docker compose up -d --no-deps ...` flow.  Postgres is forward-compatible
with the previous API because migrations are forward-only and the API does
not write to tables the previous API didn't know about.

---

## 3. Backup

```bash
# Local write to /var/backups/pseint/ (the default target; create the dir
# if it doesn't exist).  Output: pseint-YYYYMMDD-HHMMSS.sql.gz.  Files
# older than 7 days are pruned automatically.
scripts/backup.sh

# Custom target.
scripts/backup.sh /mnt/nfs/pseint-backups
```

The script runs `pg_dump` via `docker compose exec -T postgres pg_dump`
(no host postgres client required; the DB port does not need to be
exposed).  Output is plain SQL gzipped; `--no-owner --no-privileges` so
the dump restores cleanly on any postgres instance.

### 3.1 Off-host copy (UNAM prod-only)

The plan does NOT wire off-host copy automatically — that requires an
admin-chosen target (NFS, S3, scp to a remote host) that the operator
must supply.  Install a cron entry on the production host:

```cron
# /etc/cron.d/pseint-backup — daily 02:00 UTC, push off-host after local dump
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

0 2 * * * root cd /opt/pseint-judge && scripts/backup.sh /var/backups/pseint \
  && rsync -a --delete /var/backups/pseint/ backup@backup.example.unam.mx:/srv/pseint-judge/
```

Replace `backup@backup.example.unam.mx:/srv/pseint-judge/` with the
admin-chosen target.  The plan validates that `scripts/backup.sh` runs and
produces a dump; it does NOT run rsync against any specific host.

---

## 4. Restore drill

Run on a non-production host (or a scratch VM) to validate the backup
chain end-to-end.  The `--restore` mode creates a throwaway database so
the main `pseint` DB is never touched.

```bash
# 1. Pick the latest dump from /var/backups/pseint/.
ls -t /var/backups/pseint/pseint-*.sql.gz | head -1
#   /var/backups/pseint/pseint-20260115-020001.sql.gz

# 2. Restore into a scratch DB on the running compose stack.
scripts/backup.sh --restore /var/backups/pseint/pseint-20260115-020001.sql.gz
#   backup.sh: restoring /var/backups/pseint/pseint-20260115-020001.sql.gz into scratch DB pseint_restore_20260115-020301
#   backup.sh: ok — scratch DB ready: pseint_restore_20260115-020301
#     Connect:  (cd infra && docker compose exec -e PGPASSWORD=... postgres psql ...)
#     Promote:  ...
#     Drop:     ...

# 3. Spot-check the data.
(cd infra && docker compose exec -e PGPASSWORD=pseint postgres \
  psql -U pseint -d pseint_restore_20260115-020301 \
  -c 'SELECT count(*) FROM users; SELECT count(*) FROM problems;')

# 4. Drop the scratch DB when you're done.
(cd infra && docker compose exec postgres \
  psql -U pseint -d postgres -c 'DROP DATABASE pseint_restore_20260115-020301')
```

If the spot-check counts do not match your expectations, the backup
chain is broken; investigate the dump's `pg_dump` output and the cron
line above.

---

## 5. Worker resize (REPLICAS)

The `REPLICAS` env var drives the **in-process** RQ worker count inside
the worker container.  Standalone compose's `deploy.replicas: 1` is a
swarm-only no-op; the in-process count is what actually scales throughput
in the plan's single-host topology.

```bash
# Stop the worker, bump REPLICAS in infra/.env, restart.
$EDITOR infra/.env          # set REPLICAS=8 (default 3)
cd infra && docker compose up -d --no-deps worker && cd ..

# Verify the worker pool grew.
docker compose -f infra/docker-compose.yml exec worker \
  PYTHONPATH=/app python -c 'from infra.worker.worker import worker_count; print("workers:", worker_count())'
```

Rule of thumb: 1 worker per ~0.5 sustained submissions/sec on a 2-vCPU
host.  The load test (todo 37) hit 200 submissions in a burst with
`REPLICAS=3` and p95 < 60s on the developer's laptop — doubling REPLICAS
gives roughly double the burst headroom up to CPU saturation.

---

## 6. Password reset (admin endpoint)

The API has an admin-only password reset:

```bash
# Log in as the bootstrap admin (or any admin) to grab a token.
ADMIN_TOKEN=$(curl -sX POST http://localhost/api/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"<ADMIN_PASSWORD>"}' | python -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')

# Reset a student's password (user id 5 in this example).
curl -sX POST http://localhost/api/admin/users/5/reset-password \
  -H "Authorization: Bearer ${ADMIN_TOKEN}" \
  -H 'Content-Type: application/json' \
  -d '{"password":"<new-password>"}'
```

There is NO self-service password reset endpoint (the plan excludes
email service).  Admin-only reset is the supported path.

---

## 7. DB pool sizing

The API engine uses SQLAlchemy's default pool (5 connections + overflow).
This is fine for the load test (todo 37) at `REPLICAS=3`; under sustained
load you may see queue contention.

Two paths to scale:

**Path A — bump the SQLAlchemy pool** (in `web/api/src/pseint_api/db.py`):
```python
return create_engine(
    url or config.database_url(),
    pool_pre_ping=True,
    pool_size=int(os.environ.get("DB_POOL_SIZE", "10")),
    max_overflow=int(os.environ.get("DB_MAX_OVERFLOW", "20")),
)
```

**Path B — PgBouncer in front** (recommended once `REPLICAS > 10`):
PgBouncer sits between the API and postgres; the API points at PgBouncer
(typically port 6432), which multiplexes connections back to postgres.
This is documented but NOT deployed by the plan (single-host scale
boundary is the in-process pool + `REPLICAS`).

The plan's recommended ceiling is `REPLICAS=12` with `DB_POOL_SIZE=20`
before PgBouncer becomes worth the operational overhead.

---

## 8. Docker-socket access model (M9)

The plan's security invariant is: **only the worker container mounts
`/var/run/docker.sock`**.  The API has NO socket access — every request
that needs sandbox execution goes through the worker via RQ.

```bash
# Verify on a running host:
docker compose -f infra/docker-compose.yml ps --format json | python -c '
import json, sys
for svc in json.load(sys.stdin):
    if "/var/run/docker.sock" in (svc.get("Mounts") or []):
        print(f"socket mounted: {svc[\"Service\"]}")
'
# Expected output: "socket mounted: worker" (only)
```

If the API container ever shows up with the socket mounted, kill it
immediately and audit the `volumes:` block in `infra/docker-compose.yml`.
Mounting the socket in the API would let any HTTP request spawn arbitrary
host containers.

On the UNAM host, restrict the socket GID via a docker-compose override
(todo 40 plan §M9):

```yaml
# infra/docker-compose.override.yml (gitignored, local-only)
services:
  worker:
    group_add:
      - "${DOCKER_GID}"
```

Get the host's docker GID with `stat -c '%g' /var/run/docker.sock` and
set `DOCKER_GID=<that-value>` in `.env`.  This limits the socket mount
inside the worker to the host's docker group.

---

## 9. ufw default-deny (UNAM prod-only)

The plan validates locally without ufw.  On the production host:

```bash
# Default-deny inbound; allow SSH from admin scope, plus 80/443.
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow from <ADMIN_CIDR> to any port 22 proto tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable

# fail2ban for SSH (defense-in-depth; ufw alone is not enough against
# credential stuffing on the SSH port).
sudo apt install fail2ban
sudo systemctl enable --now fail2ban
# Default jail covers sshd; verify with:
sudo fail2ban-client status sshd
```

`ufw allow 80` is required for ACME http-01 challenges (Caddy obtains +
auto-renews the cert).  Do NOT open 5432 / 6379 / 8000 — those are
reachable only on the compose internal network.

---

## 10. Caddy auto-renew (UNAM prod-only)

Caddy obtains + auto-renews Let's Encrypt certs via ACME http-01 on port
80.  No action is required from the operator; the renewal is automatic.

To confirm:

```bash
docker compose -f infra/docker-compose.yml exec caddy \
  caddy list-modules | grep -i acme   # ACME module present

# Inspect the active cert.
docker compose -f infra/docker-compose.yml exec caddy \
  cat /data/caddy/certificates/acme-v02.api.letsencrypt.org-directory/<DOMAIN>/<DOMAIN>.crt | openssl x509 -noout -dates
#   notBefore=...
#   notAfter=...    # > 60 days means auto-renew is healthy
```

If `notAfter` is within 30 days and the cert hasn't auto-renewed, force a
renewal:

```bash
docker compose -f infra/docker-compose.yml exec caddy \
  caddy reload --config /etc/caddy/Caddyfile --address 2019
```

---

## 11. SECRET_KEY validation message

The API refuses to boot if `SECRET_KEY` is missing, shorter than 32 chars,
or matches the documented placeholder.  The exact message:

```
[pseint-api] refusing to boot: SECRET_KEY is not set. Generate one with:
python -c "import secrets; print(secrets.token_urlsafe(48))" and put it
in infra/.env (never commit it).
```

```
[pseint-api] refusing to boot: SECRET_KEY matches a documented placeholder
(e.g. 'replace-me-with-a-random-string-of-at-least-32-chars' from
infra/.env.example). Replace it with a real random value before booting;
refusing to start so a forgotten copy-paste cannot ship.
```

```
[pseint-api] refusing to boot: SECRET_KEY must be at least 32 chars; got
12. Generate one with: python -c "import secrets; print(secrets.token_urlsafe(48))"
```

The check fires at app construction time so the process exits before any
route is wired up; compose restarts the container, the operator sees the
message in `docker compose logs api`, and the fix is a one-line edit to
`infra/.env`.

---

## 12. CORS policy

`CORS_ALLOW_ORIGINS` (csv) defaults to empty — the API rejects
cross-origin browser calls outright.  In LOCAL mode (DOMAIN unset) the
frontend and API share an origin (Caddy reverse-proxy), so no CORS
allowlist is needed.

On the UNAM production host, set:

```
# infra/.env
CORS_ALLOW_ORIGINS=https://judge.example.unam.mx
```

Each origin must be an exact match (`scheme://host[:port]`).  Wildcards
are NOT supported; the middleware would emit a wildcard `Access-Control-
Allow-Origin` header that would also let credentialed requests through,
and the plan forbids that.

---

## 13. Structured logs

API logs are JSON, one line per event, with `ts`, `level`, `logger`,
`message`, `request_id` (when set by the request middleware).  Tail the
container log:

```bash
docker compose -f infra/docker-compose.yml logs -f api | jq .
# {"ts":"2026-01-15T02:00:01.001Z","level":"INFO","logger":"uvicorn.access","message":"...","request_id":"abc..."}
```

Caddy's access logs are also JSON (Caddy's default format).  When
correlating an end-user report, ask for the `X-Request-Id` header from
their browser dev tools and `grep` both `api` and `caddy` logs for it.

---

## 14. UNAM-only production actions (NOT executed during the plan)

These are documented but the plan deliberately does not execute them —
they require real provisioning on the production host:

- `ufw` default-deny + fail2ban (UNAM §9)
- Off-host backup cron (UNAM §3.1)
- Real DOMAIN set in `.env` → Caddy auto-HTTPS (UNAM §10)
- `DOCKER_GID` group_add override (UNAM §8)
- `CORS_ALLOW_ORIGINS=https://<DOMAIN>` (UNAM §12)
- DB pool tuning for > 12 REPLICAS (UNAM §7)

Acceptance for the plan stops at the LOCAL dry-run:
- `docker compose config --quiet` exit 0
- `curl -sf http://localhost:80/healthz` → 200
- `curl -sf http://localhost:80/readyz` → 200 (once DB + Redis are ready)
- `scripts/backup.sh` produces a dump file; `--restore` creates a
  working scratch DB
