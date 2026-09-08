"""Container entrypoint for the pseint-judge worker image (todo 34).

Reads the PseInt program source from stdin into the tmpfs-backed /tmp, runs
the engine CLI with a report file, then prints program stdout followed by a
sentinel + the JSON report. The wrapper (scripts/run_sandboxed.py) splits
that stream into (output, report) without needing `docker cp`.

Stream format (UTF-8, container stdout)::

    <program stdout bytes>\n===REPORT===\n<JSON report>\n

Exit code: the engine CLI's exit code (0/1/2/3/4), so the wrapper can map
container exit codes to verdicts without re-parsing the report.

Per-case input (todo bug #1, plan §worker input plumbing):
    The wrapper sends ``source + INPUT_SENTINEL + input`` as the container's
    stdin (one stream, no filesystem coordination).  The entrypoint splits
    at the sentinel, writes the source half to ``/tmp/source.psc`` and the
    input half to ``/tmp/input.txt``, then passes
    ``--input /tmp/input.txt`` to the engine CLI.  When no sentinel is
    present (legacy behaviour, ``input=None``) the entrypoint treats the
    entire stdin as the source and skips ``--input`` (the engine then
    reads empty stdin — already consumed by the entrypoint).

Per-case step budget (todo bug #2, SPEC §(i)):
    The wrapper passes ``-e PIPELINE_MAX_STEPS=<N>`` to ``docker run`` when
    the worker computed a budget for the current test case.  This entrypoint
    reads that env var and forwards it to the engine CLI as
    ``--max-steps <N>``.  When the env var is unset (legacy callers), no
    flag is added — the engine defaults to unlimited steps.

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
INPUT_PATH = "/tmp/input.txt"
REPORT_PATH = "/tmp/report.json"
SENTINEL = b"\n===REPORT===\n"

#: Must match ``scripts/run_sandboxed.INPUT_SENTINEL``.  Separates the
#: program source from the per-case input in the container's stdin.
INPUT_SENTINEL = b"\n===PSEINT-INPUT===\n"

#: Must match ``scripts/run_sandboxed.PIPELINE_MAX_STEPS_ENV``.  The wrapper
#: passes ``-e PIPELINE_MAX_STEPS=<N>`` on ``docker run``; we read it here
#: and forward it as ``--max-steps N`` on the engine CLI argv.  When the
#: env var is absent (or unparseable), no flag is added and the engine
#: runs with its default unlimited step count.
PIPELINE_MAX_STEPS_ENV = "PIPELINE_MAX_STEPS"


def _split_source_and_input(payload: bytes) -> tuple[bytes, bytes | None]:
    """Split the wrapper-piped stdin into (source, input) at the sentinel.

    Returns ``(payload, None)`` when no sentinel is present (legacy,
    ``input=None``).  Splits at the FIRST occurrence only — the source
    bytes are not searched for the sentinel, so a literal ``b"===INPUT==="``
    in user code would not collide (we anchor on ``\n`` so the user would
    need an exact line break followed by the literal, which is extremely
    unlikely).
    """
    idx = payload.find(INPUT_SENTINEL)
    if idx < 0:
        return payload, None
    return payload[:idx], payload[idx + len(INPUT_SENTINEL):]


def _pipeline_max_steps_argv(env: dict[str, str] | None = None) -> list[str]:
    """Return the argv fragment for the engine CLI from the step-budget env.

    Reads ``PIPELINE_MAX_STEPS`` from the supplied ``env`` (or the live
    ``os.environ`` when ``None``) and returns ``["--max-steps", "<N>"]``
    when the value parses as a positive int; an empty list otherwise.  A
    malformed value (non-integer, negative, zero) is ignored — the engine
    will run without a budget rather than crash the entrypoint, and the
    wrapper's wall timeout is still the backstop.

    Pure function (no IO) so unit tests can drive it with a hand-built
    env dict and assert the engine CLI argv directly.
    """
    src = env if env is not None else os.environ
    raw = src.get(PIPELINE_MAX_STEPS_ENV)
    if not raw:
        return []
    try:
        n = int(raw)
    except ValueError:
        return []
    if n < 1:
        return []
    return ["--max-steps", str(n)]


def build_cmd(
    *,
    extra_args: list[str] | None = None,
    env: dict[str, str] | None = None,
) -> list[str]:
    """Build the engine CLI argv (testable without spawning subprocess).

    ``extra_args`` is the per-case input plumbing (``["--input", path]``
    when ``input_bytes`` is not None, else empty).  ``env`` is the env
    to read ``PIPELINE_MAX_STEPS`` from; defaults to ``os.environ`` for
    production calls.
    """
    return [
        sys.executable,
        "-m",
        "pseint_engine.cli",
        "run",
        SOURCE_PATH,
        *(extra_args or []),
        *_pipeline_max_steps_argv(env=env),
        "--report",
        REPORT_PATH,
    ]


def main() -> int:
    try:
        payload = sys.stdin.buffer.read()
    except OSError as e:
        sys.stderr.write(f"entrypoint: cannot read stdin: {e}\n")
        return 1

    source_bytes, input_bytes = _split_source_and_input(payload)

    try:
        with open(SOURCE_PATH, "wb") as f:
            f.write(source_bytes)
    except OSError as e:
        sys.stderr.write(f"entrypoint: cannot write {SOURCE_PATH}: {e}\n")
        return 1

    # Per-case input plumbing (todo bug #1): when the wrapper sent a sentinel
    # + input half, write the input to /tmp/input.txt and pass --input to
    # the engine CLI.  When no sentinel was present (legacy), skip the
    # extra flag and the input file (engine reads empty stdin — already
    # consumed by the entrypoint above).
    extra_args: list[str] = []
    if input_bytes is not None:
        try:
            with open(INPUT_PATH, "wb") as f:
                f.write(input_bytes)
        except OSError as e:
            sys.stderr.write(f"entrypoint: cannot write {INPUT_PATH}: {e}\n")
            return 1
        extra_args = ["--input", INPUT_PATH]

    cmd = build_cmd(extra_args=extra_args)
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
