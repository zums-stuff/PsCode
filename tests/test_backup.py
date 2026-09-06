"""Tests for scripts/backup.sh (todo 40).

The script is bash; we exercise it through a pytest harness that:

* parses + validates CLI args without running them (syntax + help + flag
  validation)
* verifies the pruning primitive (find -mtime +7) that the script relies
  on, using ``find`` directly on a tmp dir
* stubs ``docker`` with a recorder and verifies the argv the script would
  pass matches the plan's pg_dump + psql invocations

The full backup + restore drill against a real compose stack is documented
in OPS.md §3 + §4 and is the user's acceptance gate.  The plan validates
that the script is parseable, has the right CLI surface, and produces the
expected docker-arg shapes when given a stub.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "backup.sh"


def _run_bash(code: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    """Run a bash snippet with the test env and return CompletedProcess."""
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    return subprocess.run(
        ["bash", "-c", code],
        capture_output=True,
        text=True,
        env=full_env,
        check=False,
    )


def _make_docker_stub(bin_dir: Path, log_file: Path) -> Path:
    """Write a docker-stub script and return its path.

    The stub records ``$@`` to ``log_file`` (one line per invocation) and
    succeeds for every command.  ``compose exec ... pg_dump`` emits a
    single SQL line so the pipeline that wraps it has data to gzip; ``psql
    -t -A 'SELECT 1'`` emits ``1`` so the scratch-DB verification query
    in the restore path finds the row.
    """
    bin_dir.mkdir(parents=True, exist_ok=True)
    recorder = bin_dir / "docker"
    recorder.write_text(
        "#!/usr/bin/env bash\n"
        "echo \"$@\" >> \"$DOCKER_RECORDER_LOG\"\n"
        "args=\"$*\"\n"
        "case \"$args\" in\n"
        "  *\" info\"*) exit 0 ;;\n"
        "  *\"pg_dump\"*) echo \"CREATE TABLE public.x (id int);\"; exit 0 ;;\n"
        "  *\"pg_database\"*) echo \"1\"; exit 0 ;;\n"
        "  *\"DROP DATABASE\"*) exit 0 ;;\n"
        "  *\"CREATE DATABASE\"*) exit 0 ;;\n"
        "  *) exit 0 ;;\n"
        "esac\n"
    )
    recorder.chmod(0o755)
    return recorder


def _stub_compose_dir(tmp_path: Path) -> Path:
    """Create the minimal compose dir + yml that the script's preflight wants."""
    compose_dir = tmp_path / "infra"
    compose_dir.mkdir()
    (compose_dir / "docker-compose.yml").write_text(
        "services:\n  postgres:\n    image: postgres:16-alpine\n"
    )
    return compose_dir


def test_backup_script_syntax_ok() -> None:
    """``bash -n`` catches parse errors without executing."""
    res = subprocess.run(
        ["bash", "-n", str(SCRIPT_PATH)], capture_output=True, text=True
    )
    assert res.returncode == 0, f"bash -n failed: {res.stderr}"


def test_backup_script_help() -> None:
    """``--help`` prints usage and exits 0; doesn't contact docker."""
    bin_dir = REPO_ROOT / "tests" / ".tmp-bin"
    if bin_dir.exists():
        shutil.rmtree(bin_dir)
    log_file = REPO_ROOT / "tests" / ".tmp-docker.log"
    if log_file.exists():
        log_file.unlink()
    bin_dir.mkdir()
    _make_docker_stub(bin_dir, log_file)
    try:
        res = subprocess.run(
            [str(SCRIPT_PATH), "--help"],
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "PATH": f"{bin_dir}:{os.environ['PATH']}",
                "DOCKER_RECORDER_LOG": str(log_file),
            },
        )
        assert res.returncode == 0
        assert "Usage" in res.stdout or "backup.sh" in res.stdout
        # --help must NOT have invoked docker at all (no log entries).
        assert not log_file.exists() or log_file.read_text() == ""
    finally:
        shutil.rmtree(bin_dir, ignore_errors=True)
        log_file.unlink(missing_ok=True)


def test_backup_script_refuses_unknown_flag() -> None:
    res = subprocess.run(
        [str(SCRIPT_PATH), "--bogus"],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 2
    assert "unknown flag" in res.stderr


def test_backup_script_refuses_restore_without_file() -> None:
    res = subprocess.run(
        [str(SCRIPT_PATH), "--restore"],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 2
    assert "requires a dump-file" in res.stderr


def test_backup_script_help_short_flag() -> None:
    """``-h`` is also accepted as the help flag."""
    res = subprocess.run(
        [str(SCRIPT_PATH), "-h"],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0


def test_backup_script_restore_refuses_missing_dump(tmp_path: Path) -> None:
    """``--restore <missing>`` exits non-zero before touching docker."""
    res = subprocess.run(
        [str(SCRIPT_PATH), "--restore", str(tmp_path / "nope.sql.gz")],
        capture_output=True,
        text=True,
    )
    assert res.returncode != 0
    assert "not found" in res.stderr


def test_backup_prunes_dumps_older_than_seven_days(tmp_path: Path) -> None:
    """The script's 7-day retention primitive works as expected.

    Pins the behaviour the script depends on (``find -mtime +7 -delete``)
    so a future find-portability regression fails loudly here instead of
    in production.
    """
    old_dump = tmp_path / "pseint-old.sql.gz"
    fresh_dump = tmp_path / "pseint-fresh.sql.gz"
    old_dump.write_text("OLD")
    fresh_dump.write_text("FRESH")
    # Force mtime to 8 days ago so the +7 match fires.
    eight_days_ago = 8 * 86400
    old_time = int(old_dump.stat().st_mtime) - eight_days_ago
    os.utime(old_dump, (old_time, old_time))

    res = subprocess.run(
        [
            "find",
            str(tmp_path),
            "-maxdepth",
            "1",
            "-type",
            "f",
            "-name",
            "pseint-*.sql.gz",
            "-mtime",
            "+7",
            "-delete",
        ],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0
    assert not old_dump.exists(), "old dump should have been pruned"
    assert fresh_dump.exists(), "fresh dump must remain"


def test_backup_mode_invokes_pg_dump_via_compose(tmp_path: Path) -> None:
    """Stubbed docker confirms the backup path invokes pg_dump."""
    log_file = tmp_path / "docker.log"
    _make_docker_stub(tmp_path / "bin", log_file)
    compose_dir = _stub_compose_dir(tmp_path)

    target = tmp_path / "backups"
    _run_bash(
        f"'{SCRIPT_PATH}' '{target}' 2>&1 || true",
        env={
            "PATH": f"{tmp_path / 'bin'}:{os.environ['PATH']}",
            "COMPOSE_DIR": str(compose_dir),
            "POSTGRES_USER": "pseint",
            "POSTGRES_PASSWORD": "pseint",
            "POSTGRES_DB": "pseint",
            "DOCKER_RECORDER_LOG": str(log_file),
        },
    )

    log_text = log_file.read_text() if log_file.exists() else ""
    assert "compose" in log_text, f"docker compose not invoked; log={log_text!r}"
    assert "exec" in log_text, f"docker compose exec not invoked; log={log_text!r}"
    assert "pg_dump" in log_text, f"pg_dump not invoked; log={log_text!r}"
    # Output file should be created in the target dir.
    dumps = list(target.glob("pseint-*.sql.gz"))
    assert len(dumps) == 1, f"expected one dump, got {dumps}"
    assert dumps[0].stat().st_size > 0, "dump should be non-empty"
    # File mode should be 0600 (secrets handling).
    mode = dumps[0].stat().st_mode & 0o777
    assert mode == 0o600, f"dump should be 0600, got {oct(mode)}"


def test_restore_mode_invokes_psql_via_compose(tmp_path: Path) -> None:
    """Stubbed docker confirms the restore path invokes psql."""
    log_file = tmp_path / "docker.log"
    _make_docker_stub(tmp_path / "bin", log_file)
    compose_dir = _stub_compose_dir(tmp_path)

    dump = tmp_path / "pseint-test.sql.gz"
    dump.write_bytes(b"CREATE TABLE public.x (id int);\n")

    _run_bash(
        f"'{SCRIPT_PATH}' --restore '{dump}' 2>&1 || true",
        env={
            "PATH": f"{tmp_path / 'bin'}:{os.environ['PATH']}",
            "COMPOSE_DIR": str(compose_dir),
            "POSTGRES_USER": "pseint",
            "POSTGRES_PASSWORD": "pseint",
            "POSTGRES_DB": "pseint",
            "DOCKER_RECORDER_LOG": str(log_file),
        },
    )

    log_text = log_file.read_text() if log_file.exists() else ""
    assert "compose" in log_text, f"docker compose not invoked; log={log_text!r}"
    assert "psql" in log_text, f"psql not invoked; log={log_text!r}"
    assert "pseint_restore_" in log_text, (
        f"scratch DB name missing from psql invocation; log={log_text!r}"
    )


def test_restore_uses_equals_form_for_flag() -> None:
    """``--restore=FILE`` syntax is also accepted."""
    res = subprocess.run(
        [str(SCRIPT_PATH), "--restore=/tmp/does-not-exist.sql.gz"],
        capture_output=True,
        text=True,
    )
    # Missing file → refuses, but it gets past the parser.
    assert res.returncode != 0
    assert "not found" in res.stderr
