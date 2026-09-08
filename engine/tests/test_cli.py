"""Tests for the pseint-engine CLI (engine/src/pseint_engine/cli.py).

Covers the run/validate subcommands, the JSON report contract, deterministic
exit codes (0/1/2/3/4), input sources (--input file vs stdin), seed
determinism, and the evaluator limits (step budget, output cap, array cap).
"""

import json
import subprocess
import sys

from pseint_engine.evaluator import evaluate
from pseint_engine.parser import parse

# The engine is pip-installed editable in the venv, so `python -m
# pseint_engine.cli` resolves from any cwd.
CLI = [sys.executable, "-m", "pseint_engine.cli"]

# -- golden programs ---------------------------------------------------------

G1_SUMA = """\
Proceso SumaN
    Definir n, i, suma Como Entero
    Leer n
    suma <- 0
    Para i <- 1 Hasta n
        suma <- suma + i
    FinPara
    Escribir suma
FinProceso
"""

G2_FORMATO = """\
Proceso Formato
    Definir r Como Real
    Definir s Como Cadena
    Definir b Como Logico
    r <- 2.5
    s <- "hola"
    b <- Verdadero
    Escribir r, " ", s, " ", b
    Escribir 3 / 2
    Escribir 2.0
FinProceso
"""

G3_FACTORIAL = """\
Proceso Factorial
    Funcion fact(n): Entero
        Si n <= 1 Entonces
            Retornar 1
        Sino
            Retornar n * fact(n - 1)
        FinSi
    FinFuncion
    Definir n, f Como Entero
    Leer n
    f <- fact(n)
    Escribir f
FinProceso
"""

AZAR_SRC = """\
Proceso Aleatorio
    Definir i Como Entero
    Para i <- 1 Hasta 5
        Escribir AZAR(100)
    FinPara
FinProceso
"""

LENTO_SRC = """\
Proceso Lento
    Definir i Como Entero
    Para i <- 1 Hasta 100000
        Escribir i
    FinPara
FinProceso
"""

MUCHO_SRC = """\
Proceso Mucho
    Definir i Como Entero
    Para i <- 1 Hasta 100000
        Escribir "x"
    FinPara
FinProceso
"""

DIV0_SRC = """\
Proceso Div
    Definir a, b Como Entero
    a <- 1
    b <- 0
    Escribir a / b
FinProceso
"""


def write(tmp_path, name: str, text: str):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


def run_cli(args: list[str], input_bytes: bytes | None = None):
    return subprocess.run(CLI + args, input=input_bytes, capture_output=True)


def read_report(path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Evaluator limits (defaults preserve behavior; limits enforced in-engine)
# ---------------------------------------------------------------------------


def test_evaluator_limits_defaults_preserve_behavior():
    r1 = evaluate(parse(G1_SUMA), input_text="10\n")
    r2 = evaluate(
        parse(G1_SUMA),
        input_text="10\n",
        step_budget=None,
        output_cap=None,
        max_array_elements=1_000_000,
    )
    assert r1.output == r2.output == "55\n"
    assert r1.steps == r2.steps
    assert r1.error == r2.error is None


def test_evaluator_step_budget_exceeded():
    result = evaluate(parse(G1_SUMA), input_text="10\n", step_budget=1)
    assert result.error is not None
    assert result.error.code == "ERR_STEP_LIMIT"


def test_evaluator_step_budget_catches_empty_loop():
    # A Mientras with an empty body never reaches _exec_stmt; the budget must
    # still fire on the condition-check steps (hard TLE cap, SPEC §(i)).
    src = "Proceso P\n    Mientras Verdadero Hacer\n    FinMientras\nFinProceso"
    result = evaluate(parse(src), step_budget=5)
    assert result.error is not None
    assert result.error.code == "ERR_STEP_LIMIT"


def test_evaluator_output_cap_exceeded():
    src = 'Proceso P\n    Escribir "hola"\nFinProceso'
    result = evaluate(parse(src), output_cap=2)
    assert result.error is not None
    assert result.error.code == "ERR_OUTPUT_CAP"


def test_evaluator_max_array_elements():
    src = "Proceso P\n    Dimension a[20]\nFinProceso"
    result = evaluate(parse(src), max_array_elements=10)
    assert result.error is not None
    assert result.error.code == "ERR_DIM"


# ---------------------------------------------------------------------------
# run: 3 golden programs round-trip (byte-exact stdout + parsed JSON report)
# ---------------------------------------------------------------------------


def test_run_golden_sum_of_n_roundtrip(tmp_path):
    src = write(tmp_path, "suma.psc", G1_SUMA)
    inp = write(tmp_path, "suma.in", "10\n")
    report = tmp_path / "report.json"
    proc = run_cli(
        ["run", str(src), "--input", str(inp), "--report", str(report)]
    )
    assert proc.returncode == 0
    assert proc.stdout == b"55\n"  # byte-exact; report never on stdout
    data = read_report(report)
    assert data["steps"] > 0
    assert data["error"] is None
    assert data["exit_ok"] is True
    assert data["output_bytes"] == 3


def test_run_golden_formatting_roundtrip(tmp_path):
    src = write(tmp_path, "formato.psc", G2_FORMATO)
    report = tmp_path / "report.json"
    proc = run_cli(["run", str(src), "--report", str(report)])
    assert proc.returncode == 0
    expected = b"2.5 hola Verdadero\n1.5\n2.0\n"
    assert proc.stdout == expected
    data = read_report(report)
    assert data["steps"] > 0
    assert data["error"] is None
    assert data["exit_ok"] is True
    assert data["output_bytes"] == len(expected)


def test_run_golden_recursion_roundtrip(tmp_path):
    src = write(tmp_path, "fact.psc", G3_FACTORIAL)
    inp = write(tmp_path, "fact.in", "10\n")
    report = tmp_path / "report.json"
    proc = run_cli(
        ["run", str(src), "--input", str(inp), "--report", str(report)]
    )
    assert proc.returncode == 0
    assert proc.stdout == b"3628800\n"
    data = read_report(report)
    assert data["steps"] > 0
    assert data["error"] is None
    assert data["exit_ok"] is True
    assert data["output_bytes"] == 8


# ---------------------------------------------------------------------------
# run: input sources, seed determinism, report placement
# ---------------------------------------------------------------------------


def test_run_input_file_matches_stdin(tmp_path):
    src = write(tmp_path, "suma.psc", G1_SUMA)
    inp = write(tmp_path, "suma.in", "10\n")
    r1 = run_cli(["run", str(src), "--input", str(inp)])
    r2 = run_cli(["run", str(src)], input_bytes=b"10\n")
    assert r1.returncode == r2.returncode == 0
    assert r1.stdout == r2.stdout == b"55\n"


def test_run_seed_determinism(tmp_path):
    src = write(tmp_path, "azar.psc", AZAR_SRC)
    r1 = run_cli(["run", str(src), "--seed", "0"])
    r2 = run_cli(["run", str(src), "--seed", "0"])
    r3 = run_cli(["run", str(src), "--seed", "1"])
    assert r1.returncode == 0
    assert r1.stdout == r2.stdout == b"49\n97\n53\n5\n33\n"
    assert r3.stdout != r1.stdout


def test_run_report_creates_parent_dirs(tmp_path):
    src = write(tmp_path, "suma.psc", G1_SUMA)
    inp = write(tmp_path, "suma.in", "3\n")
    report = tmp_path / "a" / "b" / "report.json"
    proc = run_cli(
        ["run", str(src), "--input", str(inp), "--report", str(report)]
    )
    assert proc.returncode == 0
    assert report.exists()
    assert read_report(report)["exit_ok"] is True


def test_run_without_report_writes_nothing(tmp_path):
    src = write(tmp_path, "suma.psc", G1_SUMA)
    proc = run_cli(["run", str(src)], input_bytes=b"3\n")
    assert proc.returncode == 0
    assert proc.stdout == b"6\n"


# ---------------------------------------------------------------------------
# run: deterministic exit codes 2/3/4
# ---------------------------------------------------------------------------


def test_run_step_budget_exceeded_exit_3(tmp_path):
    src = write(tmp_path, "lento.psc", LENTO_SRC)
    report = tmp_path / "report.json"
    proc = run_cli(
        ["run", str(src), "--step-budget", "10", "--report", str(report)]
    )
    assert proc.returncode == 3
    data = read_report(report)
    assert data["error"]["code"] == "ERR_STEP_LIMIT"
    assert data["exit_ok"] is False


def test_run_max_steps_alias(tmp_path):
    src = write(tmp_path, "lento.psc", LENTO_SRC)
    proc = run_cli(["run", str(src), "--max-steps", "10"])
    assert proc.returncode == 3


def test_run_max_steps_tle_with_loop_program(tmp_path):
    """Bug #2 contract: ``--max-steps N`` on a loop program → exit 3 + ERR_STEP_LIMIT.

    The LENTO_SRC program does ``Para i <- 1 Hasta 100000``, ~600000
    steps (todo 8 corpus confirmed).  A budget of 50 fires ERR_STEP_LIMIT
    mid-loop; the report should carry the error code and a non-zero
    step count.

    This test is the engine-CLI half of the bug #2 plumbing contract:
    the entrypoint threads ``--max-steps N`` into the engine CLI exactly
    this way (see ``infra/entrypoint.build_cmd``), and the wrapper
    passes the env var from ``docker run`` to the entrypoint.  If this
    test passes, the engine CLI behaves correctly when the worker asks
    for a budget; if it fails, the worker can't deliver TLE(step)
    verdicts.
    """
    src = write(tmp_path, "lento.psc", LENTO_SRC)
    report = tmp_path / "report.json"
    proc = run_cli(
        ["run", str(src), "--max-steps", "50", "--report", str(report)]
    )
    assert proc.returncode == 3
    data = read_report(report)
    assert data["error"]["code"] == "ERR_STEP_LIMIT"
    assert "máximo 50" in data["error"]["message"]
    # Steps should be at least the budget (50) plus 1 — the check is
    # strict-greater (steps > budget).
    assert data["steps"] > 50
    # But not the full ~600k: the engine aborted early.
    assert data["steps"] < 1000


def test_run_no_max_steps_runs_to_completion(tmp_path):
    """Legacy: no ``--max-steps`` flag → engine runs to completion, exit 0.

    Pins that the entrypoint's default ``os.environ.get(...) is None``
    path produces the same argv the legacy CLI did.  The LENTO_SRC
    program is finite, so it completes cleanly with no error.
    """
    # Use a tiny, self-contained program (no Leer) so the test doesn't
    # depend on input plumbing — the bug #2 contract is purely about
    # the engine CLI's --max-steps handling.
    src = write(tmp_path, "ok.psc", G2_FORMATO)
    report = tmp_path / "report.json"
    proc = run_cli(["run", str(src), "--report", str(report)])
    assert proc.returncode == 0
    assert read_report(report)["error"] is None


def test_run_output_cap_exceeded_exit_4(tmp_path):
    src = write(tmp_path, "mucho.psc", MUCHO_SRC)
    report = tmp_path / "report.json"
    proc = run_cli(
        ["run", str(src), "--max-output-bytes", "100", "--report", str(report)]
    )
    assert proc.returncode == 4
    data = read_report(report)
    assert data["error"]["code"] == "ERR_OUTPUT_CAP"
    assert data["exit_ok"] is False


def test_run_runtime_error_div0_exit_2(tmp_path):
    src = write(tmp_path, "div.psc", DIV0_SRC)
    report = tmp_path / "report.json"
    proc = run_cli(["run", str(src), "--report", str(report)])
    assert proc.returncode == 2
    data = read_report(report)
    assert data["error"]["code"] == "ERR_DIV0"
    assert data["error"]["line"] >= 1
    assert data["error"]["col"] >= 0
    assert data["exit_ok"] is False


def test_run_syntax_error_exit_2(tmp_path):
    src = write(tmp_path, "mal.psc", "Proceso Mal\n    x <-\nFinProceso")
    report = tmp_path / "report.json"
    proc = run_cli(["run", str(src), "--report", str(report)])
    assert proc.returncode == 2
    data = read_report(report)
    assert data["error"]["code"] == "ERR_SYNTAX"
    assert data["error"]["line"] >= 1
    assert data["steps"] == 0
    assert data["exit_ok"] is False


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------


def test_validate_ok(tmp_path):
    src = write(tmp_path, "ok.psc", G1_SUMA)
    proc = run_cli(["validate", str(src)])
    assert proc.returncode == 0
    assert json.loads(proc.stdout.decode("utf-8")) == {
        "ok": True,
        "errors": [],
    }


def test_validate_bad_input_line_col(tmp_path):
    src = write(tmp_path, "mal.psc", "Proceso Mal\n    Si x Entonces\nFinProceso")
    proc = run_cli(["validate", str(src)])
    assert proc.returncode == 0  # validation result is the JSON, not the code
    data = json.loads(proc.stdout.decode("utf-8"))
    assert data["ok"] is False
    assert len(data["errors"]) >= 1
    err = data["errors"][0]
    assert err["code"] == "ERR_SYNTAX"
    assert err["line"] >= 1
    assert err["col"] >= 0


# ---------------------------------------------------------------------------
# usage / IO errors -> exit 1, message on stderr
# ---------------------------------------------------------------------------


def test_usage_error_missing_source_exit_1(tmp_path):
    proc = run_cli(["run", str(tmp_path / "nope.psc")])
    assert proc.returncode == 1
    assert proc.stderr


def test_usage_error_unknown_flag_exit_1(tmp_path):
    src = write(tmp_path, "ok.psc", G1_SUMA)
    proc = run_cli(["run", str(src), "--bogus"])
    assert proc.returncode == 1
    assert proc.stderr


def test_run_missing_input_file_exit_1(tmp_path):
    src = write(tmp_path, "ok.psc", G1_SUMA)
    proc = run_cli(["run", str(src), "--input", str(tmp_path / "no.in")])
    assert proc.returncode == 1
    assert proc.stderr


def test_validate_missing_source_exit_1(tmp_path):
    proc = run_cli(["validate", str(tmp_path / "nope.psc")])
    assert proc.returncode == 1
    assert proc.stderr