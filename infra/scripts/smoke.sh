#!/usr/bin/env bash
# smoke.sh — minimal health smoke for the local pseint-judge stack (todo 36).
#
# Run after `docker compose up -d` from the `infra/` directory.  Exits 0
# when /healthz + /readyz on the Caddy front port both return 200; exits
# non-zero (with diagnostics) otherwise.  No test framework dependency —
# this is a CI-friendly one-shot probe.
#
# Usage:
#     cd infra && docker compose up -d
#     ./scripts/smoke.sh                # probe http://localhost:80
#     BASE_URL=http://localhost:8080 ./scripts/smoke.sh   # custom port
#     ./scripts/smoke.sh --verbose      # print every response

set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:80}"
VERBOSE=0
for arg in "$@"; do
    case "$arg" in
        --verbose|-v) VERBOSE=1 ;;
        --help|-h)
            sed -n '2,15p' "$0"
            exit 0
            ;;
        *) echo "unknown arg: $arg" >&2; exit 2 ;;
    esac
done

probe() {
    local path="$1" expected_status="$2"
    local url="${BASE_URL}${path}"
    local tmp
    tmp=$(mktemp)
    local code
    code=$(curl -sS -o "$tmp" -w "%{http_code}" --max-time 5 "$url" || echo "000")
    if [ "$VERBOSE" = "1" ]; then
        echo "→ ${url}"
        echo "  status: ${code}"
        echo "  body:   $(head -c 400 "$tmp")"
        echo
    fi
    if [ "$code" != "$expected_status" ]; then
        echo "FAIL ${path}: expected ${expected_status}, got ${code}" >&2
        echo "  body: $(head -c 400 "$tmp")" >&2
        rm -f "$tmp"
        exit 1
    fi
    rm -f "$tmp"
    echo "OK ${path} → ${code}"
}

echo "smoke: ${BASE_URL}"
probe "/healthz" 200
# readyz may be 200 (full stack healthy) or 503 (partial — e.g. just
# started, redis still booting).  We accept both and print whichever.
ready_code=$(curl -sS -o /tmp/readyz_body -w "%{http_code}" --max-time 5 "${BASE_URL}/readyz" || echo "000")
echo "INFO /readyz → ${ready_code}"
if [ "$ready_code" = "200" ]; then
    echo "OK /readyz → 200"
elif [ "$ready_code" = "503" ]; then
    echo "WARN /readyz → 503 (degraded; check deps in compose stack)"
    cat /tmp/readyz_body
    echo
else
    echo "FAIL /readyz: expected 200/503, got ${ready_code}" >&2
    cat /tmp/readyz_body >&2
    echo >&2
    rm -f /tmp/readyz_body
    exit 1
fi
rm -f /tmp/readyz_body

echo "smoke: all probes passed"