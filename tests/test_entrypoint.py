"""Unit tests for infra/entrypoint.py.

The entrypoint runs INSIDE the worker sandbox container, so direct
integration tests are heavy (would need to spawn ``docker run``).  The
tests here focus on the two pure helpers:

    * ``_pipeline_max_steps_argv(env)`` — reads the
      ``PIPELINE_MAX_STEPS`` env var and returns the engine CLI argv
      fragment.  Tested with hand-built env dicts so we don't have to
      mutate the live ``os.environ``.
    * ``build_cmd(extra_args, env)`` — the full engine CLI argv
      (``sys.executable -m pseint_engine.cli run SOURCE extra
      --max-steps N --report REPORT``).  Tested against expected argv
      lists; the production call passes ``extra_args=[]`` (no per-case
      input) or ``["--input", path]`` (per-case input plumbing from
      todo bug #1).

Plus a regression check: the entrypoint reads the same env var name
(``PIPELINE_MAX_STEPS``) the wrapper writes via ``docker run -e``,
so they cannot drift.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT_PATH = REPO_ROOT / "infra" / "entrypoint.py"


def _load_entrypoint():
    """Import entrypoint.py by file path (no package context)."""
    spec = importlib.util.spec_from_file_location("entrypoint_under_test", ENTRYPOINT_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def entrypoint_mod():
    return _load_entrypoint()


# ---------------------------------------------------------------------------
# _pipeline_max_steps_argv
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "env,expected",
    [
        # No env var set → no flag.
        ({}, []),
        ({"SOMETHING_ELSE": "x"}, []),
        # Empty string → no flag (the wrapper never writes "" — defensive).
        ({"PIPELINE_MAX_STEPS": ""}, []),
        # Non-integer → no flag (defensive: a typo wouldn't crash the engine).
        ({"PIPELINE_MAX_STEPS": "abc"}, []),
        ({"PIPELINE_MAX_STEPS": "1.5"}, []),
        ({"PIPELINE_MAX_STEPS": "1e6"}, []),
        # Zero / negative → no flag (a non-positive budget is meaningless;
        # the engine's strict-greater check would fire on step 1).
        ({"PIPELINE_MAX_STEPS": "0"}, []),
        ({"PIPELINE_MAX_STEPS": "-5"}, []),
        # Positive integer → --max-steps N.
        ({"PIPELINE_MAX_STEPS": "1"}, ["--max-steps", "1"]),
        ({"PIPELINE_MAX_STEPS": "50"}, ["--max-steps", "50"]),
        ({"PIPELINE_MAX_STEPS": "1140"}, ["--max-steps", "1140"]),
        ({"PIPELINE_MAX_STEPS": "999999"}, ["--max-steps", "999999"]),
    ],
)
def test_pipeline_max_steps_argv(
    entrypoint_mod, env: dict[str, str], expected: list[str],
) -> None:
    """The env-var reader is the entrypoint's only step-budget seam."""
    argv = entrypoint_mod._pipeline_max_steps_argv(env=env)
    assert argv == expected


def test_pipeline_max_steps_argv_reads_live_environ_when_env_none(
    entrypoint_mod, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When no env dict is passed, the function reads ``os.environ``."""
    monkeypatch.setenv(entrypoint_mod.PIPELINE_MAX_STEPS_ENV, "777")
    argv = entrypoint_mod._pipeline_max_steps_argv()
    assert argv == ["--max-steps", "777"]


# ---------------------------------------------------------------------------
# build_cmd
# ---------------------------------------------------------------------------


def test_build_cmd_default_no_env_no_input(entrypoint_mod) -> None:
    """Default: no per-case input, no step-budget env → no extra flags."""
    cmd = entrypoint_mod.build_cmd(env={})
    # Engine CLI argv is always ``pseint_engine.cli run SOURCE --report REPORT``.
    assert cmd[0] == sys.executable
    assert cmd[1:4] == ["-m", "pseint_engine.cli", "run"]
    assert cmd[4] == entrypoint_mod.SOURCE_PATH
    assert cmd[-2:] == ["--report", entrypoint_mod.REPORT_PATH]
    # No per-case plumbing, no --max-steps.
    assert "--input" not in cmd
    assert "--max-steps" not in cmd


def test_build_cmd_with_per_case_input(entrypoint_mod) -> None:
    """Per-case input plumbing: ``--input /tmp/input.txt`` before --max-steps."""
    cmd = entrypoint_mod.build_cmd(
        extra_args=["--input", "/tmp/input.txt"], env={},
    )
    assert "--input" in cmd
    i = cmd.index("--input")
    assert cmd[i + 1] == "/tmp/input.txt"
    # --input comes BEFORE --max-steps (engine CLI parses positional + flag
    # pairs; either order works but the convention matches the order in
    # which the wrapper passes them).
    assert "--report" in cmd
    assert cmd.index("--input") < cmd.index("--report")


def test_build_cmd_with_step_budget_env(entrypoint_mod) -> None:
    """PIPELINE_MAX_STEPS=1140 → ``--max-steps 1140`` is in the argv."""
    cmd = entrypoint_mod.build_cmd(env={"PIPELINE_MAX_STEPS": "1140"})
    assert "--max-steps" in cmd
    i = cmd.index("--max-steps")
    assert cmd[i + 1] == "1140"


def test_build_cmd_with_both_per_case_input_and_step_budget(entrypoint_mod) -> None:
    """The full argv for a per-case run with a finite budget."""
    cmd = entrypoint_mod.build_cmd(
        extra_args=["--input", "/tmp/input.txt"],
        env={"PIPELINE_MAX_STEPS": "50"},
    )
    # --input and --max-steps both present.
    assert cmd[cmd.index("--input") + 1] == "/tmp/input.txt"
    assert cmd[cmd.index("--max-steps") + 1] == "50"


def test_build_cmd_omits_max_steps_when_env_unset(entrypoint_mod) -> None:
    """No PIPELINE_MAX_STEPS env → no ``--max-steps`` flag (legacy behaviour)."""
    cmd = entrypoint_mod.build_cmd(env={})
    assert "--max-steps" not in cmd


def test_build_cmd_omits_max_steps_when_env_malformed(entrypoint_mod) -> None:
    """Malformed env value (non-int) → no ``--max-steps`` flag, not a crash."""
    cmd = entrypoint_mod.build_cmd(env={"PIPELINE_MAX_STEPS": "not a number"})
    assert "--max-steps" not in cmd


# ---------------------------------------------------------------------------
# Constants: PIN the names so wrapper and entrypoint cannot drift
# ---------------------------------------------------------------------------


def test_entrypoint_pipeline_max_steps_env_name_matches_wrapper() -> None:
    """The env-var literal must equal ``scripts/run_sandboxed.PIPELINE_MAX_STEPS_ENV``.

    Drift here would silently drop the budget at runtime — the wrapper
    would set ``-e PIPELINE_MAX_STEPS=1140`` but the entrypoint would
    look for ``PIPELINE_MAX_STEPS_BUDGET`` (or similar) and the engine
    would receive no ``--max-steps`` flag.  Pin both names here.
    """
    import importlib.util as _ilu

    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    wrapper_spec = _ilu.spec_from_file_location(
        "run_sandboxed_under_test", REPO_ROOT / "scripts" / "run_sandboxed.py",
    )
    assert wrapper_spec is not None and wrapper_spec.loader is not None
    wrapper = _ilu.module_from_spec(wrapper_spec)
    sys.modules[wrapper_spec.name] = wrapper
    wrapper_spec.loader.exec_module(wrapper)

    entrypoint_spec = _ilu.spec_from_file_location(
        "entrypoint_under_test2", ENTRYPOINT_PATH,
    )
    assert entrypoint_spec is not None and entrypoint_spec.loader is not None
    entrypoint = _ilu.module_from_spec(entrypoint_spec)
    sys.modules[entrypoint_spec.name] = entrypoint
    entrypoint_spec.loader.exec_module(entrypoint)

    assert (
        wrapper.PIPELINE_MAX_STEPS_ENV
        == entrypoint.PIPELINE_MAX_STEPS_ENV
        == "PIPELINE_MAX_STEPS"
    )


def test_entrypoint_input_sentinel_matches_wrapper(entrypoint_mod) -> None:
    """The INPUT_SENTINEL literal must equal ``scripts/run_sandboxed.INPUT_SENTINEL``.

    Same drift concern as PIPELINE_MAX_STEPS_ENV (todo bug #1 lesson).
    """
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import run_sandboxed  # noqa: PLC0415  — fixture-style import

    assert entrypoint_mod.INPUT_SENTINEL == run_sandboxed.INPUT_SENTINEL
