"""Command-line interface for the pseint-engine runner.

Subcommands::

    run <source.psc> [--input FILE] [--seed N] [--step-budget N | --max-steps N]
        [--max-output-bytes N] [--max-array-elements N] [--report FILE]
    validate <source.psc>

Exit codes (deterministic — the worker/sandbox contract, todo 34):

    0  ok
    1  usage / IO error (missing file, bad flag) — message on stderr
    2  runtime error (any RE incl. ERR_SYNTAX)
    3  step limit exceeded (ERR_STEP_LIMIT)
    4  output cap exceeded (ERR_OUTPUT_CAP)

Report JSON (written ONLY to ``--report``, never stdout)::

    {"steps": int, "error": {"code","message","line","col"} | null,
     "exit_ok": bool, "output_bytes": int}
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import NoReturn

from pseint_engine.evaluator import evaluate
from pseint_engine.lexer import LexError
from pseint_engine.parser import ParseError, parse
from pseint_engine.runtime import RuntimeError

_DEFAULT_OUTPUT_CAP = 1_048_576  # 1 MB (M13)
_DEFAULT_MAX_ARRAY_ELEMENTS = 1_000_000


class _ArgError(Exception):
    """Raised on usage errors (argparse's default exit 2 collides with RE)."""


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        raise _ArgError(message)


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(
        prog="pseint-engine",
        description="Deterministic PseInt interpreter with step counter.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="run a PseInt program")
    run_p.add_argument("source", metavar="SOURCE", help="path to the .psc source file")
    run_p.add_argument(
        "--input", metavar="FILE", help="input file (default: stdin)"
    )
    run_p.add_argument("--seed", type=int, default=0, help="AZAR/RC seed (default 0)")
    run_p.add_argument(
        "--step-budget",
        "--max-steps",
        dest="step_budget",
        type=int,
        default=None,
        metavar="N",
        help="hard step limit (default: unlimited)",
    )
    run_p.add_argument(
        "--max-output-bytes",
        type=int,
        default=_DEFAULT_OUTPUT_CAP,
        metavar="N",
        help=f"output cap in bytes (default {_DEFAULT_OUTPUT_CAP})",
    )
    run_p.add_argument(
        "--max-array-elements",
        type=int,
        default=_DEFAULT_MAX_ARRAY_ELEMENTS,
        metavar="N",
        help=f"per-array element cap (default {_DEFAULT_MAX_ARRAY_ELEMENTS})",
    )
    run_p.add_argument(
        "--report", metavar="FILE", help="write the JSON report to FILE"
    )

    val_p = sub.add_parser("validate", help="validate a PseInt program")
    val_p.add_argument("source", metavar="SOURCE", help="path to the .psc source file")
    return parser


def _read_source(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def _read_input(args) -> str:
    if args.input is not None:
        with open(args.input, encoding="utf-8") as f:
            return f.read()
    return sys.stdin.read()


def _write_report(path: str, data: dict) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


def _syntax_error(err: LexError | ParseError) -> dict:
    return {
        "code": "ERR_SYNTAX",
        "message": err.message,
        "line": err.line,
        "col": err.col,
    }


def _report(result, error: RuntimeError | None) -> dict:
    return {
        "steps": result.steps,
        "error": None
        if error is None
        else {
            "code": error.code,
            "message": error.message,
            "line": error.line,
            "col": error.col,
        },
        "exit_ok": error is None,
        "output_bytes": len(result.output.encode("utf-8")),
    }


def cmd_run(args) -> int:
    try:
        source = _read_source(args.source)
    except (OSError, UnicodeDecodeError) as e:
        print(f"pseint-engine: error: cannot read {args.source}: {e}", file=sys.stderr)
        return 1
    try:
        input_text = _read_input(args)
    except (OSError, UnicodeDecodeError) as e:
        print(f"pseint-engine: error: cannot read input: {e}", file=sys.stderr)
        return 1

    try:
        program = parse(source)
    except (LexError, ParseError) as e:
        report = {
            "steps": 0,
            "error": _syntax_error(e),
            "exit_ok": False,
            "output_bytes": 0,
        }
        if args.report is not None:
            _write_report(args.report, report)
        return 2

    result = evaluate(
        program,
        input_text=input_text,
        seed=args.seed,
        step_budget=args.step_budget,
        output_cap=args.max_output_bytes,
        max_array_elements=args.max_array_elements,
    )
    sys.stdout.buffer.write(result.output.encode("utf-8"))
    sys.stdout.buffer.flush()

    error = result.error
    if args.report is not None:
        _write_report(args.report, _report(result, error))
    if error is None:
        return 0
    if error.code == "ERR_STEP_LIMIT":
        return 3
    if error.code == "ERR_OUTPUT_CAP":
        return 4
    return 2


def cmd_validate(args) -> int:
    try:
        source = _read_source(args.source)
    except (OSError, UnicodeDecodeError) as e:
        print(f"pseint-engine: error: cannot read {args.source}: {e}", file=sys.stderr)
        return 1
    try:
        parse(source)
    except (LexError, ParseError) as e:
        data = {"ok": False, "errors": [_syntax_error(e)]}
    else:
        data = {"ok": True, "errors": []}
    print(json.dumps(data))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except _ArgError as e:
        print(f"pseint-engine: error: {e}", file=sys.stderr)
        return 1
    try:
        if args.command == "run":
            return cmd_run(args)
        return cmd_validate(args)
    except BrokenPipeError:
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
        return 1


if __name__ == "__main__":
    sys.exit(main())
