"""Container entrypoint for the pseint-judge worker image (todo 34).

Reads the PseInt program source from stdin into the tmpfs-backed /tmp, runs
the engine CLI with a report file, then prints program stdout followed by a
sentinel + the JSON report. The wrapper (scripts/run_sandboxed.py) splits
that stream into (output, report) without needing `docker cp`.

Stream format (UTF-8, container stdout)::

    <program stdout bytes>\n===REPORT===\n<JSON report>\n

Exit code: the engine CLI's exit code (0/1/2/3/4), so the wrapper can map
container exit codes to verdicts without re-parsing the report.

Why a Python entrypoint (not a shell script):
    * Plan says "no bash where possible MINIMAL deps" (todo 34).
    * No shell-quoting hazards with the source bytes (binary-safe stdin).
    * python:3.11-slim ships with Python; no extra apt packages.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

SOURCE_PATH = "/tmp/source.psc"
REPORT_PATH = "/tmp/report.json"
SENTINEL = b"\n===REPORT===\n"


def main() -> int:
    try:
        with open(SOURCE_PATH, "wb") as f:
            f.write(sys.stdin.buffer.read())
    except OSError as e:
        sys.stderr.write(f"entrypoint: cannot write {SOURCE_PATH}: {e}\n")
        return 1

    cmd = [
        sys.executable,
        "-m",
        "pseint_engine.cli",
        "run",
        SOURCE_PATH,
        "--report",
        REPORT_PATH,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, check=False)
    except OSError as e:
        sys.stderr.write(f"entrypoint: cannot exec engine CLI: {e}\n")
        return 1

    sys.stdout.buffer.write(result.stdout)
    sys.stdout.buffer.flush()

    try:
        with open(REPORT_PATH, "rb") as f:
            report_bytes = f.read()
    except OSError as e:
        sys.stderr.write(f"entrypoint: cannot read {REPORT_PATH}: {e}\n")
        return result.returncode or 1

    sys.stdout.buffer.write(SENTINEL)
    sys.stdout.buffer.write(report_bytes)
    if not report_bytes.endswith(b"\n"):
        sys.stdout.buffer.write(b"\n")
    sys.stdout.buffer.flush()

    if result.returncode != 0:
        return result.returncode

    try:
        json.loads(report_bytes)
    except json.JSONDecodeError:
        sys.stderr.write("entrypoint: report is not valid JSON\n")
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
        sys.exit(1)
