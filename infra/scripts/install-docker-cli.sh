#!/usr/bin/env bash
# Install the Docker CLI static binary into /usr/local/bin/docker.
# Used by infra/Dockerfile.rqworker so the worker pool can spawn engine
# sandbox containers (the rqworker image is python:3.11-slim which ships
# Python but not docker). No curl / apt sources required.
#
# Env:
#   DOCKER_CLI_VERSION — version tag (default 28.4.0).

set -euo pipefail

VERSION="${DOCKER_CLI_VERSION:-28.4.0}"
ARCH="$(dpkg --print-architecture)"
case "$ARCH" in
    amd64) DOCKER_ARCH=x86_64 ;;
    arm64) DOCKER_ARCH=aarch64 ;;
    *) echo "unsupported arch: $ARCH" >&2; exit 1 ;;
esac

URL="https://download.docker.com/linux/static/stable/${DOCKER_ARCH}/docker-${VERSION}.tgz"
TMP_TGZ=/tmp/docker-cli.tgz
TMP_DIR=/tmp/docker-cli-extract

# python:3.11-slim ships urllib — use it instead of curl/wget.
python - <<PYEOF
import urllib.request
with open("${TMP_TGZ}", "wb") as f:
    with urllib.request.urlopen("${URL}") as resp:
        f.write(resp.read())
PYEOF

mkdir -p "${TMP_DIR}"
tar -xz -C "${TMP_DIR}" -f "${TMP_TGZ}"
mv "${TMP_DIR}/docker/docker" /usr/local/bin/docker
chmod 0555 /usr/local/bin/docker
rm -rf "${TMP_DIR}" "${TMP_TGZ}"

/usr/local/bin/docker --version