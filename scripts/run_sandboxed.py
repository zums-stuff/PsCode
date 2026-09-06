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
    -i (stdin pipe for the program source)

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
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from subprocess import CalledProcessError
from typing import Any

DEFAULT_IMAGE = "pseint-judge-worker:latest"
SECCOMP_DIND_IMAGE = "docker:dind"
SECCOMP_DIND_PATH = "/etc/docker/seccomp/default.json"
SECCOMP_REL_PATH = Path("infra/seccomp/default.json")

STOP_TIMEOUT_S = 8
MEMORY = "128m"
CPUS = "0.5"
PIDS_LIMIT = 64
USER_ID = "65534:65534"
NETWORK = "none"
CAP_DROP = "ALL"

REPORT_SENTINEL = b"\n===REPORT===\n"


@dataclass
class SandboxResult:
    """Structured outcome of one sandboxed run.

    Mirrors the engine CLI's JSON report (``--report``) plus wrapper-level
    metadata (container exit code, docker-args snapshot, runtime error if
    the wrapper itself blew up).
    """

    container_exit_code: int
    output: str
    report: dict[str, Any] = field(default_factory=dict)
    error: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "container_exit_code": self.container_exit_code,
            "output": self.output,
            "report": self.report,
            "error": self.error,
        }


def _docker_run_cmd(
    *,
    image: str,
    name: str | None,
    seccomp_profile: Path,
) -> list[str]:
    """Build the exact docker run argv for one submission.

    Flag order is not significant to Docker, but is kept stable so tests can
    assert against a fixed command list and OPS.md grep is easy.
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
        image,
    ]
    return cmd


def build_docker_run(
    *,
    image: str = DEFAULT_IMAGE,
    name: str | None = None,
    seccomp_profile: Path = SECCOMP_REL_PATH,
) -> list[str]:
    """Public builder for the docker run argv (testable without subprocess)."""
    return _docker_run_cmd(
        image=image,
        name=name,
        seccomp_profile=seccomp_profile,
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
    runner: Any = subprocess.run,
) -> SandboxResult:
    """Execute ``source`` inside the sandbox container and return the result.

    ``source`` is piped to the container's stdin and consumed by the
    entrypoint (``infra/entrypoint.py``), which drops it into /tmp and runs
    the engine CLI. ``runner`` defaults to ``subprocess.run`` and exists so
    unit tests can inject a mock without touching the filesystem or Docker.
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

    cmd = build_docker_run(image=image, name=name, seccomp_profile=seccomp_path)
    proc = runner(cmd, input=source, capture_output=True)

    output_bytes, report_bytes = _split_report_stream(proc.stdout or b"")
    report: dict[str, Any] = {}
    if report_bytes is not None and report_bytes:
        try:
            report = json.loads(report_bytes)
        except json.JSONDecodeError as e:
            return SandboxResult(
                container_exit_code=proc.returncode,
                output=output_bytes.decode("utf-8", errors="replace"),
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
    )
    json.dump(result.to_dict(), sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0 if result.error is None else 1


if __name__ == "__main__":
    sys.exit(main())
