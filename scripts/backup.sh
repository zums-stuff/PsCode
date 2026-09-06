#!/usr/bin/env bash
# pseint-judge — postgres backup + restore helper (todo 40).
#
# Usage:
#   scripts/backup.sh                          # backup with default target
#   scripts/backup.sh /var/backups/pseint      # backup to custom target dir
#   scripts/backup.sh --restore <dump-file>    # restore <dump-file> into a
#                                              # scratch DB on the running
#                                              # compose stack (admin-only).
#   scripts/backup.sh --help                   # this message.
#
# Backups: pg_dump via `docker compose exec -T postgres pg_dump ...` so the
# script works without the host needing a postgres client or the DB port
# exposed.  Dumps land in $BACKUP_DIR (default /var/backups/pseint) with the
# timestamped name ``pseint-YYYYMMDD-HHMMSS.sql.gz``.  Old dumps are pruned to
# a 7-day window.
#
# Off-host copy is documented in OPS.md (todo 40 §backup restore drill):
# install a cron entry that runs `scripts/backup.sh` then `rsync`s the
# resulting file to an admin-chosen target outside the host.  This script
# does NOT push off-host by itself — the cron + rsync line in OPS.md is the
# canonical place to wire that.
#
# Restore: --restore creates a scratch database (``pseint_restore_<timestamp>``)
# on the running postgres container, loads the dump into it, and prints the
# connection URL so the operator can `psql` / diff / promote it.  The main
# ``pseint`` DB is NEVER touched.
#
# Env (read from .env, exported by `set -a` if the file exists):
#   POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB   — defaults: pseint/pseint/pseint
#   COMPOSE_DIR                                      — defaults: ../infra (this script's CWD-relative)
#   BACKUP_DIR                                       — defaults: $1 or /var/backups/pseint
#
# Failure mode: any unrecoverable error exits non-zero with a one-line reason
# on stderr.  Idempotent: rerunning the backup with the same minute timestamp
# overwrites the previous file.

set -euo pipefail

# ─── Paths / config ─────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
COMPOSE_DIR="${COMPOSE_DIR:-${REPO_ROOT}/infra}"

# Load .env (if present) without exporting secrets into the calling shell.
if [[ -f "${COMPOSE_DIR}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${COMPOSE_DIR}/.env"
  set +a
fi

POSTGRES_USER="${POSTGRES_USER:-pseint}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-pseint}"
POSTGRES_DB="${POSTGRES_DB:-pseint}"

RETENTION_DAYS=7

# ─── Arg parsing ────────────────────────────────────────────────────────────
print_help() {
  sed -n '2,29p' "$0"
}

RESTORE_FILE=""
TARGET_DIR=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --help|-h)
      print_help
      exit 0
      ;;
    --restore)
      if [[ $# -lt 2 ]]; then
        echo "backup.sh: --restore requires a dump-file argument" >&2
        exit 2
      fi
      RESTORE_FILE="$2"
      shift 2
      ;;
    --restore=*)
      RESTORE_FILE="${1#--restore=}"
      shift
      ;;
    -*)
      echo "backup.sh: unknown flag: $1" >&2
      exit 2
      ;;
    *)
      TARGET_DIR="$1"
      shift
      ;;
  esac
done

# ─── Helpers ────────────────────────────────────────────────────────────────
_compose() {
  ( cd "${COMPOSE_DIR}" && docker compose "$@" )
}

_require_compose_dir() {
  if [[ ! -d "${COMPOSE_DIR}" ]]; then
    echo "backup.sh: COMPOSE_DIR does not exist: ${COMPOSE_DIR}" >&2
    exit 1
  fi
  if [[ ! -f "${COMPOSE_DIR}/docker-compose.yml" ]]; then
    echo "backup.sh: no docker-compose.yml in ${COMPOSE_DIR}" >&2
    exit 1
  fi
}

_require_docker() {
  if ! command -v docker >/dev/null 2>&1; then
    echo "backup.sh: docker not found on PATH" >&2
    exit 1
  fi
  if ! docker info >/dev/null 2>&1; then
    echo "backup.sh: docker daemon unreachable (is the service running? socket perms ok?)" >&2
    exit 1
  fi
}

_pg_exec() {
  # Run psql inside the compose postgres container.
  _compose exec -T -e PGPASSWORD="${POSTGRES_PASSWORD}" postgres psql -U "${POSTGRES_USER}" -d "$1" -v ON_ERROR_STOP=1 -t -A "$2"
}

_pg_dump() {
  # Stream pg_dump output (custom-format, compressed) to stdout.
  _compose exec -T -e PGPASSWORD="${POSTGRES_PASSWORD}" postgres \
    pg_dump -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" --no-owner --no-privileges
}

_timestamp() {
  date -u +"%Y%m%d-%H%M%S"
}

# ─── Backup mode ────────────────────────────────────────────────────────────
do_backup() {
  _require_compose_dir
  _require_docker

  local target="${TARGET_DIR:-${BACKUP_DIR:-/var/backups/pseint}}"
  if [[ "${target}" == "/var/backups/pseint" && ! -d "${target}" && -w "$(dirname "${target}")" ]]; then
    echo "backup.sh: creating ${target}" >&2
    mkdir -p "${target}"
  fi
  mkdir -p "${target}"

  local stamp
  stamp="$(_timestamp)"
  local outfile="${target}/pseint-${stamp}.sql.gz"

  echo "backup.sh: writing ${outfile}" >&2
  # shellcheck disable=SC2086
  _pg_dump | gzip -9 > "${outfile}"
  chmod 600 "${outfile}"

  # 7-day retention: drop any dump file older than RETENTION_DAYS.
  local pruned=0
  while IFS= read -r -d '' old; do
    rm -f -- "${old}"
    pruned=$((pruned + 1))
  done < <(find "${target}" -maxdepth 1 -type f -name 'pseint-*.sql.gz' -mtime +"${RETENTION_DAYS}" -print0 2>/dev/null || true)

  echo "backup.sh: ok (pruned ${pruned} dump(s) older than ${RETENTION_DAYS}d)" >&2
  echo "${outfile}"
}

# ─── Restore mode ───────────────────────────────────────────────────────────
do_restore() {
  _require_compose_dir

  local dump="$1"
  if [[ ! -f "${dump}" ]]; then
    echo "backup.sh: dump file not found: ${dump}" >&2
    exit 1
  fi

  _require_docker

  local scratch_db="pseint_restore_$(_timestamp)"
  echo "backup.sh: restoring ${dump} into scratch DB ${scratch_db}" >&2

  # Recreate the scratch DB fresh.
  _pg_exec postgres "DROP DATABASE IF EXISTS ${scratch_db};" >/dev/null
  _pg_exec postgres "CREATE DATABASE ${scratch_db};" >/dev/null

  # Stream the dump (gunzip on the fly) into psql inside the running
  # postgres container via `docker compose exec`.  We use `docker compose
  # exec -T` (no TTY) so the pipeline can carry binary-safe bytes; psql's
  # ON_ERROR_STOP=1 aborts the restore on the first failed statement and
  # surfaces the error on stderr so the script's `set -e` catches it.
  if ! gunzip -c "${dump}" | _compose exec -T \
      -e PGPASSWORD="${POSTGRES_PASSWORD}" \
      postgres \
      psql -U "${POSTGRES_USER}" -d "${scratch_db}" -v ON_ERROR_STOP=1; then
    echo "backup.sh: restore failed; the scratch DB ${scratch_db} exists but is partial" >&2
    exit 1
  fi

  # Confirm the scratch DB is present and reachable.
  if _pg_exec postgres "SELECT 1 FROM pg_database WHERE datname='${scratch_db}'" | grep -q '^1$'; then
    cat <<EOF
backup.sh: ok — scratch DB ready: ${scratch_db}
  Connect:  (cd ${COMPOSE_DIR} && docker compose exec -e PGPASSWORD=${POSTGRES_PASSWORD} postgres psql -U ${POSTGRES_USER} -d ${scratch_db})
  Promote:  (cd ${COMPOSE_DIR} && docker compose exec postgres pg_dump -U ${POSTGRES_USER} -d ${scratch_db} --no-owner --no-privileges | gzip > /var/backups/pseint/${scratch_db}.sql.gz)
  Drop:     (cd ${COMPOSE_DIR} && docker compose exec postgres psql -U ${POSTGRES_USER} -d postgres -c 'DROP DATABASE ${scratch_db}')
EOF
  else
    echo "backup.sh: restore failed (scratch DB not present); inspect compose logs postgres" >&2
    exit 1
  fi
}

# ─── Dispatch ───────────────────────────────────────────────────────────────
if [[ -n "${RESTORE_FILE}" ]]; then
  do_restore "${RESTORE_FILE}"
else
  do_backup
fi
