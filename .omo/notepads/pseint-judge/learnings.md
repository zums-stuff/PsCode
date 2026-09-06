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

## Todo 8 — golden corpus + harness (2026-09-05)

- **Corpus generation approach**: wrote a throwaway generator script that emits all .psc files, runs each through `evaluate()`, and writes .out/.json from the engine result — then hand-verified every expected value against SPEC semantics (outputs, error codes, step counts). Step counts were cross-checked by manual trace for the small programs; all matched.
- **Mientras statement costs 1 step on top of condition evals**: `Mientras i < 3` with 3 iterations = 1 (stmt) + 3×(2 cond + 2 Escribir + 2 assign) + 2 final cond = 22 steps. The statement step is easy to forget when hand-tracing.
- **Para step model confirmed**: entry = 1 (statement) + per-iteration = 1 (check) + body + 1 (increment) + final failing check = 1. `Para i <- 1 Hasta 4` = 18 steps.
- **ERR_OUTPUT_CAP fires AFTER the offending Escribir completes**: the output append happens first, then the cap check raises — so the .out for neg_output_cap contains the full 10 lines (110 bytes > 100 cap) and the 10th iteration only costs 4 steps (cond 2 + Escribir stmt+arg 2), not 6.
- **ERR_STEP_LIMIT fires on strictly-greater**: `_check_step_budget` raises when `steps > budget`, so a budget of 5 fires at step 6 (during the BinaryOp eval of `i <- i + 1`, not at the statement boundary).
- **Corpus harness pattern**: pytest parametrize over sorted case names + a separate coverage-count test that prints per-category counts and asserts minimums (>=25 total, >=5 negative). Per-case kwargs dict for negative cases needing step_budget/output_cap.
- **Byte-exactness QA is cheap**: one `printf 'mayor \n' > si_basico.out` + pytest run proves the harness catches trailing-space mutations with a visible diff.

## Todo 9 — hardening + property tests (2026-09-05)

- **No engine bugs found**: 200+200 hypothesis property examples across bounded-depth expressions and array access, plus the full edge matrix, all passed against the existing evaluator with zero crashes. The todo-6 crash guards (AZAR(0), LN(0), EXP overflow, complex power, arity, Redimensionar caps) hold across the generated space.
- **Hypothesis strategy shape**: build the program as `Proceso P / Escribir <expr> / FinProceso`, parse (skip CE via LexError/ParseError), then evaluate. The no-crash invariant is `result.error is None or result.error.code in {8 SPEC codes}`.
- **SUBCADENA out-of-range is safe**: negative and >len indices slice cleanly (Python slicing semantics) — no crash, no RE. This is the documented behavior.
- **Negative MOD**: Python `%` semantics (sign follows divisor) — `-7 MOD 3` = 2, `7 MOD -3` = -2, `-7 MOD -3` = -1. Matches SPEC section (c) (MOD truncates reals first, then Python `%`).
- **Output cap fires after append**: ERR_OUTPUT_CAP raises after the offending Escribir completes, so partial output is present. Confirmed in the edge matrix.
- **Step budget fires on strictly-greater**: `_check_step_budget` raises when `steps > budget`. Infinite Mientras with budget=1000 terminates by design.

## Todo 10 — submission runner (2026-09-05)

- **Subprocess contract is the seam**: `[sys.executable, "-m", "pseint_engine.cli", "run", ...]` — sys.executable is the venv python, so no PATH dependency; the judge never imports the engine for execution (only `parse`/`LexError`/`ParseError` for the CE path). This keeps the worker/sandbox wrapper (todo 34) able to swap the engine for a containerized one later.
- **cpu_ms via RUSAGE_CHILDREN delta**: `resource.getrusage(RUSAGE_CHILDREN)` before/after `subprocess.run` gives the child's user+sys CPU time — simplest reliable approach on Linux; fine for the single-threaded-per-submission worker.
- **Source temp file written ONCE, reused for N cases**: parse-once/run-N means one `.psc` NamedTemporaryFile for the whole submission, per-case `.txt` input + `.json` report files, all unlinked in `finally`.
- **Missing/corrupt report degrades to ERR_INTERNAL**: a hard engine crash (segfault/OOM) leaves no report JSON; guard with try/except around json.load → synthetic error record instead of raising.
- **`10 / n` with Entero n → "5.0"**: engine true-division rule (todo 5) bit the practice-mode test — expected "5\n", got "5.0\n". Test fixed, not the runner.
- **Bootstrap scaffolded a partial judge/**: pyproject had a `pseint-engine` dependency + stale `src/__init__.py`; removed the dep (subprocess contract instead) and deleted the stale file before the real package landed.
- **Engine dep declared in judge pyproject (plan todo-1 spec)**: the runner imports `pseint_engine.lexer`/`parser` directly for the CE path, so `dependencies = ["pseint-engine"]` is required — fresh installs pull pseint-engine (todo-34 Docker image build would otherwise ImportError).

## Todo 11 — output comparison (2026-09-05)

- **Trailing-newline semantics fall out of `split("\n")` naturally**: `"5\n".split("\n")` → `["5", ""]` vs `"5".split("\n")` → `["5"]` — the extra empty element IS the diff (first_diff_line=2, both sides report `""`). No special-casing needed; the MUST-NOT-trim rule is just "don't drop the trailing empty element".
- **Missing-side convention**: when one side is longer, the missing side reports `""` for expected_line/got_line (not None) — keeps the return dict JSON-serializable for the API layer (todo 12+).
- **Token mode is whole-text `split()`, not per-line**: `"1  2\n3\n".split()` → `["1","2","3"]` equals `"1 2 3\n".split()` — newlines are just whitespace. Per-line token splitting would fail this pinned case.
- **first_diff_line doubles as token index in token mode**: same field name, 1-based index into the token sequence (plan says "first_diff_token" but the dict key stays `first_diff_line` per the todo-11 contract).

## Todo 12 — verdict classification (2026-09-05)

- **Classifier derives from the error dict, not the provisional verdict string**: `classify_case` reads `case.error["code"]` (ground truth) rather than trusting `case.verdict` (OK/TLE/RE provisional). The runner's provisional mapping is a subset; the classifier owns the full taxonomy.
- **Wall TLE uses strictly-greater `wall_ms > wall_limit_ms`**, mirroring the engine's strictly-greater step-budget convention (todo 8) — consistent boundary semantics across both budget kinds.
- **`wall_limit_ms=None` disables the wall check**: the classifier hardcodes no defaults (todo 15 constants module owns 5s/3s/128MB); the caller passes the problem's limit. Keeps the module pure and testable.
- **Priority edges tested pairwise**: the 6-level table has 5 adjacent edges; tests cover all of them (CE passthrough, step>wall, wall>RE, RE>WA, step>comparison) plus the closed-taxonomy constant `VERDICTS`.
- **CE passthrough is defensive**: the runner short-circuits CE at submission level (no CaseResult ever has verdict CE from the runner), but the classifier handles it so the taxonomy is complete in one module and todo 14 has a uniform consumption point.

## Todo 13 — complexity bands (2026-09-05)

- **SPEC §(k) is fully self-contained**: the coefficient table, band thresholds, hard-budget formula, and n_estimate rule are all pinned in the spec — no interpretation questions arose. Implemented the table verbatim with `math.floor` on logs.
- **"other" complexity → ValueError**: no auto formula; the caller must supply `problem.step_budget`. Raising (vs returning None) makes the contract explicit and testable with `pytest.raises`.
- **Band is a pure function of (steps, expected)**: `band()` needs no problem context — keeps complexity.py independent of verdicts.py (todo 14 wires them together). The planted bubble-vs-merge test proves the same step count lands in different bands depending on the expected complexity.
- **n_estimate is just `len(input_text.split())`**: whitespace-token count, empty → 0. Trivial but pinned by SPEC §k.

## Todo 14 — scoring engines + scoreboard (2026-09-05)

- **Scoreboard carries its full submission set** so recompute is ALWAYS possible: `apply_submission(prev, new)` = `compute_scoreboard(prev.submissions + [new], ...)`. This satisfies "no frozen scoreboards" trivially and keeps the incremental hook correct without caching.
- **Competition ranking (1,1,3)** is the stable same-score convention: equal keys share a rank, next rank skips. Implemented via `dataclasses.replace(row, rank=...)` since rows are frozen.
- **CF wrong-attempt exclusions are all in one predicate**: non-AC AND not-retry AND submitted_at >= start_at AND submitted_at < first_ac. The `retry` flag on `Submission` marks infra retries (excluded from wrong attempts).
- **Whole-minutes penalty** = `max(0, int((t - start_at).total_seconds() // 60))` — floored, never negative.
- **Teams = roster-driven participant set**: when a `roster` is passed, participants are the roster's teams and only locked-roster members' submissions count. This enforces the roster-lock edge (no mid-contest edits) by construction.
- **Assignment best is per-problem**: the best submission detail (best_ac_cases/best_steps/best_submission_id) lives on `ProblemResult`, not the row — tests access via `row.problems[pid]`.
- **Mode is explicit, never inferred**: `compute_scoreboard(subs, mode=...)` raises `ValueError` on unknown mode; `cf` requires `start_at`, `assignment` requires `deadline`.

## Todo 15 — determinism + budgets (2026-09-05)

- **Corpus .out files are byte-identical to judge_submission stdout**: all 5 sampled corpus programs reproduce their golden .out byte-for-byte through the full judge path (runner subprocess → CLI stdout). The corpus is a valid golden source for judge-level determinism tests, not just engine-level ones.
- **Determinism fingerprint excludes wall_ms/cpu_ms**: rejudge stability compares (verdict, error, per-case (verdict, steps, output, error)) — wall/cpu ms are legitimately variable measurements and must NOT be part of the byte-identical assertion.
- **effective_limits via dataclasses.replace over field-filtered keys**: `{k: v for k, v in problem.items() if k in Limits.__dataclass_fields__}` — unknown keys (step_budget, compare_mode) are ignored by construction, keeping the module pure and the override contract explicit.
- **Frozen Limits dataclass + replace() works cleanly**: `replace(Limits(), **overrides)` is the whole override mechanism; no mutation, no defaults drift.
- **The runner's seed plumbing needed zero changes**: `tc.get("seed", 0)` (todo 10) already implements SPEC §(h); todo 15 only centralizes the default as `DEFAULT_SEED = 0` in budgets.py and proves it with a missing-seed-key test.

## Todo 28 — CodeMirror PseInt mode (2026-09-05)

- **StreamLanguage tags live on node types via an internal styleTags prop**: `node.type.tags` is undefined and `node.type.prop(styleTags)` is undefined too (styleTags() returns a prop SOURCE, not the prop). The public reader is `getStyleTags(node)` from @lezer/highlight — that's the path the editor's highlighter uses. Tests must read tags via `getStyleTags(node).tags`.
- **Legacy defaultTable shadows custom token names**: StreamLanguage's TokenTable pre-maps CodeMirror-5 legacy names — `"type"` → typeName, `"builtin"` → variableName.standard, `"variable"` → variableName, etc. Custom tokenTable entries with those names are NEVER consulted. Use non-colliding names: `pseintType`, `pseintBuiltin` (keyword/literal/operator/number/string/comment/punct are safe).
- **`Language.highlight` does not exist** — highlightTree(tree, lang.highlight, ...) crashes with "Cannot read properties of undefined (reading 'scope')". StreamLanguage has no highlight property; tags come from the tokenTable attached to node types.
- **jsdom's URL global breaks `new URL(rel, import.meta.url)`**: resolves against http://localhost:3000 (document location) instead of the file base → "The URL must be of scheme file" from fileURLToPath. Use `fileURLToPath(import.meta.url)` (string) + node:path join instead.
- **EditorView in jsdom needs polyfills**: ResizeObserver, requestAnimationFrame, Element.scrollIntoView. Without them the mount test crashes; with them, CodeMirror 6 renders fine in jsdom.
- **Custom tags need a HighlightStyle to produce DOM spans**: without `syntaxHighlighting(...)`, tokens get tags but no CSS classes → `.cm-line span` count is 0. The lang package ships `pseintHighlightStyle` wired into `pseint()` so colors work out of the box.
- **Tag.define(name) accepts a name** — naming custom tags makes test failure messages readable (String(tag) prints the name).
- **StringStream.peek() is typed `string | undefined`** in @codemirror/language 6.12 — capture `const ch = stream.peek() ?? ""` once at the top of token().

## [2026-09-05] Todo 28: CodeMirror PseInt mode
- StreamLanguage tags read via getStyleTags(node), NOT node.type.tags
- Legacy defaultTable shadows "type"/"builtin" token names -> renamed pseintType/pseintBuiltin
- jsdom URL global breaks new URL(rel, import.meta.url); EditorView needs ResizeObserver/rAF/scrollIntoView polyfills
- Engine lexer is lexer.py (not tokenizer.py); types are parser-level _TYPE_NAMES, not lexer keywords
- KNOWN MINOR GAP: client punct set missing ";" (engine SEMICOLON) - no corpus usage, cosmetic only

## Todo 16 — PostgreSQL schema + Alembic + bootstrap admin (2026-09-05)

- **Complexity enum must use superscript forms**: judge complexity.py + SPEC §(k) use `O(n²)`, `O(n³)`, `O(2ⁿ)` (unicode), NOT ASCII `O(n^2)`. The task brief said ASCII, but the judge compares these exact strings — the DB enum MUST match the judge or grading breaks. When a task brief conflicts with an authoritative consumer, the consumer wins.
- **Composite PKs make named UniqueConstraints redundant in PG**: alembic autogenerate omits a UniqueConstraint when a composite PK covers the same columns, so `alembic check` flags drift if the model declares both. Use composite PK only for join tables.
- **PG enum types survive table drops**: `alembic downgrade base` drops tables but NOT the `CREATE TYPE` enums. Re-running the initial migration on a "downgraded" DB fails with `DuplicateObject: type "user_role" already exists`. Drop the enum types manually (`DROP TYPE ... CASCADE`) or recreate the volume.
- **alembic env.py URL override**: `config.set_main_option("sqlalchemy.url", ...)` in env.py is the right seam — but it must come from `config.database_url()` (env with local default), NOT the placeholder in alembic.ini. Tests point at the test DB by setting the `DATABASE_URL` env var before `command.upgrade`.
- **psycopg.sql.Composed can't go through SQLAlchemy conn.execute()**: raises `ObjectNotExecutableError`. Use `text()` with a constant identifier (safe) or the raw psycopg connection.
- **Test DB pattern**: session-scoped fixture creates `pseint_test` on the same docker postgres (via the `postgres` maintenance DB with AUTOCOMMIT), runs `command.upgrade(Config("alembic.ini"), "head")`, yields an engine, drops the DB with `DROP DATABASE ... WITH (FORCE)`.
- **`__test__ = False` on model classes**: `TestCase`/`TestResult` get picked up by pytest as test classes (PytestCollectionWarning). Mark them `__test__ = False`.

## Todo 17 — Auth: registration, login, JWT, roles (2026-09-05)

- **pwdlib raises `UnknownHashError` for non-argon2 hashes**: `PasswordHash.recommended().verify(plain, "x")` raises `pwdlib.exceptions.UnknownHashError`, not ValueError. The constant-time fallback (`hmac.compare_digest`) is what lets a test-seeded admin with `password_hash="x"` log in with password "x".
- **HTTP tests commit → rollback-only fixtures can't isolate them**: the session-scoped test DB persists rows across tests (register commits). A function-scoped autouse fixture that deletes all rows (`reversed(Base.metadata.sorted_tables)`) before each test is the fix — rollback alone is insufficient for TestClient-driven tests.
- **SECRET_KEY must be set for the whole test session, not just during fixture setup**: `monkeypatch.undo()` in the test_engine fixture's `finally` would undo a SECRET_KEY setenv added inside the try block. Use a session-scoped autouse fixture that sets `os.environ["SECRET_KEY"]` and pops it at teardown.
- **JWT expiry test via negative TTL**: `TOKEN_TTL_MINUTES=-1` makes `exp` land in the past → `jwt.decode` raises `ExpiredSignatureError` (a `JWTError` subclass) → 401. No need to sleep or mock time.
- **HTTPBearer(auto_error=False) + manual 401**: cleaner than OAuth2PasswordBearer for a pure-Bearer API; missing credentials → explicit 401 with `WWW-Authenticate: Bearer` header.
- **Role guards as plain functions with `Depends` defaults**: `require_teacher(user: User = Depends(get_current_user))` works both as a FastAPI dependency AND as a directly-callable function (tests call `require_teacher(student)` with a constructed User and assert the HTTPException).
- **TestClient + identity map**: after an HTTP DELETE commits in a *different* session, the test's `db_session.get()` returns the stale cached object (identity map) — or raises `ObjectDeletedError` after `expire_all()`. Use a fresh `select(...).where(...)` scalar query instead of `db.get` to assert deletion.
- **CF penalty is relative to contest start_at, not "now"**: `compute_scoreboard` computes `solve_time_min` from `start_at`. Tests seeding runs at `now + 10min` with `start_at = now - 2h` get penalty 130+150=280, not 40. Seed runs relative to `start_at` explicitly.
- **Forum contest lock must return the contest for teachers too**: the D15 phase-lock helper early-returned `None` for teachers, so threads created by teachers during a live contest never recorded `contest_id`. Return the running contest for everyone; raise 403 only for students.
- **ruff F841 on `_make_user` assignments**: tests that only use the username string (`_login(client, "alice")`) leave the `alice` variable unused. Drop the assignment, keep the call (the user must exist in the DB).
- **redis-py enqueue must be best-effort**: `_enqueue_run` wraps `redis.Redis.from_url(...).rpush(...)` in try/except + `logger.warning` so tests never require a Redis server; the run stays `queued` in the DB and the worker (todo 35) picks it up later.

## Todo 19 — WebSocket push for live results (2026-09-05)

- **`portal.call(func, *args)` is positional-only**: anyio's `BlockingPortal.call` (starlette TestClient's `client.portal`) does NOT accept keyword arguments. The broadcast helper's `contest_id` must be a positional param (or tests must use positional args). `client.portal.call(broadcast_run_event, run.id, user.id, event, contest.id)` works; `contest_id=contest.id` raises TypeError.
- **The broadcast helper's `run_id` param is for logging only** — the payload is `event_dict`. A test that reused one `make_run_event(1, ...)` dict for two broadcasts (run 1 to a non-connected user, run 2 to the connected user) received run_id 1: the second broadcast delivered the SAME dict. Each broadcast needs its own event dict with the correct run_id.
- **`websocket.close(code=4408)` before `accept()` works in TestClient**: starlette 1.6.0 sends `websocket.close` with the code; TestClient's `_receive` raises `WebSocketDisconnect(code=4408)`. Verified empirically before writing tests.
- **WS handler DB access via `Depends(get_db)`**: FastAPI websocket routes support dependencies, so the test's `app.dependency_overrides[get_db]` redirects replay queries to the test engine. Do NOT create a module-level engine in ws.py — it would bind to the default DB and break tests.
- **Replay ordering needs explicit `created_at`**: `server_default=func.now()` gives identical timestamps for bulk inserts → `ORDER BY created_at DESC` is nondeterministic. Seed `created_at=base - timedelta(minutes=i)` for deterministic replay-order assertions.
- **Module-level `_connections` survives across tests**: the in-memory connection manager is process-global; tests must not assume it's empty. The `_clean_tables` fixture truncates the DB but not the dict — sockets unsubscribe on disconnect (verified: `_connections` empties after context exit), so no cross-test leakage in practice.
- **Event design choice (documented)**: ONE `run` event per run emitted after all per_case are filled; `per_case` always ordered by case_index (replay query orders by case_index). The alternative (incremental per_case updates) was allowed by the plan; picked the simpler one.
- **Contest observer routing is explicit, not DB-derived**: `broadcast_run_event(run_id, user_id, event_dict, contest_id=None)` — the worker passes contest_id for contest-mode runs (it has the run row). No DB lookup in the broadcast path keeps it deterministic and testable.

## Todo 20 — Rate limiting + request validation (2026-09-05)

- **Fail-open Redis limiter is REQUIRED for the existing suite**: existing test files call `create_app()` with no limiter → Redis-backed RateLimiter. With Redis down (dev laptop), every request would raise ConnectionError → 500s. `check()` catches `redis.RedisError` → `(True, 1)` (fail-open) keeps all 147 pre-existing tests green. Rate limiting is a guardrail, not an availability boundary.
- **BaseHTTPMiddleware passes non-HTTP scopes straight through** (starlette 1.6.0 `__call__` checks `scope["type"] != "http"` first) — the `/ws/submissions` WebSocket route is neither rate-limited nor broken by the middleware. No skip-list entry needed for /ws.
- **redis-py is lazy**: `redis.Redis.from_url(...)` doesn't connect until a command runs, so the middleware constructor is safe; the first `INCR` is where ConnectionError surfaces. Add `socket_connect_timeout=1, socket_timeout=1` to bound fail-open latency.
- **INCR+TTL pipeline pattern**: `pipe.incr(key); pipe.ttl(key)` in one round trip; `count == 1` → fresh key → `EXPIRE` + use window_seconds as TTL; `ttl < 0` (race, key without TTL) → fall back to window_seconds. `retry_after = max(1, ttl)`.
- **Middleware identity extraction via header peek**: `request.headers.get("Authorization")` → strip "Bearer " → `auth.decode_token(token, config.secret_key())` → user_id. No FastAPI Depends resolution in middleware; decode failure → anonymous (`anon:{ip}`). Wrap in try/except — middleware must never raise.
- **Counter order on /api/runs**: submissions first (30), then runs (10) — the runs limit is the binding one on runs endpoints; "runs allowed but subs exceeded → still 429" is tested explicitly (25 validates + 5 runs OK, 6th run → 429 submissions).
- **Per-IP test trick**: `/api/me` 401s without auth but the middleware counts the request BEFORE the route runs — 60×401 then 61st → 429. Every non-skipped request counts against IP regardless of auth outcome.
- **Health/static skip proof**: the API has no /health route (healthz/readyz are Caddy-level, todo 40) — hits return 404, so the test asserts `!= 429` and proves non-consumption by doing 60 real requests after 100 skipped ones (all fit, 61st → 429).
- **InMemoryRateLimiter window reset test**: `window_seconds=1` + `time.sleep(1.1)` proves the dict counter resets after expiry — no clock injection needed.

## Todo 21 — Listing/polish endpoints (2026-09-05)

- **Per-user state via ONE aggregate query, not selectinload**: the plan says "eager-loading to avoid N+1 (selectinload)", but the listing response items reference ONLY columns — no relationship is serialized. The right move is a single `select(Run.problem_id, Run.summary_verdict).where(user_id=me, verdict not null)` grouped in Python, not loading relationships that are never touched. Zero N+1 by construction; selectinload would have been dead weight.
- **Verdict "best" = priority max, not SQL max**: AC > WA > TLE > RE > CE is a custom order (alphabetical max would pick WA over AC). `max(verdicts, key=VERDICT_PRIORITY.get)` in Python beats a CASE WHEN in SQL for readability.
- **Assignment best is per-assignment, not per-problem**: best_verdict/best_steps come from `Run.assignment_id == assignment.id` (the assignment submissions), NOT any run on the problem. Practice runs on the same problem don't count toward the assignment's best.
- **Tiebreak for best_steps**: best verdict wins; among equal verdicts, fewest steps wins. Implemented as tuple compare `(VERDICT_PRIORITY[v], -(steps or 0))`.
- **FastAPI Query(ge=1, le=100) gives 422 for free**: page>=1 and 1<=size<=100 validation is one decorator arg, no manual HTTPException. Beyond-range pages need NO special handling — offset/limit naturally returns an empty list with 200.
- **Generic Page[T] envelope**: `class Page(BaseModel, Generic[T]): items: list[T]; page; size; total` + `response_model=Page[ProblemListItem]` — Pydantic v2 generics work cleanly with FastAPI.
- **Empty `.in_([])` is safe in SQLAlchemy 2.x**: a student in no classes produces `class_id.in_([])` which renders as a false expression — returns nothing, no crash.
- **Route conflicts at the same path+method**: FastAPI matches the FIRST registered route; the OpenAPI schema keeps the LAST. Replacing a plain-list endpoint with a paginated one at the same path means the old function must be REMOVED (not shadowed) or the docs lie.

## Todo 22 — Problem + test-case admin UI (2026-09-05)

- **JWT carries no role claim — role comes from GET /api/me**: todo 17's `create_access_token` payload is only `{sub, exp}`. The brief said "decode JWT payload to get role" — impossible against the real API. The consumer wins: login() = POST /api/login → store token → GET /api/me → store `{id, username, display_name, role}` in localStorage. RequireRole reads user.role, never the token.
- **api client paths must include the `/api` prefix**: BASE_URL is the origin only (`http://localhost:8000`); callers pass `/api/problems`, `/api/validate`, etc. First red run failed because call sites passed `/problems` → URL `http://localhost:8000/problems` (404). The brief's own mock keys (`GET /api/problems`) pin the contract.
- **jsdom 26 dropped Storage entirely**: `typeof localStorage === "undefined"` in the vitest jsdom env (verified empirically). Auth flows need an in-memory Storage polyfill in test/setup.ts. Real browsers ship their own; this is test-env only.
- **Mock-fetch helper should accept plain objects OR functions**: `Record<string, MockHandler | unknown>` + `typeof handler === "function" ? handler(path, init) : handler` — tests pass response bodies as literals, and the `__error` marker object for non-2xx. Calling a plain object as a function was the second red run.
- **AuthProvider must read localStorage in useState initializers, not effects**: an effect-only read flashes token=null on first render → RequireRole redirects to /login before the effect runs. `useState(() => localStorage.getItem(...))` makes the first render correct; the effect only handles the "token without cached user" /api/me refresh.
- **vite.config.ts needs the `@codemirror/lang-pseint` alias too**: vitest.config.ts had it (todo 28), but `vite build` failed resolving the import from StatementEditor. Both configs must carry the alias (and `@/` → src).
- **React Router v6 future-flag warnings in tests are cosmetic**: `v7_startTransition` / `v7_relativeSplatPath` deprecation notices on stderr; no action needed (todo 27 may opt in).
- **Statement editor design**: textarea + "Vista previa" tab; fenced code blocks render through a read-only CodeMirror EditorView with `pseint()` + `EditorView.editable.of(false)` + lineWrapping. Markdown subset hand-rolled (headings, paragraphs, bold/italic, inline code, fences) — no markdown lib.
- **RunSampleButton = POST /api/validate with the statement content as `source`** (CE check only, per plan). The brief's "expected_output AS the source" alternative was dropped — the statement editor is the only source-shaped field on the problem.
- **Delete action is frontend-ready but the API has no DELETE /api/problems/{id}** (todo 18 gap): the button calls `api.delete("/api/problems/{id}")` and surfaces the error inline. Documented in issues.md; a follow-up API todo should add the route (draft C3 says "problems CRUD").

## Todo 23 — Classes, assignments, submissions admin (2026-09-05)

- **Per-student best = tuple compare on (VERDICT_PRIORITY, -steps)**: the same pattern todo 21 used for assignment best_verdict/best_steps generalizes to the submissions endpoint — `max` over `(VERDICT_PRIORITY[v], -(steps or 0))` picks AC over WA and fewest steps among equals in one expression. Import `VERDICT_PRIORITY` from `routes/listings.py` (it's the single source of the AC>WA>TLE>RE>CE order).
- **The submissions endpoint is the ONLY allowed backend change**: the brief pins `web/api/routes/assignments.py` as the sole modifiable API file. Every other gap (no GET /api/classes/{id}, no members endpoint, no class_id on AssignmentListItem, no DELETE /api/classes/{id}) must be absorbed on the frontend or documented — never fixed by touching the forbidden routers.
- **Class detail loads the class from the list, not by id**: `GET /api/classes` returns the full list (teacher-scoped server-side); `GET /api/classes/{code}` takes the 6-char join code, not an id. `classesQuery.data?.find((c) => c.id === Number(id))` is the lookup; the ownership guard (`cls.teacher_id !== user.id` for teachers) runs BEFORE the assignments query is enabled, so a forbidden teacher never fires the extra fetches.
- **Ownership guard must short-circuit before dependent queries**: the teacher-B test mocks ONLY `GET /api/classes` — if the guard didn't gate `enabled: !isNew && cls !== undefined` on the assignments/problems/submissions queries, the test would throw "No mock for GET /api/assignments..." and fail. Guard-first + `enabled` flags keep the fetch graph minimal and the test surface honest.
- **Role guard before any hook call**: `AdminAssignmentDetail` returns `<Navigate to="/403" replace />` when `user?.role === "student"` BEFORE the useQuery hooks — React hooks can't be conditional, so the guard is a plain early return above the hooks (the hooks are unconditional after it). The student test mocks zero handlers, proving no fetch fires.
- **CodeMirror splits source across token spans**: `findByText(/Proceso P/)` fails because "Proceso" (keyword) and "P" (identifier) land in different `<span>`s — no single element's textContent is contiguous. Assert on the container: `document.querySelector(".source-view")?.textContent` contains the source. Same lesson as todo 28's span-count assertions, one level up.
- **jsdom 26 has no navigator.clipboard**: `navigator.clipboard` is undefined in the test env; ClassCodeDisplay's copy button needs a polyfill in test/setup.ts (same pattern as the Storage polyfill from todo 22). Tests then `vi.spyOn(navigator.clipboard, "writeText")` and assert the call.
- **useQueries index alignment**: per-assignment submission counts in the class detail use `submissionCounts[i]?.data?.length` inside `items.map((a, i))` — the queries array is built from the same items array, so index alignment is guaranteed. A `.find((q) => q.data !== undefined)` first-draft returned the same count for every row (first query with data wins).
- **Rejudge = re-POST /api/runs with the stored source**: `{problem_id, source, mode: "assignment", assignment_id}` — teacher/admin are exempt from ASSIGNMENT_CLOSED, so rejudge works post-deadline. The table refetches submissions via `onRejudged()` after a successful POST; the mock asserts the body shape, not just the call.
- **i18n keys must be added, never removed**: the brief's "ADD new keys" is literal — es.ts is the single source and pre-existing keys (admin.problems.*, nav.*, etc.) must stay untouched. Duplicate keys in the object literal are a TS1117 error (caught by tsc), so load-error and create-error got distinct keys (`loadError` vs `error`).
- **Scoreboard rows carry participant_id, not usernames**: `GET /api/contests/{id}/scoreboard` rows have `participant_id` (user id as string, or team id when teams_enabled). The frontend must resolve display names from the participants list (`GET /api/contests/{id}/participants`) and teams list (`GET /api/contests/{id}/teams`) — ContestScoreboard takes both as props and builds `Map<string, string>` lookups.
- **TS does not preserve narrowing inside function-declaration closures**: `const contest = contestQuery.data; if (contest === undefined) return;` narrows in the outer scope, but a hoisted `async function handleSave()` referencing `contest` re-widens to `Contest | undefined` (TS18048). Fix: optional chaining `contest?.title ?? ""` inside the closure (and parenthesize `||`/`??` mixes — TS5076).
- **PhaseAwareActions is best tested directly, not through ParticipantsPanel**: the panel's own buttons carry `disabled={!classId}` logic, so asserting "enabled when running" through the panel fails regardless of the wrapper. Unit-test the wrapper with plain `<button>` children.
- **Team names appear twice in TeamsPanel DOM**: once in the team list, once in the member-select dropdown — `findByText("Equipo A")` throws "multiple elements"; use `findAllByText(...).length > 0`.
- **Gate the teams query on teams_enabled**: `enabled: contestQuery.data?.teams_enabled === true` avoids a wasted `GET /api/contests/{id}/teams` fetch for non-team contests (and simplifies the teams_enabled=false test — no teams mock needed).
- **TS does not narrow destructured `token` inside nested closures**: `const { token } = useAuth()` is `string | null`; even after `if (!token) return`, a nested `function connect()` referencing `token` re-widens to `string | null` (TS2345 on URLSearchParams). Fix: capture `const authToken = token;` after the guard.
- **App.tsx owns its BrowserRouter — tests must not wrap it**: rendering `<App />` inside `<MemoryRouter>` throws "You cannot render a <Router> inside another <Router>". Render `<App />` bare (its own BrowserRouter works in jsdom); use MemoryRouter only for isolated route tests.
- **Guard tests must wrap the route in the guard**: testing "student on /admin -> /403" by rendering a bare `<Route path="/admin" element={<div>admin area</div>} />` tests nothing — the guard must be in the test tree (`<RequireRole roles={["teacher","admin"]}>` around the element).
- **Nav link + page heading duplicate text**: "Problemas" appears in both the StudentLayout nav and the Problems page h1 — `getByText` throws "multiple elements"; use `getAllByText(...).length > 0` for nav-vs-heading collisions.
- **Register auto-login flow**: POST /api/register returns the user dict (no token); the client then calls POST /api/login + GET /api/me via the auth context's login() so token+user land in localStorage in one place.

## Todo 29 — Solve page + inline syntax errors (2026-09-06)

- **Engine lexer line/col convention**: `line` is 1-based, `col` is 0-based (`engine/src/pseint_engine/lexer.py`). `posFromLineCol`: `from = doc.line(line).from + col`, `to = from + 1`.
- **`defaultKeymap` lives in `@codemirror/commands`, NOT `@codemirror/view` or `codemirror`**: the `codemirror` meta-package re-exports `basicSetup`/`minimalSetup` but NOT `defaultKeymap`. `@codemirror/view` exports `keymap` but not `defaultKeymap`. Import from `@codemirror/commands` to get it.
- **`@codemirror/lint` was a transitive dep (not direct)**: CodeMirror's lint gutter/linter extension require `@codemirror/lint` as a peer dep. Pin it in `package.json` to avoid resolution surprises.
- **Statement pane's CodeMirror code-block is NOT the solve editor**: `document.querySelector(".cm-content")` in tests picks up the statement pane's read-only code block FIRST. The solve editor lives inside `.solve-editor-cm .cm-content`. Always use the more specific selector.
- **jsdom + CodeMirror linter debounce works but needs real setTimeout**: the `linter(source, {delay: 400})` uses `setTimeout` internally. jsdom runs Node's real `setTimeout`, so the debounce fires — but only if dispatched to the CORRECT EditorView. Dispatching to the wrong view (statement code-block) means the linter extension never sees the doc change.
- **React state flush needs yield before DOM click**: `view.dispatch({changes: ...})` synchronously calls `onChangeRef.current(doc.toString())` → `setSource(...)`, but React batches state updates. A `setTimeout(r, 0)` yield between dispatch and `fireEvent.click` ensures the Solve component's `source` state has propagated before the toolbar reads it for the submit payload.
- **`RunDetailOut` must be in `src/lib/types.ts`**: the API's `GET /api/runs/{id}` returns `test_results: TestResultOut[]` (extends RunOut). If the type is missing, the route module fails to compile. Add it alongside `RunOut` and `TestResultOut`.
- **Duplicate text assertions (AC, AC)**: the run detail has `summary_verdict: "AC"` AND `test_results[0].verdict: "AC"`. `getByText("AC")` throws "multiple elements found"; use `getAllByText("AC").length > 0`.
- **Mock calls type assertion**: `mock.calls[0]` returns `unknown[][]`, not `[string, RequestInit]`. Use `as unknown as [string, RequestInit]` to satisfy TS strict mode.

## Todo 30 — Practice sandbox (Run button) (2026-09-06)

- **Practice runs need a separate callback from graded submits**: SolveToolbar's `onRunCreated` fires for BOTH the Submit button and the RunModal. The Solve page must distinguish them (practice run → PracticeOutputPanel, graded run → SolveResultsPane), so the toolbar takes a second prop `onPracticeRunCreated(runId, stdin)` wired only to the modal. The stdin travels with the callback — the panel needs it to render the "input" column.
- **RunModal owns its sample-input fetch**: the modal fetches GET /api/problems/{id}/cases on mount and picks `is_sample` client-side (the endpoint returns all cases; there's no server-side sample filter). The Solve page ALSO fetches the same endpoint for the output panel's expected-output column — two consumers, one endpoint, both fine with the same mock handler.
- **429 handling differs between modal and toolbar**: the toolbar's Submit shows the quota notice inline and keeps the button; the modal keeps itself OPEN on 429 so the user's edited stdin survives (closing would lose it). Both use the same `solve.errors.quota` key.
- **Verdict badge colors need new CSS classes**: SolveResultsPane only had status-green/red/gray. PracticeOutputPanel needs yellow (TLE), orange (RE), purple (CE) — added `.status-yellow/.status-orange/.status-purple` to styles.css (allowed: only engine/, judge/, infra/, src/lang/ are forbidden).
- **`<pre>` textContent normalization traps in tests**: output "42" and expected "42\n" both normalize to "42" under getByText → "multiple elements". Use `getAllByText(/42/)` for output/expected assertions; assert unique strings (suggestion, CE error) with findByText.
- **jsdom + CodeMirror linter RectangleMarker noise**: the linter's `coordsAtPos` calls `getClientRects` which jsdom doesn't implement — stderr noise in practice tests, harmless (same as solve.test.tsx). Tests pass regardless.

## Todo 38 — Anticheat similarity engine (2026-09-06)

- **D13 normalization ORDER MATTERS** — the task brief lists `strip // comments, strip whitespace, lowercase, fold identifiers`, but `\b[A-Za-z_]\w*\b` after ws-strip misses identifiers glued to adjacent digits (e.g. `0Para` has no `\b` boundary between `0` and `P`). With the literal task-brief order, the planted renamed-variable pair scores 0.83 (just below the 0.85 threshold) and the test fails. Reordered to `comments → lowercase → fold → ws strip` so the regex catches every identifier with whitespace as boundary; lowercasing BEFORE fold keeps the placeholder `N` uppercase. All four transformations are still applied; only the order differs from the brief.
- **`SequenceMatcher.ratio()` over normalized forms is robust** — bubble sort vs merge sort scores 0.40 (well below 0.85), two renamed copies of the same algorithm score 1.0. The fold step is what makes renamed-variable copies collapse to identical strings; without it, `suma<-0` and `total<-0` are different.
- **Top-k per submission is naturally union-of-sides**: pair survives iff either side kept the other. With 4 identical subs and top_k=2, the (X3, X4) pair is the ONLY one dropped because both X3 and X4 prefer their lex-smaller neighbors (X1, X2) when sorting ties by `(-score, run_a_id, run_b_id)`. Useful test that the cap actually bounds something.
- **Canonical pair order = `(min, max)`** — lets the dedupe path be a one-liner `seen.add((p.run_a_id, p.run_b_id))` and makes input-list order irrelevant for `find_pairs`.
- **`exclude_team_pairs` is optional** — when the caller supplies a roster lock or extra exclusions, pass an iterable of `(id_a, id_b)` tuples; both orderings are accepted (stored as `frozenset({a, b})`).
