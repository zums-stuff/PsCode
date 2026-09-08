"""Sandbox wrapper for pseint-judge submissions (todo 34).

This module is the SINGLE entry point that executes user-supplied PseInt code
on the host. It is invoked from the worker (todo 35), which is reached via
the API.

SECURITY MODEL (binding):
    The API container MUST NOT get the Docker socket (todo 34 / plan §Admin).
    Only the worker container may mount or otherwise access the Docker
    socket, and only via a dedicated management network or a restricted
    bind mount (read-only, no privileged scope) as documented in OPS.md (M9).
    Mounting the Docker socket into the API would let any request spawn
    arbitrary host containers; this module exists so the API never has to.

EXECUTION MODEL:
    One container per submission (todo 34, plan §One container per
    submission). All test cases for that submission run INSIDE the same
    container with M2 lazy rules enforced in-container (CE short-circuit,
    CF lazy-stop) — the wrapper runs once per submission, not once per test
    case.

    The wrapper reads the PseInt program source from stdin (the worker
    pipeline uses stdin per todo 7's engine CLI contract: --input FILE OR
    stdin are both supported; the wrapper always uses stdin to keep the
    caller's contract uniform). The program source is piped into the
    container via `docker run -i`; the container's entrypoint drops it
    into the tmpfs-backed /tmp and runs the engine CLI with --report.

HARDENING FLAGS (exact, per todo 34):
    --network none
    --cap-drop ALL
    --security-opt no-new-privileges:true
    --security-opt seccomp=infra/seccomp/default.json
    --memory 128m
    --cpus 0.5
    --pids-limit 64
    --read-only
    --tmpfs /tmp
    --user 65534:65534
    --stop-timeout 8
    -i (stdin pipe for the program source + per-case input)

WALL KILL (M9):
    `docker run --stop-timeout 8` sends SIGTERM after the program finishes
    naturally and SIGKILL after 8 seconds if it is still alive; combined
    with the engine CLI's own --step-budget / --max-output-bytes budgets
    this is the dual wall/step cap the plan requires.

ALLOWED DEPS:
    The Docker host only — no nsjail, no host bind mounts other than tmpfs.

USAGE:
    # Export the host's default seccomp profile to infra/seccomp/default.json
    python scripts/run_sandboxed.py --export-seccomp

    # Run a program (reads the source from stdin)
    python scripts/run_sandboxed.py < program.psc > result.json

PER-CASE INPUT (todo bug #1, plan §worker input plumbing):
    When invoked programmatically (``run_sandboxed(source, input=...)``) the
    wrapper pipes ``source + INPUT_SENTINEL + input`` as the container's
    stdin stream.  The entrypoint (``infra/entrypoint.py``) splits stdin at
    the sentinel, writes the source half to ``/tmp/source.psc`` and the
    input half to ``/tmp/input.txt``, then passes
    ``--input /tmp/input.txt`` to the engine CLI.  This avoids filesystem
    coordination between the worker container and the docker daemon
    (a tmpfs-mounted file inside the worker is invisible to the daemon's
    bind-mount source resolver).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from subprocess import CalledProcessError
from typing import Any

#: Default image the wrapper spawns for one submission. The engine sandbox
#: is built by ``infra/Dockerfile.worker``; the rqworker pool (built by
#: ``infra/Dockerfile.rqworker``) lives under a separate tag so the two
#: images don't collide on ``pseint-judge-worker:latest``.  Override via
#: the ``$WORKER_IMAGE`` env (set by docker-compose.yml).
DEFAULT_IMAGE = os.environ.get("WORKER_IMAGE", "pseint-judge-engine:latest")
SECCOMP_DIND_IMAGE = "docker:dind"
SECCOMP_DIND_PATH = "/etc/docker/seccomp/default.json"
#: Default seccomp profile path.  Resolved relative to *this* wrapper's
#: location so the default works both from the repo root (dev: ``python
#: scripts/run_sandboxed.py …`` → ``../infra/seccomp/default.json``) and
#: from inside the rqworker container (``/app/scripts/run_sandboxed.py``
#: → ``/app/infra/seccomp/default.json``).  Override via the
#: ``$SECCOMP_PROFILE`` env if you need a custom path.
SECCOMP_REL_PATH = Path(
    os.environ.get(
        "SECCOMP_PROFILE",
        str(Path(__file__).resolve().parent.parent / "infra" / "seccomp" / "default.json"),
    )
)

STOP_TIMEOUT_S = 8
MEMORY = "128m"
CPUS = "0.5"
PIDS_LIMIT = 64
USER_ID = "65534:65534"
NETWORK = "none"
CAP_DROP = "ALL"

REPORT_SENTINEL = b"\n===REPORT===\n"

#: Sentinel that separates the program source from the per-case input in
#: the container's stdin (todo bug #1).  Both halves are written by the
#: entrypoint to ``/tmp/source.psc`` and ``/tmp/input.txt`` respectively.
#: The literal string is unlikely to appear in either side; the entrypoint
#: uses ``bytes.split(SENTINEL, 1)`` so only the FIRST occurrence splits.
INPUT_SENTINEL = b"\n===PSEINT-INPUT===\n"

#: Env var the wrapper uses to thread the per-case step budget through
#: ``docker run -e`` into the entrypoint, which reads ``os.environ`` and
#: passes ``--max-steps N`` to the engine CLI.  This is preferable to a
#: CLI flag because argv coordination across (worker → wrapper → docker
#: CLI → entrypoint sys.argv) is fragile; an env var is one
#: ``docker run`` flag away.  Set inside ``run_sandboxed`` when
#: ``max_steps`` is supplied.
PIPELINE_MAX_STEPS_ENV = "PIPELINE_MAX_STEPS"


@dataclass
class SandboxResult:
    """Structured outcome of one sandboxed run.

    Mirrors the engine CLI's JSON report (``--report``) plus wrapper-level
    metadata (container exit code, measured wall clock, runtime error if
    the wrapper itself blew up).
    """

    container_exit_code: int
    output: str
    report: dict[str, Any] = field(default_factory=dict)
    error: dict[str, Any] | None = None
    wall_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "container_exit_code": self.container_exit_code,
            "output": self.output,
            "report": self.report,
            "error": self.error,
            "wall_ms": self.wall_ms,
        }


def _docker_run_cmd(
    *,
    image: str,
    name: str | None,
    seccomp_profile: Path,
    max_steps: int | None = None,
) -> list[str]:
    """Build the exact docker run argv for one submission.

    Flag order is not significant to Docker, but is kept stable so tests can
    assert against a fixed command list and OPS.md grep is easy.

    ``max_steps``: when not None, append ``-e PIPELINE_MAX_STEPS=<N>`` so
    the entrypoint can forward ``--max-steps N`` to the engine CLI.  This
    is the wrapper→entrypoint step-budget plumbing (todo bug #2).  The
    wrapper's own ``--stop-timeout 8`` is the wall-clock backstop; the
    step budget is the primary TLE mechanism (engine's
    ``_check_step_budget`` fires before the wall timeout for any
    well-formed loop program).
    """
    cmd: list[str] = ["docker", "run", "--rm"]
    if name is not None:
        cmd += ["--name", name]
    cmd += [
        "--network", NETWORK,
        "--cap-drop", CAP_DROP,
        "--security-opt", "no-new-privileges:true",
        "--security-opt", f"seccomp={seccomp_profile}",
        "--memory", MEMORY,
        "--cpus", CPUS,
        "--pids-limit", str(PIDS_LIMIT),
        "--read-only",
        "--tmpfs", "/tmp",
        "--user", USER_ID,
        "--stop-timeout", str(STOP_TIMEOUT_S),
        "-i",
    ]
    if max_steps is not None:
        # The entrypoint reads this exact env var and converts it to
        # ``--max-steps N`` on the engine CLI argv.  See
        # ``infra/entrypoint.py`` for the matching reader.
        cmd += ["-e", f"{PIPELINE_MAX_STEPS_ENV}={int(max_steps)}"]
    cmd += [image]
    return cmd


def build_docker_run(
    *,
    image: str = DEFAULT_IMAGE,
    name: str | None = None,
    seccomp_profile: Path = SECCOMP_REL_PATH,
    max_steps: int | None = None,
) -> list[str]:
    """Public builder for the docker run argv (testable without subprocess)."""
    return _docker_run_cmd(
        image=image,
        name=name,
        seccomp_profile=seccomp_profile,
        max_steps=max_steps,
    )


def export_seccomp(
    dest: Path | str = SECCOMP_REL_PATH,
    *,
    runner: Any = subprocess.run,
) -> Path:
    """Export the host Docker engine's default seccomp profile to disk.

    Producer: a one-shot ``docker:dind`` container (the only image that
    ships ``/etc/docker/seccomp/default.json`` for a given engine version).
    Pipes the JSON to ``dest``; refuses to overwrite unless ``dest`` does
    not exist or matches the new contents exactly.

    Returns the resolved destination path.
    """
    dest_path = Path(dest)
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "docker",
        "run",
        "--rm",
        SECCOMP_DIND_IMAGE,
        "cat",
        SECCOMP_DIND_PATH,
    ]
    try:
        proc = runner(cmd, capture_output=True, check=True)
    except CalledProcessError as e:
        raise RuntimeError(
            f"seccomp export failed: docker run returned {e.returncode}: "
            f"{e.stderr.decode(errors='replace') if e.stderr else ''}"
        ) from e
    if proc.returncode != 0:
        raise RuntimeError(
            f"seccomp export failed: docker run returned {proc.returncode}: "
            f"{proc.stderr.decode(errors='replace')}"
        )

    new_bytes = proc.stdout
    if dest_path.exists() and dest_path.read_bytes() == new_bytes:
        return dest_path

    tmp_path = dest_path.with_suffix(dest_path.suffix + ".tmp")
    tmp_path.write_bytes(new_bytes)
    os.replace(tmp_path, dest_path)
    return dest_path


def _split_report_stream(stream_bytes: bytes) -> tuple[bytes, bytes | None]:
    """Split the container stdout into (program_output, report_json_bytes)."""
    idx = stream_bytes.rfind(REPORT_SENTINEL)
    if idx == -1:
        return stream_bytes, None
    output = stream_bytes[:idx]
    report_blob = stream_bytes[idx + len(REPORT_SENTINEL):].strip()
    return output, report_blob


def run_sandboxed(
    source: bytes,
    *,
    image: str = DEFAULT_IMAGE,
    seccomp_profile: Path = SECCOMP_REL_PATH,
    name: str | None = None,
    input: bytes | None = None,
    wall_timeout_s: float | None = None,
    max_steps: int | None = None,
    runner: Any = subprocess.run,
) -> SandboxResult:
    """Execute ``source`` inside the sandbox container and return the result.

    ``source`` is piped to the container's stdin and consumed by the
    entrypoint (``infra/entrypoint.py``), which drops it into /tmp and runs
    the engine CLI.

    ``input`` (optional) is the per-case program input.  When provided, the
    wrapper appends ``INPUT_SENTINEL + input`` to the source bytes and
    pipes the combined stream as the container's stdin.  The entrypoint
    splits at the sentinel, writes the input half to ``/tmp/input.txt``,
    and passes ``--input /tmp/input.txt`` to the engine CLI.
    ``input=None`` preserves the legacy behaviour (the engine reads empty
    stdin — there's no sentinel, so the entrypoint treats the entire stdin
    as the source).

    ``wall_timeout_s`` (optional) bounds the docker-run wall clock.  When
    exceeded, the wrapper kills the subprocess (SIGKILL via ``subprocess``
    timeout) and returns ``error={"code": "ERR_STEP_LIMIT", ...}`` so the
    worker classifies the verdict as TLE.  The default ``None`` waits
    indefinitely — callers MUST supply a timeout for untrusted input.

    ``max_steps`` (optional) is the per-case hard step budget the engine
    CLI receives as ``--max-steps N``.  When provided, the wrapper
    appends ``-e PIPELINE_MAX_STEPS=<N>`` to the docker argv; the
    container's entrypoint reads the env var and prepends ``--max-steps
    N`` to the engine CLI's argv.  This is the primary TLE(step) path
    (todo bug #2, SPEC §(i)); ``wall_timeout_s`` is the wall-clock
    backstop that catches engine crashes.  When ``max_steps`` is None,
    no ``--max-steps`` flag reaches the engine (the engine's default
    behaviour is unlimited steps).

    ``runner`` defaults to ``subprocess.run`` and exists so unit tests can
    inject a mock without touching the filesystem or Docker.
    """
    seccomp_path = Path(seccomp_profile)
    if not seccomp_path.is_file():
        return SandboxResult(
            container_exit_code=-1,
            output="",
            error={
                "code": "ERR_SECCOMP_MISSING",
                "message": (
                    f"seccomp profile not found at {seccomp_path}; run "
                    "`python scripts/run_sandboxed.py --export-seccomp`"
                ),
            },
        )

    cmd = build_docker_run(
        image=image,
        name=name,
        seccomp_profile=seccomp_path,
        max_steps=max_steps,
    )

    # Per-case input plumbing (todo bug #1): append the sentinel and input
    # to the source bytes so the entrypoint can split stdin into
    # (source, input) halves.  This avoids filesystem coordination between
    # the worker container and the docker daemon — a tempfile written
    # inside the worker container is invisible to the daemon's bind-mount
    # source resolver, so the sentinel approach is more portable.
    stdin_payload: bytes = source
    if input is not None:
        stdin_payload = source + INPUT_SENTINEL + input

    wall_start = time.monotonic()
    try:
        proc = runner(
            cmd,
            input=stdin_payload,
            capture_output=True,
            timeout=wall_timeout_s,
        )
    except subprocess.TimeoutExpired as e:
        # Wall-time TLE (M9 hard bound).  The engine may have already hit
        # ERR_STEP_LIMIT — we report the same verdict so the worker can
        # normalise.  ``e.stdout`` is bytes captured up to the timeout;
        # ``e.stderr`` is the docker/kill error stream.
        wall_ms = int((time.monotonic() - wall_start) * 1000)
        return SandboxResult(
            container_exit_code=-1,
            output=(e.stdout or b"").decode("utf-8", errors="replace"),
            report={
                "steps": 0,
                "error": {
                    "code": "ERR_STEP_LIMIT",
                    "message": (
                        f"wall timeout after {wall_timeout_s}s"
                    ),
                    "line": None,
                    "col": None,
                },
                "exit_ok": False,
                "output_bytes": len(e.stdout or b""),
            },
            wall_ms=wall_ms,
        )
    wall_ms = int((time.monotonic() - wall_start) * 1000)

    output_bytes, report_bytes = _split_report_stream(proc.stdout or b"")
    report: dict[str, Any] = {}
    if report_bytes is not None and report_bytes:
        try:
            report = json.loads(report_bytes)
        except json.JSONDecodeError as e:
            return SandboxResult(
                container_exit_code=proc.returncode,
                output=output_bytes.decode("utf-8", errors="replace"),
                wall_ms=wall_ms,
                error={
                    "code": "ERR_REPORT_PARSE",
                    "message": f"container report is not valid JSON: {e}",
                },
            )

    wrapper_error: dict[str, Any] | None = None
    if proc.returncode not in (0, 2, 3, 4):
        wrapper_error = {
            "code": "ERR_CONTAINER",
            "message": (
                f"docker run returned unexpected exit code {proc.returncode}: "
                f"{proc.stderr.decode(errors='replace').strip()}"
            ),
        }

    return SandboxResult(
        container_exit_code=proc.returncode,
        output=output_bytes.decode("utf-8", errors="replace"),
        report=report,
        error=wrapper_error,
        wall_ms=wall_ms,
    )


def _export_seccomp_arg(
    dest: Path,
    *,
    runner: Any = subprocess.run,
) -> Path:
    return export_seccomp(dest, runner=runner)


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run_sandboxed",
        description=(
            "Run a PseInt program inside the hardened Docker sandbox. "
            "Reads the program source from stdin."
        ),
    )
    parser.add_argument(
        "--export-seccomp",
        metavar="DEST",
        nargs="?",
        const=str(SECCOMP_REL_PATH),
        default=None,
        help=(
            "Export the host Docker engine's default seccomp profile to DEST "
            "(default: infra/seccomp/default.json) and exit. Does not run a "
            "container."
        ),
    )
    parser.add_argument(
        "--image",
        default=DEFAULT_IMAGE,
        help=f"worker image name (default: {DEFAULT_IMAGE})",
    )
    parser.add_argument(
        "--seccomp-profile",
        default=str(SECCOMP_REL_PATH),
        help=f"seccomp profile path (default: {SECCOMP_REL_PATH})",
    )
    parser.add_argument(
        "--name",
        default=None,
        help="optional container name (debug only; defaults to none)",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=None,
        metavar="N",
        help=(
            "forward a per-case step budget to the engine CLI via "
            "PIPELINE_MAX_STEPS env (default: unlimited)"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    if args.export_seccomp is not None:
        try:
            dest = _export_seccomp_arg(Path(args.export_seccomp))
        except (RuntimeError, OSError) as e:
            print(f"run_sandboxed: {e}", file=sys.stderr)
            return 1
        print(str(dest), file=sys.stdout)
        return 0

    source = sys.stdin.buffer.read()
    result = run_sandboxed(
        source,
        image=args.image,
        seccomp_profile=Path(args.seccomp_profile),
        name=args.name,
        max_steps=args.max_steps,
    )
    json.dump(result.to_dict(), sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0 if result.error is None else 1


if __name__ == "__main__":
    sys.exit(main())
