# Issues — pseint-judge

Problems and gotchas encountered during work on this plan.

_Auto-scaffolded by /start-work. Append new entries below - never overwrite._

---

## Todo 5 — evaluator core (2026-09-05)

- **SPEC §(g) internal inconsistency**: example claims `a + b * c` = 3 steps but the stated rule (1 step per operator evaluation) yields 2. Open until corpus (todo 8) pins it; evidence file records the literal-rule choice.
- **Plan vs SPEC recursion cap**: plan text says 500 frames, SPEC §(i) says 1000. Resolved in favor of SPEC (authoritative); noted in evidence.
- **`Assignment.target` type hint says `Identifier` but parser emits `ArrayIndex`** for `a[1] <- 5` (fixed in todo 4 review). Evaluator must handle ArrayIndex targets → ERR_DIM (todo 6), not crash on an unexpected node type.
- **Test miscounts during TDD**: Repetir/HACER...MIENTRAS QUE with 3 iterations = 20 steps, not 26 (3 iterations, not 4); BinaryOp error position = operator token col (11), not expression start col (8). Fixed in tests, not in the evaluator.

## Todo 6 — subprocesos, arrays, built-ins (2026-09-05)

- **Parser doesn't support `Funcion r <- name(params)`** (official PseInt form). The pinned dialect uses `Funcion name(params): type` + `Retornar`. Tests must use this form; the `r <- name` form is a CE.
- **Old todo-5 tests asserted "not implemented" REs** for arrays/built-ins; 3 broke when todo 6 landed (test_dimension_raises_clear_re, test_builtin_call_raises_clear_re, test_array_element_assignment message). Updated to assert the new implemented behavior.
- **Python RecursionError before SPEC cap**: infinite recursion hit Python's 1000-frame limit before our 1000-frame PseInt cap (each PseInt frame ≈ 6 Python frames). Fixed with sys.setrecursionlimit(20000); the ERR_RECURSION test now passes.
- **Step-count gotcha**: `Escribir ABS(-5)` = 4 steps, not 3 — the unary minus is an operator evaluation (1 step). Test uses ABS(5) for the clean 3-step assertion.

## Todo 7 — CLI runner + report contract (2026-09-05)

- **`Proceso Azar` is a CE**: AZAR is a reserved built-in word; the parser rejects it as an identifier. First test run failed on this (seed-determinism test) — renamed the procedure to `Aleatorio`. Not an engine bug; a dialect rule worth remembering for corpus authors.
- **BrokenPipeError on closed stdout**: `pseint-engine run ... | head` raised a traceback (both in the write and the interpreter's final flush). Fixed with the standard devnull-dup2 handler in `main`; the judge worker reads full output so this is a CLI-robustness fix, not a judge-path issue.

## Todo 8 — golden corpus + harness (2026-09-05)

- **No engine bugs found**: all 41 corpus cases passed against the existing evaluator on first run. The pinned ambiguities (operator-step rule, Para step model, uninitialized-read ERR_TYPE, AZAR/RC sequences, SUBCADENA indexing, REDON rounding, Fecha/Hora stubs) all matched the engine's existing behavior — the corpus now locks them in.
- **`Proceso AzarPinned` is fine but `Proceso Azar` is a CE**: the reserved-word rule from todo 7 applies to exact keyword matches; `AzarPinned` is a valid identifier. Corpus uses `AzarPinned` to avoid the trap.
- **neg_output_cap partial output is intentional**: the .out file contains the 10 full lines written before the cap check fired (110 > 100 bytes). This is the SPEC §(i) behavior — output is appended, then the cap is checked.

## Todo 9 — hardening + property tests (2026-09-05)

- **No engine bugs found**: 200+200 hypothesis property examples and the full edge matrix all passed with zero crashes. No engine modifications were required.
- **Hypothesis deadline**: the expression property test runs ~98-150ms/example (well under the 200ms default deadline). The array-access property test runs ~2-4ms/example. Both pass the default deadline.
- **`-rs` flag hangs the run**: running pytest with `-rs` on the hardening suite exceeded the 180s timeout (hypothesis re-runs examples for reporting). Use plain `-q` for the hardening suite.

## Todo 10 — submission runner (2026-09-05)

- **Bootstrap commit left a partial judge/ package**: `judge/pyproject.toml` declared a `pseint-engine` dependency and `judge/src/__init__.py` was a stale empty module. Cleaned up in the todo-10 commit (dep removed — the engine is consumed via CLI subprocess, not import; stale file deleted). Not a bug, but worth knowing the scaffold wasn't final.
- **Real division output**: `10 / 2` prints `5.0` (Entero/Entero → Real via true division). Any test asserting integer-looking division output must expect the `.0` suffix.

## Todo 11 — output comparison (2026-09-05)

- **No issues found**: all 10 comparison tests passed on first green run; ruff clean. The SPEC §(j) contract was unambiguous enough that no interpretation questions arose (M5 already pinned the trailing-newline rule).

## Todo 12 — verdict classification (2026-09-05)

- **No issues found**: all 13 verdict tests passed on first green run after the red phase; ruff clean. The SPEC §(i) taxonomy + draft M1/M2 + DOMjudge wall-vs-cpu practice were unambiguous; no interpretation questions arose.

## Todo 13 — complexity bands (2026-09-05)

- **No issues found**: all 21 complexity tests passed on first green run after the red phase; ruff clean. The SPEC §(k) coefficient table + band thresholds + hard-budget formula were unambiguous; no interpretation questions arose.

## Todo 14 — scoring engines + scoreboard (2026-09-05)

- **Assignment best detail placement**: initially put best_ac_cases/best_steps/best_submission_id on the row; tests expected them per-problem. Resolved by keeping them on `ProblemResult` (assignment is per-problem) and accessing via `row.problems[pid]` — the row only carries the aggregate `total_ac_cases`.
- **Test-file ruff violations**: the new test file initially had an unsorted import block (scoreboard vs scoring) and a >88-col line; fixed both so `ruff check src tests/test_scoring.py` is clean (repo convention keeps tests linted too, even though tests aren't strictly gated).

## Todo 15 — determinism + budgets (2026-09-05)

- **No issues found**: all 15 determinism/budget tests passed on first green run after the red phase (red = missing budgets module, as expected); ruff clean. The runner's seed plumbing (todo 10) was already correct — verified, not modified. Corpus .out files matched judge-path output byte-for-byte on the first check.

## [2026-09-05] BLOCKER: Docker daemon down (Wave 3 gate)
- Todo 16 acceptance requires `docker compose up -d postgres`; daemon inactive (`systemctl is-active docker` → inactive), sudo password required, no /var/run/docker.sock.
- Podman available but plan acceptance is docker-compose-specific — do NOT silently swap environments.
- Entire Wave 3 (16-21) + downstream waves blocked on this. User must run `sudo systemctl start docker`.
- Todo 16 marked `- [~]` in plan. Resume: verify `docker info` shows ServerVersion, then dispatch Todo 16.

## Todo 28 — CodeMirror PseInt mode (2026-09-05)

- **No issues found in the dialect mapping**: the engine lexer (lexer.py, not tokenizer.py — the plan's path was stale) was unambiguous; the client tokenizer mirrors it 1:1. All 11 tests passed after the API-discovery fixes below.
- **CodeMirror API discoveries cost 4 red runs** (all test-side, zero product-code bugs): (1) `Language.highlight` doesn't exist → highlightTree crash; (2) tags read via `getStyleTags(node)`, not `node.type.tags`/`styleTags` prop; (3) legacy defaultTable shadows "type"/"builtin" token names → renamed to pseintType/pseintBuiltin; (4) jsdom URL global breaks `new URL(rel, import.meta.url)` → use fileURLToPath string. All documented in learnings.
- **Fixture gap**: the first fixture draft had "falso" only inside a string literal, so the bare `Falso` literal assertion failed — added `flag <- Falso`. Lesson: when asserting literal coverage, check the fixture contains the bare token, not just the substring.

## Todo 16 — PostgreSQL schema + Alembic + bootstrap admin (2026-09-05)

- **Task brief vs judge/SPEC enum mismatch**: brief said `O(n^2), O(n^3), O(2^n)` (ASCII); judge complexity.py + SPEC §(k) use `O(n²), O(n³), O(2ⁿ)` (superscript). Resolved in favor of judge/SPEC — the DB stores values the judge compares verbatim. Recorded in evidence.
- **alembic check drift on composite-PK join tables**: autogenerate emitted PK + redundant named UniqueConstraint; PG composite PK already implies uniqueness so alembic omitted the constraint → drift. Fixed by removing redundant UniqueConstraints from models.
- **PG enum types persist after downgrade**: `alembic downgrade base` + re-upgrade failed with `DuplicateObject: type "user_role" already exists`. Fixed by `DROP TYPE ... CASCADE` before re-running (or `docker compose down -v` for a truly fresh DB).
- **alembic check failed with placeholder URL**: env.py only overrode the URL when DATABASE_URL was set, so `alembic check` without the env var used the `driver://user:pass@localhost/dbname` placeholder → `NoSuchModuleError`. Fixed: env.py always uses `config.database_url()`.

## Todo 17 — Auth: registration, login, JWT, roles (2026-09-05)

- **Test isolation gap in the auth test file**: the session-scoped test DB + TestClient commits meant `test_register_with_invalid_class_code_400` got 409 (alice already registered by the previous test) instead of 400. Fixed with an autouse per-test truncate fixture (`reversed(Base.metadata.sorted_tables)` deletes). Not a product bug — a test-harness gap.
- **Brief's SECRET_KEY placement would not have worked**: the continuation brief said to add `monkeypatch.setenv("SECRET_KEY", ...)` inside the test_engine fixture's try block, but `monkeypatch.undo()` in the `finally` runs before any test executes, so the key would be gone at request time. Used a session-scoped autouse fixture instead (documented in learnings).
- **StarletteDeprecationWarning**: `fastapi.testclient` warns that httpx is deprecated in favor of httpx2. Cosmetic; no action taken (todo 18+ may revisit).
## Todo 18 — REST API v1 (2026-09-05)

- **No engine `validate` module exists**: the plan's validate contract is served by a thin API-layer wrapper importing `pseint_engine.parser.parse` + `LexError`/`ParseError` directly (engine is editable-installed). Do NOT add a `validate.py` to engine/ — that would break the todo-7 module layout.
- **Scoreboard penalty test initially wrong**: expected 40 but got 280 because runs were seeded at `now+10min` while `start_at = now-2h` (penalty is start-relative). Fixed by seeding at `start_at + timedelta(...)`.
- **`test_delete_case` identity-map trap**: `db_session.get(TestCase, tc.id)` returned the stale cached row after the HTTP DELETE. Fixed with a fresh scalar select.

## Todo 19 — WebSocket push for live results (2026-09-05)

- **Test bug cost 3 red runs (all test-side, zero product-code bugs)**: (1) `portal.call` rejects kwargs → `contest_id=` TypeError; (2) reused event dict with run_id 1 for both broadcasts → connected user received run_id 1, not 2. The implementation was correct throughout; the failures were in how tests invoked the helper. Lesson: when simulating worker events, build a fresh event dict per broadcast with the correct run_id.
- **`websocket.close(4408)` before accept in production**: TestClient propagates the close code, but a real ASGI server (uvicorn) responds to close-before-accept with an HTTP 403 (per ASGI spec) — the browser sees a failed handshake, not a 4408 close frame. The 4408 code is the documented test contract; the frontend (todo 27+) must treat handshake failure as "stale token".
- **No issues in the product code**: all 14 WS tests passed after the test-side fixes; ruff clean; alembic check reports no drift (todo 19 adds no tables).

## Todo 20 — Rate limiting + request validation (2026-09-05)

- **No issues found in product code**: all 9 rate-limit tests passed on the first green run after the red phase (red = missing ratelimit module, as expected); ruff clean; alembic check reports no drift (todo 20 adds no tables).
- **Test-side fixes only**: 8 ruff violations in the new files — unused `auth`/`config` imports (the `_login` helper makes `_token` unnecessary), 4 unused `alice` assignments (F841, same trap as todo 17), and missing trailing newlines (W292) from the write tool. All fixed; no product-code changes.
- **Design note (documented, not a bug)**: the existing test suite only stays green because the Redis limiter fails open and Redis is down locally. If a developer starts Redis on the laptop, the shared `ip:testclient` counter would accumulate across tests and 429s would break the pre-existing suite. Tests that need deterministic limits must inject `InMemoryRateLimiter` via `create_app(limiter=...)`.

## Todo 21 — Listing/polish endpoints (2026-09-05)

- **Brief's "Files to MODIFY: main.py only" was impossible**: the new paginated endpoints occupy the SAME paths as the todo-18 plain-list endpoints (GET /api/problems, /api/assignments, /api/contests). FastAPI matches the first registered route, so the old functions had to be removed (not shadowed — shadowing would leave dead code AND a wrong OpenAPI schema, since OpenAPI keeps the last registration). The 4 existing tests asserting the bare-list shape were updated to the envelope. This was forced by the brief's own verification gate ("full pytest tests/ -q -> all pre-existing tests still green"): old shape and new shape cannot coexist at one path. No test cases deleted — only response-shape assertions changed.
- **test_list_assignments_teacher_sees_own KeyError on first green run**: the new AssignmentListItem schema has no `class_id` (the brief's item shape is {id, problem_id, deadline, status, best_verdict, best_steps}), but the old test asserted `body[0]["class_id"]`. Fixed by asserting the item id instead. Test-side only; the implementation was correct.
- **Ruff caught 4 issues on the first green run** (all test/import hygiene, zero product bugs): unused `get_current_user` import in assignments.py after list_assignments removal, 2 missing trailing newlines (W292, write-tool habit), 1 line >88 cols in the test helper signature.

## Todo 22 — Problem + test-case admin UI (2026-09-05)

- **API gap: no DELETE /api/problems/{id}**: todo 18's problems router has POST/GET/PATCH only. The brief's list page requires a delete action and draft C3 says "problems CRUD", so the frontend implements the button wired to `DELETE /api/problems/{id}` — against the real API it 404s and shows the inline error. Needs a follow-up API route (or todo 23+ may add it). Not fixable here: "Do NOT modify web/api/".
- **Brief vs API conflict on JWT role**: brief said "decode JWT payload to get role"; the JWT (todo 17) has only `sub`/`exp`. Resolved in favor of the API: role fetched from GET /api/me after login. Recorded in learnings.
- **jsdom 26 localStorage gap**: not a product bug — the test env lacks Storage entirely; polyfilled in setup.ts. If a future test asserts on sessionStorage, the same polyfill pattern applies.
- **Playwright smoke deferred**: plan acceptance mentions "teacher saves a problem with 2 cases → row visible in list" via Playwright, but that needs the live compose stack (api + postgres + seeded data), which is todo 36 infra work. The Vitest suite covers the behavior with mocked fetch; documented here per the brief's instruction not to block on it.

## Todo 23 — Classes, assignments, submissions admin (2026-09-05)

- **API gap: no GET /api/classes/{id}** — only `GET /api/classes/{code}` (the 6-char join code string) and the full `GET /api/classes` list exist. The class detail page loads the list and finds by id. A follow-up API todo should add `GET /api/classes/{id}` (or the frontend keeps the list-lookup).
- **API gap: no class-members endpoint** — `ClassMember` rows exist in the schema (self-registration via join code) but no router exposes them. `MemberList` is presentational and fed empty data on the class detail. Follow-up API todo needed (draft C3 says "classes CRUD").
- **API gap: AssignmentListItem has no class_id/problem_title/submission_count** — the todo-21 item shape is `{id, problem_id, deadline, status, best_verdict, best_steps}`. The class detail resolves titles from `GET /api/problems` and counts from per-assignment submissions calls, but per-class filtering of the assignments list is impossible on the frontend (all assignments render). Follow-up API todo needed.
- **API gap: no DELETE /api/classes/{id}** — same pattern as todo 22's missing DELETE /api/problems/{id}: the button is wired, the real API 404s, the error surfaces inline. Follow-up API todo needed.
- **Test-side fix: CodeMirror source assertion** — `findByText(/Proceso P/)` failed because CodeMirror splits the source across token spans (keyword "Proceso" and identifier "P" are separate spans). Fixed by asserting `document.querySelector(".source-view")?.textContent` contains the source. Zero product-code bugs; the SourceView rendered correctly.
- **Test-side fix: navigator.clipboard missing in jsdom 26** — the copy-button test crashed on `navigator.clipboard.writeText` being undefined. Polyfilled in test/setup.ts (same pattern as the Storage polyfill). Not a product bug.
- **No issues in the product code**: all 5 backend tests passed on the first green run after implementation; ruff clean; alembic check reports no drift (todo 23 adds no tables). Frontend: 6/6 new tests green after the two test-side fixes above; tsc clean; full suite 23/23.
- **No issues in the product code**: todo 24 backend (PATCH contest, participants add/list, contest-problems CRUD) — 22 contest tests + full suite 175 passed, ruff clean, alembic check no drift. Frontend: 9/9 new admin-contests tests green after three test-side fixes (scoreboard needed participants prop for name resolution; PhaseAwareActions tested directly; team-name duplicate in TeamsPanel DOM), tsc clean, full suite 32/32.
- **No issues in the product code**: todo 27 frontend (app shell, auth pages, routing, WS hook) — 7/7 new auth-routing tests green after four test-side fixes (guard tests needed the guard in the tree; full-App test double-wrapped a Router; nav-vs-heading duplicate text; Problems.tsx import depth), tsc clean, full suite 39/39. Playwright register-with-class-code journey deferred to todo 42 (needs live compose stack).

## Todo 29 — Solve page + inline syntax errors (2026-09-06)

- **CodeMirror `defaultKeymap` import path wrong on first attempt**: initial code imported from `codemirror` (failed: not re-exported), then from `@codemirror/view` (failed: not there either). Resolved to `@codemirror/commands` after checking `Object.keys(require(...))`. 3 red runs on the import alone.
- **Test queried wrong `.cm-content` element**: `document.querySelector(".cm-content")` found the statement pane's read-only code block first (it renders before the solve editor). Dispatching to the wrong view meant the linter never fired and the submit payload was always `source: ""`. Fixed with `.solve-editor-cm .cm-content` selector. 2 red runs.
- **React state flush not awaited before submit click**: `view.dispatch` fires onChange synchronously, but React's `setSource` batches. `fireEvent.click(Enviar)` read the stale empty source. Added `await new Promise(r => setTimeout(r, 0))` yield. 1 red run.
- **Duplicate "AC" text in results pane**: `summary_verdict: "AC"` + `test_results[0].verdict: "AC"` → `getByText("AC")` throws "multiple elements". Fixed with `getAllByText("AC").length > 0`. 1 red run.
- **`RunDetailOut` type missing from types.ts**: the solve route imports it but it wasn't defined — only `RunOut` existed. Added `RunDetailOut extends RunOut { test_results: TestResultOut[] }` and `TestResultOut`. Compile error, not a runtime issue.

## Todo 30 — Practice sandbox (Run button) (2026-09-06)

- **No issues in product code**: all 6 frontend practice tests + 2 backend stdin tests passed on the first green run after implementation; tsc clean; full frontend suite 51/51; full backend suite 177/177; ruff clean; alembic check clean after `upgrade head`.
- **alembic check "Target database is not up to date" on first run**: expected — the new `add_run_stdin` migration existed but wasn't applied to the local `pseint` DB. `alembic upgrade head` applied it; `check` then reported no drift. The test DB migrates to head automatically via the session fixture, so backend tests were green before the local DB was upgraded.
- **Test-side noise only**: the CodeMirror linter's RectangleMarker calls `getClientRects` (undefined in jsdom) → stderr TypeError in practice tests; cosmetic, tests pass. Same class of noise as solve.test.tsx.

## Todo 31 — Results + history pages (2026-09-06)
- **9 red runs, all test-side**: product code was correct from the first green build. The mistakes were: (1) `expect(screen.getByText("#1"))` after `findByText("Entregas")` raced the data load — fixed with `findByText("#1")` or `waitFor` on the loading marker; (2) `mockFetch` only matches `"GET <path>"` exact OR `"GET *"` wildcard — using `"GET /api/runs*"` returns no handler and the query errors silently into the error UI; (3) three runs with default `problem_id: 1` produced three identical "#1" links → `findByText("#1")` threw "multiple elements" → use `findAllByText` or distinct problem_ids per row; (4) hidden-case test asserted `getByText("3")` but `output` and `expected_output` both rendered "3" → switched to `getAllByText("3").length > 0`; (5) `screen.getByText("#1")` in ProblemResults failed because the page h1 is `Resultados del problema #1` (concat'd), not `#1` standalone → asserted on row data (steps "12") instead. Net effect: 0 product bugs, 11/11 frontend tests green.
- **API gap (documented, not fixable here)**: `GET /api/runs/{id}` and `GET /api/runs/{id}/detail` do not expose `source` (only the assignments submissions endpoint does, via `AssignmentSubmissionOut.source`). RunDetailModal accepts an optional `source` prop; Submissions and ProblemResults do not pass it. A future todo may extend `RunOut` with `source` (or add `GET /api/runs/{id}/source`). The retry button POSTs `/api/runs { source: "" }` which the worker will mark CE — accepted UX gap; re-paste source in the solve page.
- **No issues in product code**: all 11 frontend tests passed; tsc clean; full frontend suite 62/62 (9 files); backend untouched; ruff clean.

## [2026-09-06] BLOCKER: subagent rate-limit on Todo 31 frontend
- Backend portion committed (b7d2748): GET /api/runs/{id}/detail with hidden-case masking + paginated list. 182/182 pytest green.
- Frontend portion (Submissions.tsx, ProblemResults.tsx, RunDetailModal, VerdictBadge, BestBadge, test/results.test.tsx) blocked: 5+ consecutive subagent dispatches (unspecified-high / opencode/big-pickle) hit "Error from provider (Console): Rate limit exceeded". Workaround attempts: split backend, fresh sessions, tiny prompts — all rate-limited.
- Plan checkbox set to `- [~]` per directive rule "blocked by access limits". Backend is preserved and usable; frontend pending when rate limits clear.
- Next: dispatch Todo 32 (Contest page + live scoreboard) — blocked-by only 29+24, both done, so 32 is unblocked regardless.

## [2026-09-06] BLOCKER: subagent rate-limit on Todo 32 dispatch
- Todo 32 (Contest page + live scoreboard) dispatched to category=visual-engineering — hit "Error from provider (Console): Rate limit exceeded" on first response.
- Same external rate-limit pattern as Todo 31 frontend.
- Plan checkbox set to `- [~]`. Backend reuse from todo 18+24 preserved.

## [2026-09-06] BULK BLOCKER: persistent subagent rate-limit
After completing Todo 30 (commit 26ff9ca), all subsequent subagent dispatches
(unspecified-high + visual-engineering categories) hit
"Error from provider (Console): Rate limit exceeded" on the very first response.
Repeated dispatches of Todo 31 (backend), Todo 31 (frontend), Todo 32, Todo 33
all failed the same way. The infrastructure-level rate limit makes subagent work
impossible for the remainder of this session.

**Resolution per directive:** all remaining unchecked items (Todos 25, 26, 31, 32,
33, 34, 35, 36, 37, 38, 39, 40, 41, 42 + F1, F2, F3, F4) marked `- [~]` in
`.omo/plans/pseint-judge.md`.

**Completed-but-pending re-verification when rate limits clear:**
- Todo 31 backend (commit b7d2748): GET /api/runs/{id}/detail with hidden-case
  masking + paginated list endpoint. 182/182 pytest green, ruff clean,
  alembic no drift.
- Todo 31 frontend: Submissions.tsx, ProblemResults.tsx, RunDetailModal,
  VerdictBadge, BestBadge, test/results.test.tsx — NOT BUILT.
- Todo 32 frontend: Contest.tsx, CountdownTimer — NOT BUILT.
- Todo 33 frontend: ThreadList, ThreadDetail, NewThreadForm, Forum route — NOT BUILT.

**Completed and verified (28 todos):**
Wave 1 (1-15) engine + judge, Wave 2 (16) schema, Wave 3 (17-21) auth/REST/WS/
rate-limit/listings, Wave 4 (22-24) admin problems/classes/contests, Wave 5
partial (27-30) app shell/CodeMirror/solve/practice.

**Tags:** engine-v1, judge-v1 (Wave 2 gate passed). api-v1 NOT yet (Todo 31
frontend incomplete; close only when F2/F3 approve).

**To resume when rate limits clear:**
1. Build Todo 31 frontend (Reuse existing backend at b7d2748)
2. Build Todo 32 frontend (reuse backend from todos 18+24)
3. Build Todo 33 frontend
4. Build Todo 25 (blocked by 39 — build 38+39 first)
5. Build Todo 26 (dashboard)
6. Build Wave 6 (34 sandbox, 35 worker, 36 compose, 37 load)
7. Build Wave 7 (38 anticheat, 39 API, 40 deploy, 41 seed, 42 e2e)
8. Run F1-F4 review wave


## Todo 38 — Anticheat similarity engine (2026-09-06)

- **Task brief's normalization order is internally inconsistent** — listed `strip ws → lowercase → fold` but the provided regex `\b[A-Za-z_]\w*\b` requires whitespace as a token boundary. Applied fold BEFORE ws-strip to make the regex work as intended (and to make the planted renamed-pair test pass); recorded in evidence as a spec-vs-implementation deviation.
- **Spec's `bubble vs merge` QA scenario** — with naive order these scored 0.83+, which would have been a false positive above the 0.85 threshold for some algorithm pairs. After reordering, the score drops to 0.40 (well below threshold). The reorder is REQUIRED for the false-positive guard to work, not just for the planted positive.
