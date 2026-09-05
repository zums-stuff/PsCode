# Learnings — pseint-judge

Conventions, patterns, and successful approaches discovered during work on this plan.

_Auto-scaffolded by /start-work. Append new entries below - never overwrite._

---

## Todo 5 — evaluator core (2026-09-05)

- **Step-count ambiguity (SPEC §(g))**: the table says "each operator evaluation costs 1 step" and its example claims `a + b * c` = 3 steps, but the literal rule (each operator NODE = 1 step) gives 2. Implemented the literal rule; discrepancy recorded in evidence; corpus (todo 8) will pin it.
- **Para step model that works**: entry = 1 step (statement), per-iteration = 1 (check) + body + 1 (increment), final failing check = 1. End/step expressions evaluated once at entry. Loop var type = declared, else Real if any bound/step is Real, else Entero; increment converted back to that type. Bidirectional: step >= 0 → `var <= end`, step < 0 → `var >= end`.
- **StringLiteral typing**: SPEC §(a) defines character literals as double-quoted single chars → 1-char string literal is typed Caracter, multi-char is Cadena. This matters for the conversion matrix (Caracter→Entero = ASCII).
- **Leer is line-aware, not a flat token stream**: tokens are `\s+`-split per line; normal Leer consumes tokens across lines (equivalent to global split), but bare Leer must discard the rest of the *current line* — so keep `_input_lines` + a line cursor, not a flat list.
- **Numeric token grammar**: `[+-]?\d+` (Entero) and `[+-]?\d+\.\d+` (Real) — no exponent notation, matching SPEC §(a) literal grammar. Never use bare `int()`/`float()` for parsing (they accept "1e5", "0x10", "1_000").
- **Real formatting = `repr(float)` verbatim** (shortest roundtrip): 2.0 → "2.0", 0.5 → "0.5". Matches SPEC §(e) golden examples exactly.
- **MOD sign convention**: Python's `%` (non-negative for positive divisor). `int/int` → real via Python true division.
- **Recursion cap**: SPEC pins 1000 frames (plan text said 500 — SPEC wins). White-box test via `_enter_frame`/`_exit_frame` since SubProceso execution is todo 6.
- **Not-implemented features must raise clear REs, never crash**: arrays → `ERR_DIM "arrays no implementados (todo 6)"`; FunctionCall → `ERR_TYPE "función no implementada (todo 6): NAME"`; SubProcCall/Retornar → ERR_TYPE.
- **Test-file linting**: existing test files (test_parser.py, test_lexer.py) already have ruff violations, so tests aren't strictly gated — but a compact `body_out(*stmts)` helper keeps new test lines under 88 cols anyway.

## Todo 6 — subprocesos, arrays, built-ins (2026-09-05)

- **Funcion syntax is `Funcion name(params): type` + `Retornar expr`** — the parser does NOT support the official `Funcion r <- name(params)` form. Return value comes exclusively from Retornar; the `: type` suffix is the return type.
- **SubProceso/Funcion declarations live INSIDE the Proceso block** (after `Proceso P`), not before it — the parser requires `Proceso` as the first token.
- **By-reference params = Env aliasing, not shadowing**: `bind_reference(param, caller_var)` stores an alias; reads/writes resolve outward to the caller's scope. Arrays default by-reference (same mechanism); simple types default by-value (copy in callee scope).
- **Python recursion limit vs SPEC cap**: each PseInt frame costs ~6 Python frames (evaluator→block→stmt→expr→call→block), so Python's default 1000 limit fires before the SPEC 1000-frame cap. `sys.setrecursionlimit(20000)` in evaluator.py fixes it.
- **Retornar outside a function must raise ERR_TYPE, not escape**: track `_in_function` flag; `_ReturnSignal` (control-flow exception) only fires inside a Funcion body.
- **SubProceso declaration costs 1 step** (consistent with todo-5 model: every block statement = 1 step). factorial(10) = 71 steps total.
- **AZAR(100) seed-0 pinned sequence**: 49 97 53 5 33 65 62 51 38 61 (random.Random(0).randrange(100)). RC(1) seed-0: m y n b (lowercase alphabet).
- **Array indexing = 1 step** (operator model, both read and write). Built-in call = 1 step.
- **SUBCADENA is 1-indexed inclusive** (official PseInt); REDON rounds half away from zero.
- **Redimensionar mutates the Array object in place** so by-reference arrays stay consistent across scopes.

## Todo 7 — CLI runner + report contract (2026-09-05)

- **Step budget must be checked at ALL step-increment sites, not just `_exec_stmt`**: an empty-body `Mientras Verdadero Hacer FinMientras` never reaches `_exec_stmt`, so a budget check only there would never fire. Wired `_check_step_budget` into all 12 increment sites (stmt, Leer/Escribir args, Segun cases, Para check+increment, conditions, unary/binary, array index r/w, function calls) → true hard TLE cap.
- **argparse default exit 2 collides with runtime-error=2**: override `ArgumentParser.error()` to raise a custom exception (print usage first), catch in `main`, return 1. `--help` still exits 0 via the un-overridden `exit()`.
- **Reserved words can't be procedure names**: `Proceso Azar` is a CE ("reserved word 'Azar' cannot be used as an identifier") — AZAR is a built-in. Test programs must use non-reserved names (e.g. `Proceso Aleatorio`).
- **CLI defaults ≠ evaluator defaults**: evaluator `output_cap`/`step_budget` default None (preserve behavior); CLI `--max-output-bytes` defaults 1_048_576 (M13 1MB) and passes it through. The distinction keeps the 448-test invariant while the CLI enforces the sandbox cap.
- **BrokenPipeError pattern**: CLI writing raw program output to stdout needs the Python-docs devnull-dup2 handler in `main` — piping to `head`/closed pipe otherwise dumps a traceback.
- **Editable install picks up new modules** (`.pth`-based): `python -m pseint_engine.cli` works in subprocess tests without reinstall; `pip install -e .` regenerates the `pseint-engine` console script.
