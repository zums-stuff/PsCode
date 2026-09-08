"""Unit tests for scripts/run_sandboxed.py (todo 34).

The wrapper's job is to run ONE submission in a hardened Docker container
with the exact hardening flags the plan pins. We mock ``subprocess.run``
(by injecting a ``runner`` callable — the wrapper accepts ``runner=`` as a
test seam) so the tests don't need a Docker daemon; the only thing they
assert is that the right argv + the right stdin bytes get to docker, and
that the container's stdout stream is parsed correctly.

Coverage:

    1.  build_docker_run — every required flag is present
    2.  build_docker_run — flag set is byte-exact against a frozen list
        (so OPS.md grep stays easy and there are no accidental changes)
    3.  run_sandboxed — stdin bytes reach the container unchanged
    4.  run_sandboxed — the sentinel split parses (program_output, report)
    5.  run_sandboxed — container exit codes 0/2/3/4 are accepted (engine
        CLI's 0/1/2/3/4 — wrapper never flags 1 (its own usage error) as
        an "unexpected container error")
    6.  run_sandboxed — non-zero exit codes outside {0,2,3,4} yield
        ERR_CONTAINER in result.error
    7.  run_sandboxed — malformed report JSON yields ERR_REPORT_PARSE
    8.  run_sandboxed — missing seccomp profile yields ERR_SECCOMP_MISSING
        and never spawns docker
    9.  export_seccomp — uses `docker:dind cat /etc/docker/seccomp/default.json`
    10. export_seccomp — writes bytes to the destination path
    11. export_seccomp — skips the write if the file already matches
    12. CLI --export-seccomp — invokes the exporter, prints the path, exits 0
    13. CLI --export-seccomp — propagates exporter errors to stderr + exit 1
    14. CLI --help — exits 0 and shows the subcommands (sanity)
    15. CLI default mode — reads stdin, runs the container, writes JSON
    16. hardening contract — image has no curl and no wget install lines
    17. hardening contract — no bash binary in ENTRYPOINT (Python only)
    18. plan acceptance — `docker inspect --format '{{.HostConfig.NetworkMode}}'`
        would see `none` (assert via flag)
    19. plan acceptance — `docker inspect --format '{{.HostConfig.SecurityOpt}}'`
        contains `no-new-privileges` and `seccomp=...`
    20. plan acceptance — `--memory`, `--cpus`, `--pids-limit`,
        `--read-only`, `--tmpfs /tmp`, `--user 65534:65534`,
        `--stop-timeout 8` are all present
    21. integration with the engine CLI — golden SUM program parses under
        the real engine CLI (contract stays aligned with todo 7)
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import run_sandboxed


@pytest.fixture
def seccomp_profile_path(tmp_path: Path) -> Path:
    """A non-empty seccomp profile so run_sandboxed does not short-circuit."""
    profile = tmp_path / "default.json"
    profile.write_text(json.dumps({"default": []}))
    return profile

CLI = [sys.executable, "-m", "pseint_engine.cli"]

GOLDEN_SUM = (
    "Proceso Suma\n"
    "    Definir a, b Como Entero\n"
    "    Leer a, b\n"
    "    Escribir a + b\n"
    "FinProceso\n"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeProc:
    """Drop-in for subprocess.run's CompletedProcess-ish return value."""

    def __init__(self, stdout: bytes = b"", stderr: bytes = b"",
                 returncode: int = 0) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode
        self.call_args: Any = None


def make_runner(proc: _FakeProc):
    """Return (callable, holder-dict) so tests can inspect the call args."""

    holder: dict[str, Any] = {"calls": []}

    def _run(cmd, **kwargs):
        holder["calls"].append((tuple(cmd), kwargs))
        return proc

    return _run, holder


# ---------------------------------------------------------------------------
# build_docker_run: hardening contract
# ---------------------------------------------------------------------------


def test_build_docker_run_is_byte_exact(seccomp_profile_path: Path) -> None:
    """Pin the exact argv so OPS.md grep stays trivial."""
    cmd = run_sandboxed.build_docker_run(seccomp_profile=seccomp_profile_path)
    expected = [
        "docker",
        "run",
        "--rm",
        "--network", "none",
        "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges:true",
        "--security-opt", f"seccomp={seccomp_profile_path}",
        "--memory", "128m",
        "--cpus", "0.5",
        "--pids-limit", "64",
        "--read-only",
        "--tmpfs", "/tmp",
        "--user", "65534:65534",
        "--stop-timeout", "8",
        "-i",
        # DEFAULT_IMAGE — engine sandbox image (separate tag from the
        # rqworker pool image to avoid collision when compose builds both).
        run_sandboxed.DEFAULT_IMAGE,
    ]
    assert cmd == expected


@pytest.mark.parametrize(
    "flag,value",
    [
        ("--network", "none"),
        ("--cap-drop", "ALL"),
        ("--memory", "128m"),
        ("--cpus", "0.5"),
        ("--pids-limit", "64"),
        ("--user", "65534:65534"),
        ("--stop-timeout", "8"),
        ("--read-only", None),
        ("--tmpfs", "/tmp"),
        ("-i", None),
    ],
)
def test_build_docker_run_required_flag_present(
    seccomp_profile_path: Path, flag: str, value: str | None
) -> None:
    cmd = run_sandboxed.build_docker_run(seccomp_profile=seccomp_profile_path)
    i = cmd.index(flag)
    if value is not None:
        assert cmd[i + 1] == value
    assert cmd[-1].endswith(":latest")  # DEFAULT_IMAGE — exact tag pinned below


def test_build_docker_run_includes_both_security_opts(
    seccomp_profile_path: Path,
) -> None:
    cmd = run_sandboxed.build_docker_run(seccomp_profile=seccomp_profile_path)
    assert "--security-opt" in cmd
    assert "no-new-privileges:true" in cmd
    assert f"seccomp={seccomp_profile_path}" in cmd


def test_build_docker_run_seccomp_profile_is_repo_relative() -> None:
    """Default seccomp profile must point to infra/seccomp/default.json.

    Resolves relative to the wrapper's own location so the default works
    in both dev mode and inside the rqworker container.
    """
    cmd = run_sandboxed.build_docker_run()
    expected = str(run_sandboxed.SECCOMP_REL_PATH)
    assert f"seccomp={expected}" in cmd
    assert expected.endswith("infra/seccomp/default.json")


def test_build_docker_run_supports_optional_container_name(
    seccomp_profile_path: Path,
) -> None:
    cmd = run_sandboxed.build_docker_run(
        name="pseint-worker-debug", seccomp_profile=seccomp_profile_path
    )
    assert "--name" in cmd
    i = cmd.index("--name")
    assert cmd[i + 1] == "pseint-worker-debug"


def test_build_docker_run_image_override(seccomp_profile_path: Path) -> None:
    cmd = run_sandboxed.build_docker_run(
        image="custom:latest", seccomp_profile=seccomp_profile_path
    )
    assert cmd[-1] == "custom:latest"


# ---------------------------------------------------------------------------
# run_sandboxed: stdin + report parsing
# ---------------------------------------------------------------------------


def test_run_sandboxed_pipes_source_to_docker_stdin(
    seccomp_profile_path: Path,
) -> None:
    proc = _FakeProc(
        stdout=b"55\n" + run_sandboxed.REPORT_SENTINEL + b"{}", returncode=0
    )
    runner, holder = make_runner(proc)
    src = GOLDEN_SUM.encode()
    run_sandboxed.run_sandboxed(
        src, seccomp_profile=seccomp_profile_path, runner=runner
    )
    assert len(holder["calls"]) == 1
    _cmd, kwargs = holder["calls"][0]
    assert kwargs["input"] == src
    assert kwargs["capture_output"] is True


def test_run_sandboxed_parses_report_from_stdout(
    seccomp_profile_path: Path,
) -> None:
    report = {"steps": 12, "error": None, "exit_ok": True, "output_bytes": 3}
    stream = (
        b"55\n" + run_sandboxed.REPORT_SENTINEL + json.dumps(report).encode() + b"\n"
    )
    proc = _FakeProc(stdout=stream, returncode=0)
    runner, _ = make_runner(proc)
    result = run_sandboxed.run_sandboxed(
        b"x", seccomp_profile=seccomp_profile_path, runner=runner
    )
    assert result.output == "55\n"
    assert result.report == report
    assert result.error is None
    assert result.container_exit_code == 0


@pytest.mark.parametrize("exit_code", [0, 2, 3, 4])
def test_run_sandboxed_accepts_engine_exit_codes(
    seccomp_profile_path: Path, exit_code: int
) -> None:
    """Engine CLI exits 0/2/3/4 (todo 7); 1 is the wrapper's own usage code."""
    proc = _FakeProc(
        stdout=b"" + run_sandboxed.REPORT_SENTINEL + b'{"steps": 0}',
        returncode=exit_code,
    )
    runner, _ = make_runner(proc)
    result = run_sandboxed.run_sandboxed(
        b"x", seccomp_profile=seccomp_profile_path, runner=runner
    )
    assert result.error is None, f"unexpected wrapper error for exit {exit_code}"


def test_run_sandboxed_flags_unexpected_container_error(
    seccomp_profile_path: Path,
) -> None:
    proc = _FakeProc(
        stdout=b"" + run_sandboxed.REPORT_SENTINEL + b'{"steps": 0}',
        returncode=137,
        stderr=b"killed",
    )
    runner, _ = make_runner(proc)
    result = run_sandboxed.run_sandboxed(
        b"x", seccomp_profile=seccomp_profile_path, runner=runner
    )
    assert result.error is not None
    assert result.error["code"] == "ERR_CONTAINER"
    assert "137" in result.error["message"]


def test_run_sandboxed_handles_malformed_report_json(
    seccomp_profile_path: Path,
) -> None:
    proc = _FakeProc(
        stdout=b"55\n" + run_sandboxed.REPORT_SENTINEL + b"not json {",
        returncode=0,
    )
    runner, _ = make_runner(proc)
    result = run_sandboxed.run_sandboxed(
        b"x", seccomp_profile=seccomp_profile_path, runner=runner
    )
    assert result.output == "55\n"
    assert result.report == {}
    assert result.error is not None
    assert result.error["code"] == "ERR_REPORT_PARSE"


def test_run_sandboxed_missing_seccomp_short_circuits(tmp_path: Path) -> None:
    """Never spawn docker without a seccomp profile."""
    runner, holder = make_runner(_FakeProc())
    missing = tmp_path / "nope.json"
    result = run_sandboxed.run_sandboxed(
        b"x", seccomp_profile=missing, runner=runner
    )
    assert holder["calls"] == []
    assert result.error is not None
    assert result.error["code"] == "ERR_SECCOMP_MISSING"


def test_run_sandboxed_handles_empty_program_output(
    seccomp_profile_path: Path,
) -> None:
    report = {"steps": 0, "error": None, "exit_ok": True, "output_bytes": 0}
    proc = _FakeProc(
        stdout=run_sandboxed.REPORT_SENTINEL + json.dumps(report).encode(),
        returncode=0,
    )
    runner, _ = make_runner(proc)
    result = run_sandboxed.run_sandboxed(
        b"x", seccomp_profile=seccomp_profile_path, runner=runner
    )
    assert result.output == ""
    assert result.report == report


def test_run_sandboxed_handles_stream_without_sentinel(
    seccomp_profile_path: Path,
) -> None:
    """A container that prints nothing parseable still returns the raw bytes."""
    proc = _FakeProc(stdout=b"raw stdout, no sentinel here", returncode=0)
    runner, _ = make_runner(proc)
    result = run_sandboxed.run_sandboxed(
        b"x", seccomp_profile=seccomp_profile_path, runner=runner
    )
    assert result.output == "raw stdout, no sentinel here"
    assert result.report == {}
    assert result.error is None


def test_run_sandboxed_uses_image_from_call(
    seccomp_profile_path: Path,
) -> None:
    proc = _FakeProc(stdout=b"55\n" + run_sandboxed.REPORT_SENTINEL + b"{}",
                     returncode=0)
    runner, holder = make_runner(proc)
    run_sandboxed.run_sandboxed(
        b"x",
        seccomp_profile=seccomp_profile_path,
        image="pseint-judge-engine:dev",
        runner=runner,
    )
    cmd, _ = holder["calls"][0]
    assert cmd[-1] == "pseint-judge-engine:dev"


def test_run_sandboxed_uses_name_from_call(
    seccomp_profile_path: Path,
) -> None:
    proc = _FakeProc(stdout=b"" + run_sandboxed.REPORT_SENTINEL + b"{}",
                     returncode=0)
    runner, holder = make_runner(proc)
    run_sandboxed.run_sandboxed(
        b"x",
        seccomp_profile=seccomp_profile_path,
        name="submission-42",
        runner=runner,
    )
    cmd, _ = holder["calls"][0]
    assert "--name" in cmd
    assert "submission-42" in cmd


# ---------------------------------------------------------------------------
# export_seccomp
# ---------------------------------------------------------------------------


def test_export_seccomp_uses_dind_image(tmp_path: Path) -> None:
    """Producer is `docker:dind cat /etc/docker/seccomp/default.json`."""
    captured: dict[str, Any] = {}

    class _P:
        stdout = b'{"default": []}'
        stderr = b""
        returncode = 0

    def fake_run(cmd, **kwargs):
        captured["cmd"] = list(cmd)
        return _P()

    dest = tmp_path / "default.json"
    out = run_sandboxed.export_seccomp(dest, runner=fake_run)
    assert captured["cmd"] == [
        "docker",
        "run",
        "--rm",
        "docker:dind",
        "cat",
        "/etc/docker/seccomp/default.json",
    ]
    assert out == dest
    assert dest.read_bytes() == b'{"default": []}'


def test_export_seccomp_overwrites_when_contents_differ(tmp_path: Path) -> None:
    dest = tmp_path / "default.json"
    dest.write_text("old")

    class _P:
        stdout = b'{"default": []}'
        stderr = b""
        returncode = 0

    run_sandboxed.export_seccomp(dest, runner=lambda *a, **kw: _P())
    assert dest.read_bytes() == b'{"default": []}'


def test_export_seccomp_is_idempotent(tmp_path: Path) -> None:
    """If the file already matches, the exporter must not touch mtime."""
    dest = tmp_path / "default.json"
    payload = b'{"default": []}'
    dest.write_bytes(payload)
    mtime_before = dest.stat().st_mtime_ns

    class _P:
        stdout = payload
        stderr = b""
        returncode = 0

    run_sandboxed.export_seccomp(dest, runner=lambda *a, **kw: _P())
    assert dest.stat().st_mtime_ns == mtime_before


def test_export_seccomp_propagates_nonzero_exit(tmp_path: Path) -> None:
    class _P:
        stdout = b""
        stderr = b"boom"
        returncode = 1

    def fake_run(cmd, **kwargs):
        return _P()

    with pytest.raises(RuntimeError, match="seccomp export failed"):
        run_sandboxed.export_seccomp(
            tmp_path / "default.json", runner=fake_run
        )


def test_export_seccomp_creates_parent_dirs(tmp_path: Path) -> None:
    dest = tmp_path / "deep" / "nested" / "default.json"

    class _P:
        stdout = b"{}"
        stderr = b""
        returncode = 0

    run_sandboxed.export_seccomp(dest, runner=lambda *a, **kw: _P())
    assert dest.is_file()


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------


def test_cli_export_seccomp_prints_dest_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    captured: dict[str, Path] = {}

    def fake_export(dest, **kwargs):
        captured["dest"] = Path(dest)
        Path(dest).write_bytes(b"{}")
        return Path(dest)

    monkeypatch.setattr(run_sandboxed, "export_seccomp", fake_export)
    monkeypatch.setattr(sys, "argv", ["run_sandboxed", "--export-seccomp"])
    rc = run_sandboxed.main()
    out = capsys.readouterr().out.strip()
    assert rc == 0
    assert Path(out) == captured["dest"]


def test_cli_export_seccomp_propagates_errors(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    def boom(*a, **kw):
        raise RuntimeError("seccomp export failed: docker not reachable")

    monkeypatch.setattr(run_sandboxed, "export_seccomp", boom)
    monkeypatch.setattr(sys, "argv", ["run_sandboxed", "--export-seccomp"])
    rc = run_sandboxed.main()
    err = capsys.readouterr().err
    assert rc == 1
    assert "seccomp export failed" in err


def test_cli_default_mode_reads_stdin_and_writes_json(
    seccomp_profile_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    """End-to-end CLI: stdin → mocked docker → JSON to stdout."""
    report = {"steps": 7, "error": None, "exit_ok": True, "output_bytes": 3}

    def fake_run_sandboxed(source: bytes, **_kwargs: Any) -> run_sandboxed.SandboxResult:
        assert source == GOLDEN_SUM.encode()
        return run_sandboxed.SandboxResult(
            container_exit_code=0,
            output="55\n",
            report=report,
        )

    monkeypatch.setattr(run_sandboxed, "run_sandboxed", fake_run_sandboxed)

    class _FakeStdin:
        def __init__(self, payload: bytes) -> None:
            self._buf = io.BytesIO(payload)

        @property
        def buffer(self) -> io.BytesIO:
            return self._buf

    monkeypatch.setattr(sys, "stdin", _FakeStdin(GOLDEN_SUM.encode()))
    monkeypatch.setattr(
        sys,
        "argv",
        ["run_sandboxed", "--seccomp-profile", str(seccomp_profile_path)],
    )
    rc = run_sandboxed.main()
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out)
    assert payload["output"] == "55\n"
    assert payload["report"] == report
    assert payload["error"] is None


def test_cli_help_exits_zero(capsys: pytest.CaptureFixture) -> None:
    with pytest.raises(SystemExit) as exc_info:
        run_sandboxed.main(["--help"])
    assert exc_info.value.code == 0


# ---------------------------------------------------------------------------
# Container image contract (Dockerfile.worker) — no curl/wget, no bash
# ---------------------------------------------------------------------------


def test_dockerfile_worker_installs_no_curl_or_wget() -> None:
    """No apt-get/RUN line in the worker image may install curl or wget."""
    dockerfile = (REPO_ROOT / "infra" / "Dockerfile.worker").read_text()
    run_lines = [
        line.strip() for line in dockerfile.splitlines()
        if line.strip().startswith("RUN")
    ]
    for line in run_lines:
        for banned in ("curl", "wget"):
            assert banned not in line, (
                f"Dockerfile.worker RUN must not install {banned!r}: {line!r}"
            )


def test_dockerfile_worker_uses_python311_slim() -> None:
    dockerfile = (REPO_ROOT / "infra" / "Dockerfile.worker").read_text()
    assert "FROM python:3.11-slim" in dockerfile


def test_dockerfile_worker_runs_as_65534() -> None:
    dockerfile = (REPO_ROOT / "infra" / "Dockerfile.worker").read_text()
    assert "USER 65534:65534" in dockerfile


def test_dockerfile_worker_has_no_bash_entrypoint() -> None:
    """Plan: 'no bash where possible MINIMAL deps' (todo 34)."""
    dockerfile = (REPO_ROOT / "infra" / "Dockerfile.worker").read_text()
    entry_lines = [
        line.strip() for line in dockerfile.splitlines()
        if line.strip().startswith("ENTRYPOINT")
    ]
    assert entry_lines, "Dockerfile.worker must declare an ENTRYPOINT"
    assert all("/bin/bash" not in line for line in entry_lines), (
        f"ENTRYPOINT must not invoke bash: {entry_lines!r}"
    )
    assert all("sh -c" not in line for line in entry_lines), (
        f"ENTRYPOINT must not invoke sh -c: {entry_lines!r}"
    )


def test_entrypoint_writes_source_to_tmpfs_path() -> None:
    """The entrypoint writes /tmp/source.psc and reads the engine report."""
    src = (REPO_ROOT / "infra" / "entrypoint.py").read_text()
    assert "/tmp/source.psc" in src
    assert "/tmp/report.json" in src
    assert "pseint_engine.cli" in src


# ---------------------------------------------------------------------------
# Bug #1 fix: per-case input plumbing (stdin sentinel split)
# ---------------------------------------------------------------------------


def test_run_sandboxed_input_none_keeps_legacy_stdin(
    seccomp_profile_path: Path,
) -> None:
    """When input=None, stdin is the source bytes only (no sentinel)."""
    proc = _FakeProc(
        stdout=b"55\n" + run_sandboxed.REPORT_SENTINEL + b"{}", returncode=0
    )
    runner, holder = make_runner(proc)
    src = b"Proceso P\nEscribir 55\nFinProceso\n"
    run_sandboxed.run_sandboxed(
        src,
        seccomp_profile=seccomp_profile_path,
        runner=runner,
    )
    _cmd, kwargs = holder["calls"][0]
    assert kwargs["input"] == src
    # No sentinel in the payload — the entrypoint treats the whole stdin
    # as the source (legacy behaviour, no /tmp/input.txt).
    assert run_sandboxed.INPUT_SENTINEL not in kwargs["input"]


def test_run_sandboxed_input_provided_appends_sentinel(
    seccomp_profile_path: Path,
) -> None:
    """When input=b"...", the wrapper appends SENTINEL + input to stdin."""
    proc = _FakeProc(
        stdout=b"5\n" + run_sandboxed.REPORT_SENTINEL + b"{}", returncode=0
    )
    runner, holder = make_runner(proc)
    src = b"Proceso P\nEscribir 5\nFinProceso\n"
    run_sandboxed.run_sandboxed(
        src,
        input=b"5\n",
        seccomp_profile=seccomp_profile_path,
        runner=runner,
    )
    _cmd, kwargs = holder["calls"][0]
    expected = src + run_sandboxed.INPUT_SENTINEL + b"5\n"
    assert kwargs["input"] == expected
    # The sentinel sits exactly at len(src) bytes from the start.
    assert kwargs["input"].find(run_sandboxed.INPUT_SENTINEL) == len(src)


def test_run_sandboxed_input_provided_no_bind_mount(
    seccomp_profile_path: Path,
) -> None:
    """No -v flag is added to argv when input is set (sentinel-only plumbing).

    Sentinel-only avoids the docker-daemon host-path-resolution pitfall
    for tmpfiles created inside the worker container (the daemon cannot
    see them on the host filesystem).
    """
    proc = _FakeProc(
        stdout=b"5\n" + run_sandboxed.REPORT_SENTINEL + b"{}", returncode=0
    )
    runner, holder = make_runner(proc)
    run_sandboxed.run_sandboxed(
        b"src",
        input=b"5\n",
        seccomp_profile=seccomp_profile_path,
        runner=runner,
    )
    cmd, _ = holder["calls"][0]
    assert "-v" not in cmd
    assert "/tmp/input.txt" not in cmd
    assert cmd[-1] == run_sandboxed.DEFAULT_IMAGE


def test_run_sandboxed_input_empty_bytes_still_appends_sentinel(
    seccomp_profile_path: Path,
) -> None:
    """input=b"" still triggers the sentinel — distinguishes from input=None."""
    proc = _FakeProc(
        stdout=b"" + run_sandboxed.REPORT_SENTINEL + b"{}", returncode=0
    )
    runner, holder = make_runner(proc)
    src = b"src"
    run_sandboxed.run_sandboxed(
        src,
        input=b"",
        seccomp_profile=seccomp_profile_path,
        runner=runner,
    )
    _cmd, kwargs = holder["calls"][0]
    # src + sentinel + empty input == src + sentinel
    assert kwargs["input"] == src + run_sandboxed.INPUT_SENTINEL


def test_run_sandboxed_input_sentinel_split_in_entrypoint(
    seccomp_profile_path: Path,
) -> None:
    """Verify the entrypoint's INPUT_SENTINEL constant equals the wrapper's.

    Catches drift: if the wrapper and entrypoint ever use different
    sentinel literals, the inner container would silently run the
    WRONG program (the input bytes would be parsed as part of the
    source).  We check via AST extraction rather than raw-text grep
    so quote-style changes (b'...' vs b"...") don't false-fail.
    """
    import ast
    src_text = (REPO_ROOT / "infra" / "entrypoint.py").read_text()
    tree = ast.parse(src_text)
    entrypoint_sentinel = None
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "INPUT_SENTINEL"
        ):
            entrypoint_sentinel = ast.literal_eval(node.value)
            break
    assert entrypoint_sentinel is not None, (
        "entrypoint must define INPUT_SENTINEL"
    )
    assert entrypoint_sentinel == run_sandboxed.INPUT_SENTINEL


def test_run_sandboxed_records_wall_ms(seccomp_profile_path: Path) -> None:
    """The wrapper records wall_ms around the docker call."""
    import time as _time

    proc = _FakeProc(
        stdout=b"" + run_sandboxed.REPORT_SENTINEL + b"{}", returncode=0
    )
    runner, _ = make_runner(proc)
    start = _time.monotonic()
    result = run_sandboxed.run_sandboxed(
        b"x", seccomp_profile=seccomp_profile_path, runner=runner
    )
    elapsed = int((_time.monotonic() - start) * 1000)
    assert result.wall_ms >= 0
    assert result.wall_ms <= elapsed


def test_run_sandboxed_wall_timeout_returns_err_step_limit(
    seccomp_profile_path: Path,
) -> None:
    """When subprocess.run times out, the wrapper reports ERR_STEP_LIMIT.

    This is the M9 wall-clock bound — an infinite loop's docker run never
    finishes naturally (no SIGTERM), so the wrapper enforces the deadline
    itself via subprocess.run(timeout=…).  The verdict maps to TLE in the
    worker.
    """
    import subprocess as _subprocess

    def fake_runner(cmd, **kwargs):
        # Mimic subprocess.TimeoutExpired: stdout partial, exit code -1
        raise _subprocess.TimeoutExpired(cmd=cmd, timeout=kwargs["timeout"])

    result = run_sandboxed.run_sandboxed(
        b"x",
        seccomp_profile=seccomp_profile_path,
        wall_timeout_s=0.5,
        runner=fake_runner,
    )
    assert result.container_exit_code == -1
    # The report's error.code drives the worker's TLE classification.
    assert result.report is not None
    assert result.report.get("error") is not None
    assert result.report["error"]["code"] == "ERR_STEP_LIMIT"
    # wall_ms is recorded as a non-negative int (mock-time may give 0).
    assert result.wall_ms >= 0


def test_run_sandboxed_wall_timeout_passes_to_runner(
    seccomp_profile_path: Path,
) -> None:
    """The wall_timeout_s is forwarded to runner(cmd, ..., timeout=…)."""
    captured: dict[str, Any] = {}

    def fake_runner(cmd, **kwargs):
        captured.update(kwargs)
        proc = _FakeProc(
            stdout=b"" + run_sandboxed.REPORT_SENTINEL + b"{}",
            returncode=0,
        )
        return proc

    run_sandboxed.run_sandboxed(
        b"x",
        seccomp_profile=seccomp_profile_path,
        wall_timeout_s=3.5,
        runner=fake_runner,
    )
    assert captured.get("timeout") == 3.5


def test_sandbox_result_to_dict_includes_wall_ms() -> None:
    """The wall_ms field round-trips through to_dict()."""
    sb = run_sandboxed.SandboxResult(
        container_exit_code=0, output="x", wall_ms=42,
    )
    d = sb.to_dict()
    assert d["wall_ms"] == 42


# ---------------------------------------------------------------------------
# Engine CLI integration: golden SUM round-trips through the parser
# ---------------------------------------------------------------------------


def test_golden_sum_parses_under_real_engine_cli() -> None:
    """Smoke check: the golden SUM source still parses under todo 7's CLI.

    This is the wrapper's downstream contract — if the engine CLI changes,
    the sandbox wrapper must change with it.
    """
    src_path = REPO_ROOT / "engine" / "tests" / "_sandbox_smoke.psc"
    try:
        src_path.write_text(GOLDEN_SUM, encoding="utf-8")
        proc = subprocess.run(
            CLI + ["validate", str(src_path)],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        assert proc.returncode == 0
        payload = json.loads(proc.stdout)
        assert payload["ok"] is True
        assert payload["errors"] == []
    finally:
        src_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Bug #2 fix: max_steps → PIPELINE_MAX_STEPS env → engine CLI --max-steps
# ---------------------------------------------------------------------------


def test_build_docker_run_max_steps_none_omits_env_flag(
    seccomp_profile_path: Path,
) -> None:
    """When ``max_steps`` is None, no ``-e PIPELINE_MAX_STEPS`` reaches docker.

    Legacy behaviour (unlimited steps) is preserved when the caller does
    not opt in.  This is the default for any code path that hasn't been
    updated to compute a per-case budget.
    """
    cmd = run_sandboxed.build_docker_run(seccomp_profile=seccomp_profile_path)
    assert not any(
        arg.startswith(f"{run_sandboxed.PIPELINE_MAX_STEPS_ENV}=")
        for arg in cmd
    )
    assert "-e" not in cmd or not any(
        arg.startswith(run_sandboxed.PIPELINE_MAX_STEPS_ENV)
        for arg in cmd
    )


def test_build_docker_run_max_steps_passed_via_env(
    seccomp_profile_path: Path,
) -> None:
    """``max_steps=1140`` appends ``-e PIPELINE_MAX_STEPS=1140`` to docker argv.

    The flag order matches the rest of the hardening contract: -e goes
    right before the image (the conventional ordering for ``docker run``).
    """
    cmd = run_sandboxed.build_docker_run(
        max_steps=1140, seccomp_profile=seccomp_profile_path,
    )
    # The env flag is present in the argv (split into -e + KEY=VAL).
    i = cmd.index("-e")
    assert cmd[i + 1] == "PIPELINE_MAX_STEPS=1140"
    # The flag comes right before the image (positional last).
    assert cmd[-2] == "PIPELINE_MAX_STEPS=1140"
    assert cmd[-1] == run_sandboxed.DEFAULT_IMAGE


def test_run_sandboxed_max_steps_none_no_env_in_call(
    seccomp_profile_path: Path,
) -> None:
    """``run_sandboxed(max_steps=None)`` does NOT pass ``-e`` to docker."""
    proc = _FakeProc(
        stdout=b"" + run_sandboxed.REPORT_SENTINEL + b"{}", returncode=0,
    )
    runner, holder = make_runner(proc)
    run_sandboxed.run_sandboxed(
        b"x", seccomp_profile=seccomp_profile_path, runner=runner,
    )
    cmd, _ = holder["calls"][0]
    assert not any(
        "PIPELINE_MAX_STEPS" in str(arg) for arg in cmd
    )


def test_run_sandboxed_max_steps_int_passes_env(
    seccomp_profile_path: Path,
) -> None:
    """``run_sandboxed(max_steps=50)`` propagates the env flag to docker."""
    proc = _FakeProc(
        stdout=b"" + run_sandboxed.REPORT_SENTINEL + b"{}", returncode=0,
    )
    runner, holder = make_runner(proc)
    run_sandboxed.run_sandboxed(
        b"x",
        max_steps=50,
        seccomp_profile=seccomp_profile_path,
        runner=runner,
    )
    cmd, _ = holder["calls"][0]
    i = cmd.index("-e")
    assert cmd[i + 1] == "PIPELINE_MAX_STEPS=50"


def test_run_sandboxed_max_steps_combined_with_input(
    seccomp_profile_path: Path,
) -> None:
    """max_steps + per-case input: both propagations work in one call."""
    proc = _FakeProc(
        stdout=b"" + run_sandboxed.REPORT_SENTINEL + b"{}", returncode=0,
    )
    runner, holder = make_runner(proc)
    run_sandboxed.run_sandboxed(
        b"src",
        input=b"5\n",
        max_steps=1140,
        seccomp_profile=seccomp_profile_path,
        runner=runner,
    )
    cmd, kwargs = holder["calls"][0]
    # Step budget plumbing.
    i = cmd.index("-e")
    assert cmd[i + 1] == "PIPELINE_MAX_STEPS=1140"
    # Per-case input plumbing (todo bug #1): sentinel-split stdin.
    assert kwargs["input"] == b"src" + run_sandboxed.INPUT_SENTINEL + b"5\n"


def test_run_sandboxed_signature_accepts_max_steps_kwarg() -> None:
    """``run_sandboxed`` exposes ``max_steps`` as a keyword parameter."""
    import inspect

    sig = inspect.signature(run_sandboxed.run_sandboxed)
    assert "max_steps" in sig.parameters
    assert sig.parameters["max_steps"].default is None


def test_cli_default_mode_forwards_max_steps_flag(
    seccomp_profile_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    """``--max-steps N`` on the wrapper CLI flows through to ``run_sandboxed``."""
    captured_kwargs: dict = {}

    def fake_run_sandboxed(source: bytes, **kwargs: Any) -> run_sandboxed.SandboxResult:
        captured_kwargs.update(kwargs)
        return run_sandboxed.SandboxResult(
            container_exit_code=0, output="", report={},
        )

    monkeypatch.setattr(run_sandboxed, "run_sandboxed", fake_run_sandboxed)

    class _FakeStdin:
        @property
        def buffer(self) -> io.BytesIO:
            return io.BytesIO(b"Proceso P\nFinProceso\n")

    monkeypatch.setattr(sys, "stdin", _FakeStdin())
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_sandboxed",
            "--seccomp-profile",
            str(seccomp_profile_path),
            "--max-steps",
            "777",
        ],
    )
    rc = run_sandboxed.main()
    out = capsys.readouterr().out
    assert rc == 0
    assert captured_kwargs.get("max_steps") == 777
    # And the JSON output shape is unchanged.
    payload = json.loads(out)
    assert payload["output"] == ""


def test_cli_default_mode_max_steps_default_none(
    seccomp_profile_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No ``--max-steps`` CLI flag → wrapper's default (None) reaches docker."""
    captured_kwargs: dict = {}

    def fake_run_sandboxed(source: bytes, **kwargs: Any) -> run_sandboxed.SandboxResult:
        captured_kwargs.update(kwargs)
        return run_sandboxed.SandboxResult(
            container_exit_code=0, output="", report={},
        )

    monkeypatch.setattr(run_sandboxed, "run_sandboxed", fake_run_sandboxed)

    class _FakeStdin:
        @property
        def buffer(self) -> io.BytesIO:
            return io.BytesIO(b"Proceso P\nFinProceso\n")

    monkeypatch.setattr(sys, "stdin", _FakeStdin())
    monkeypatch.setattr(
        sys,
        "argv",
        ["run_sandboxed", "--seccomp-profile", str(seccomp_profile_path)],
    )
    run_sandboxed.main()
    assert captured_kwargs.get("max_steps") is None
