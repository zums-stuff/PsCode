# pseint-judge - Work Plan

## TL;DR (For humans)
A complete online judge for PseInt pseudocode, like Codeforces but for algorithmics class: students write and run pseudocode in a browser editor, teachers create problems, classes, assignments and contests, and the platform grades submissions automatically with per-test-case verdicts, algorithm-complexity feedback, a live contest scoreboard, and a light similarity report of copied work. Built as one self-contained system that a school can run on a single server for up to a few hundred students.

**What you'll get:** A ready-to-deploy platform (students + teachers sides) where pseudocode programs are interpreted by our own engine — deterministic, with a step counter that grades both *correctness* (test cases pass/fail) and *efficiency* (complexity bands OK/ALTA/EXCESIVA) — plus assignments with deadlines, contests with Codeforces-style or partial-point scoring, per-problem forums, optional teams, and a minimal text-similarity plagiarism report (no automatic penalties). Built and verified entirely on your laptop first (`docker compose up -d`, plain HTTP at localhost) — UNAM production wiring (HTTPS, firewall, backups) is documented but only executed later when you provision the real host.

**Why this approach:** The interpreter core is the real risk and the heart of everything, so it is built first, driven by a written dialect spec and a large golden corpus of tested programs — including pinned-down "random" numbers so every run is reproducible. Everything else (judge, API, web, sandbox) is layered in waves on top of that core, in one Python/React stack that deploys on a single university machine with Docker.

**What it will NOT do:** No flowchart drawing, no converting pseudocode to other languages, no judging other programming languages, no student tracking or proctoring, no email flows, no automatic cheating penalties (reports are advisory only), no in-browser execution of pseudocode (all runs happen in a hardened sandbox server-side).

**Effort:** XL
**Risk:** Medium - dialect fidelity (matching how the real PSeInt tool behaves, including PSeInt's flexible syntax variants) and sandbox hardening are the two drivers
**Decisions to sanity-check:** (1) Complexity/efficiency is measured by a *deterministic step counter* rather than CPU time — fair and reproducible, but a novel choice; (2) the interpreter pins "canonical modern PseInt" with several official flexible variants enabled — students who use the real Windows tool for the same code may see small format differences; (3) cheating detection is deliberately minimal and non-punitive; (4) the original "exam mode" idea was replaced by contests with per-contest scoring options.

Your next move: approve to start executing the plan (the worker will build it in 7 waves with verifiable checks at each step), or ask for a high-accuracy review of this full plan first. Full execution detail follows below.

---

> TL;DR (machine): XL effort / Medium risk — full PseInt judge platform (deterministic interpreter engine + judge + FastAPI/Postgres API + React teacher/student web + Docker sandbox + CF/IOI contests + minimal text anticheat) in 42 todos across 7 waves plus final verification F1-F4; LOCAL-FIRST: verified end-to-end on the developer laptop via docker-compose HTTP (DOMAIN unset); UNAM deployment documented as a post-plan step, scale = REPLICAS workers on one host.

## Scope
### Must have
- C1 Interpreter core: pinned canonical-modern PseInt dialect (SPEC.md + golden .psc corpus); lexer/parser/AST/evaluator; deterministic semantics; step counter; runtime-error taxonomy; SubProceso/Funcion, Dimension arrays, built-ins (incl. deterministic AZAR); CLI runner with JSON report contract + validate subcommand.
- C2 Judge + scoring: parse-once/run-N; input injection; output comparison (exact-line default, token option); verdicts AC/WA/TLE/RE/CE; complexity bands (correctness first, steps = OK/ALTA/EXCESIVA, step budget = hard TLE); CF-style + IOI-style contest scoring (configurable per contest, incl. teams); scoreboard computation (live on AC + nightly reconcile); assignment best-count rules.
- C3 Teacher tooling (web): problem/test-case CRUD with complexity annotation; classes & class codes; assignments w/ deadlines; contests CRUD (schedule, scoring mode, teams_enabled) + participant/team management; contest + assignment submission browser w/ rejudge; anticheat report UI (thresholds, pair list, side-by-side diff); dashboard.
- C4 Student UX (web, responsive desktop+phone): register w/ class code; problem lists; solve page (CodeMirror 6 PseInt highlighting + debounced server-side inline errors); practice Run button w/ sample input; submit; live per-case results via WebSocket; history with best indicator; contest page + live scoreboard (CF/IOI, teams); per-problem forums with contest-phase lock.
- C5 Persistence + auth + API: PostgreSQL schema + Alembic (users/classes/problems/test_cases/assignments/contests/contest_problems/contest_participants/contest_teams/contest_team_members/runs/test_results/forum_threads/forum_posts/similarity_pairs); roles admin/teacher/student; JWT (24h); class-code self-registration; bootstrap admin via env; REST v1; WebSocket push; rate limiting; test_case.seed + problem.expected_complexity + problem.step_budget columns.
- C6 Sandbox + workers: engine container (hardened: no network, cap-drop, non-root, read-only, cgroup limits); RQ queue + 3 stateless workers (horizontal-ready); per-submission run (Docker wrapper + engine internal budgets); retries (infra errors only, never verdicts); status propagation.
- C7 Anticheat (minimal text similarity) + deployment: normalize (strip comments/whitespace, lowercase, identifier-fold); pairwise scores per problem scope; same-team exclusion; thresholds; report API + diff payloads; batch job; Caddy HTTPS; backups; healthchecks; seed data; Playwright E2E.
- TDD everywhere: engine golden corpus (>=25 cases incl. >=5 negative); judge/API unit + integration tests; Vitest components; Playwright journeys (register, solve, inline errors, run, submit, contest scoreboard, forum lock, anticheat report, mobile 375px).

### Must NOT have (guardrails, anti-slop, scope boundaries)
- No flowchart/diagram rendering; no export/code-gen to other languages; no arbitrary-language judging (pinned dialect only).
- No multi-tenant public SaaS; single-institution UNAM deployment, one host.
- LOCAL-FIRST execution (user scope 2026-09-04): the whole platform runs and is verified on the DEVELOPER's laptop via `docker compose up -d` (HTTP, DOMAIN unset → localhost) before any production wiring. UNAM/production provisioning is a SEPARATE post-plan step the user triggers; it is never performed during this plan's execution.
- No email flows (no verification, no reset-by-email; admin resets passwords).
- Anticheat: no proctoring, no IP tracking, no AI-written detection, NO automatic penalties (reports only).
- Contests: teams optional per contest (default individual); no rating system; no scoreboard freeze.
- Forums: role-gated, real accounts only, no anonymous posting, no private messaging; contest-problem threads teacher-only during the live window.
- No in-browser execution of pseudocode; no JS re-implementation of the parser (inline errors MUST use the server endpoint).
- No nsjail; Docker sandbox only. No multi-node/shared-nothing deployment architecture.
- No SSE fallback; WebSocket only.

## Verification strategy
> Zero human intervention - all verification is agent-executed.
- Test decision: TDD (pytest for engine/judge/API; Vitest + Testing Library for frontend; Playwright for journeys; hypothesis for engine property fuzz) + table-driven golden corpus
- Evidence: <attemptDir>/task-<N>-pseint-judge.<ext> (attemptDir = currentAttemptDir from 'omo ulw-loop status --json', .omo/evidence/ulw/<session>/<goalId>/a<attempt>; outside ulw-loop use .omo/evidence/)
- Per todo: agent runs the acceptance commands and stores output under the evidence path above; failure = fix + rerun; acceptance is green output + assertion, not logs.

## Execution strategy
### Parallel execution waves
> Target 5-8 todos per wave. Fewer than 3 (except the final) means you under-split.
- Wave 1 (Spec + interpreter core, C1): todos 1-9. Sequential inside; parser depends on lexer etc.
- Wave 2 (Judge + scoring, C2): todos 10-15. Blocks on 7-9 (engine CLI/report contract + corpus).
- Wave 3 (Persistence + auth + API, C5): todos 16-21. Blocks on nothing outside itself; runs parallel to Wave 2 at the package level (different dirs), integration after.
- Wave 4 (Teacher tooling, C3): todos 22-26. Blocks on 18-19 (API) + 15 (judge endpoints) + 39-40 (anticheat API) for the report UI — anticheat report UI todo 25 is a trailing item exempt from the Wave-4 gate (its API dep todo 39 lives in Wave 7; todo 25 completes right after 39 lands, before the Wave-4 dashboard todo 26 finalizes the anticheat badge).
- Wave 5 (Student UX, C4): todos 27-33. Blocks on API (18-20) + validate endpoint semantics from 7; parallel-safe within wave after 27-28.
- Wave 6 (Sandbox + workers, C6): todos 34-37. Blocks on 7 (CLI contract) + 16 (runs schema).
- Wave 7 (Anticheat engine + deployment): todos 38-42. Blocks on 10-12 (verdicts/schema) for anticheat; deployment blocks on 34-36.
- ALL waves are LOCAL-FIRST (user scope 2026-09-04): every acceptance command runs on the developer's laptop; the full stack is brought up with `docker compose up -d` in HTTP mode (DOMAIN unset); todo 36 explicitly targets localhost, and todo 40 delivers everything as locally dry-run-validated config + runbook (prod-only actions are documented, executed on the UNAM host only after the user provisions it).
- Scaling (user: "be able to scale it"): horizontal path within the plan = stateless RQ workers + Redis queue; `REPLICAS` env raises the worker count; multi-host remains OUT per M10 (single host, more replicas).
- Waves 2 and 3 can run in parallel (different package dirs; integration deferred to Wave 5). Wave 4 and 5 also parallel-safe after their deps land.

### Dependency matrix
| Todo | Depends on | Blocks | Can parallelize with |
| --- | --- | --- | --- |
| 1 (bootstrap) | - | 2-9 | - |
| 2 (SPEC) | 1 | 3-9 | - |
| 3 (lexer) | 2 | 4 | - |
| 4 (parser) | 3 | 5 | - |
| 5 (evaluator core) | 4 | 6,7 | - |
| 6 (subprocesos/arrays/builtins) | 5 | 7,8 | - |
| 7 (CLI + report contract + validate) | 5,6 | 8,9,10,29 | - |
| 8 (golden corpus) | 6,7 | 9 | - |
| 9 (hardening/property) | 8 | (wave gate) | - |
| 10 (judge runner) | 7,8 | 11-15 | 16 |
| 11 (comparison) | 10 | 12 | - |
| 12 (verdicts) | 10,11 | 13,14 | - |
| 13 (complexity bands) | 10,12,2 | 14 | - |
| 14 (scoring + scoreboard) | 12,13 | 15 | - |
| 15 (determinism + budgets glue) | 10,14 | (wave gate), 18 | - |
| 16 (schema + migrations + bootstrap admin) | 1 | 17,18 | 10 |
| 17 (auth) | 16 | 18 | - |
| 18 (REST v1) | 16,17 | 19,20,22-26,27-33 | 15 |
| 19 (WebSocket push) | 18 | 27-33 | 20 |
| 20 (rate limiting) | 16,18 | (wave gate) | 19 |
| 21 (listing/polish endpoints) | 18 | (wave gate) | - |
| 22 (problem admin UI) | 18 | 26 | 23-24 |
| 23 (classes/assignments admin UI) | 18 | 26 | 22,24 |
| 24 (contests admin UI) | 18,15 | 26,32 | 22-23 |
| 25 (anticheat report UI, trailing) | 18,39 | 26 (badge) | - |
| 26 (teacher dashboard) | 22,23,24 (+25 for badge finalization, after Wave 7) | (wave gate) | - |
| 27 (shell + auth pages) | 18,19 | 29-33 | 28 |
| 28 (CodeMirror PseInt mode) | - | 29 | 27 |
| 29 (solve page + inline errors) | 27,28,7 | 30-33 | - |
| 30 (practice sandbox) | 29,19 | 31 | - |
| 31 (results + history) | 29 | (wave gate) | 32-33 |
| 32 (contest page + scoreboard) | 29,24 | (wave gate) | 31,33 |
| 33 (forums) | 29 | (wave gate) | 31-32 |
| 34 (engine container + hardened run) | 7 | 35,36 | - |
| 35 (workers) | 34,16 | 36 | - |
| 36 (docker-compose stack) | 34,35 | 37,40 | - |
| 37 (load/burst pass) | 36 | (wave gate) | - |
| 38 (anticheat similarity engine) | 10-12,16 | 39 | - |
| 39 (similarity report API) | 38 | 25 | - |
| 40 (deployment hardening: HTTPS/backups) | 36 | 41 | - |
| 41 (seed data + docs) | 40,16 | 42 | - |
| 42 (Playwright E2E journeys) | 26,33,32,25,41 | (final) | - |

## Todos
> Implementation + Test = ONE todo. Never separate.
<!-- APPEND TASK BATCHES BELOW THIS LINE WITH edit/apply_patch - never rewrite the headers above. -->

### Wave 1 - Spec + interpreter core (C1)
- [x] 1. Bootstrap the monorepo
  What to do / Must NOT do: `git init` in /home/zum/Documents/Aula CISCO/Interprete; create layout spec/ engine/ judge/ web/api/ web/frontend/ infra/ scripts/; engine/pyproject.toml (name pseint-engine, requires-python >=3.11, no runtime deps, dev = pytest+hypothesis+ruff); judge/pyproject.toml (pseint-judge, deps: engine); root .gitignore (venv, __pycache__, .venv, node_modules, dist, .omo/evidence); README.md stub with architecture one-paragraph. MUST NOT scaffold web apps yet (Vite comes in Wave 5 todo 27); no CI config.
  Parallelization: Wave 1 | Blocked by: - | Blocks: 2-9
  References (executor has NO interview context - be exhaustive): `.omo/drafts/pseint-judge.md` (Decisions D4/D7, Scope IN); skill template at /home/zum/.cache/opencode/packages/oh-my-openagent@latest/node_modules/oh-my-openagent/dist/skills/ulw-plan/references/full-workflow.md (plan contract)
  Acceptance criteria (agent-executable): `cd engine && python -m pytest` exits 0 with "no tests ran"; `cd engine && ruff check src` exits 0; `git -C <root> status --porcelain` empty after initial commit; both packages are importable via `pip install -e` (pip install -e engine + judge succeeds)
  QA scenarios (name the exact tool + invocation): happy: `cd engine && python -m pytest` → exit 0; failure: remove pyproject build config → `pip install -e .` fails with clear error before proceeding. Evidence .omo/evidence/task-1-pseint-judge.txt
  Commit: Y | chore(repo): bootstrap pseint-judge monorepo

- [x] 2. Write the pinned dialect spec (SPEC.md)
  What to do / Must NOT do: Write spec/SPEC.md with MANDATORY sections: (a) grammar EBNF for the whole language; (b) keyword table incl. flexible-syntax synonyms (y/o/no for &|~, Dimensionar, HACER...MIENTRAS QUE, Sin Saltar/Sin Bajar, Segun variants) and accents/eñes-in-identifiers rule; (c) types + conversion matrix (Entero/Real/Logico/Caracter/Cadena; Definir optional under flexible profile, type inferred otherwise; int/int -> real; type mismatch -> RE); (d) operator precedence (algebraic, relational, logical; parens); (e) Escribir formatting table (numbers: integer-as-int, real shortest-roundtrip float with '.', bools Verdadero/Falso, strings raw; Sin Saltar semantics; multi-arg no separator) + 3 golden examples; (f) Leer parsing rules (token split, type inference, EOF -> RE 'fin de entrada inesperado'); (g) step-counting rules table (what counts as 1 step: each statement, each condition eval, each iteration check, each builtin call, each Escribir arg; recursive calls count callee body); (h) deterministic runtime: AZAR seeded per run via test_case.seed (default 0); FechaActual/HoraActual deterministic stubs (fixed ISO 2026-01-01T12:00:00); Esperar no-op costing 1 step; (i) runtime-error taxonomy with codes (ERR_DIV0, ERR_TYPE, ERR_BOUNDS, ERR_DIM, ERR_RECURSION, ERR_EOF_INPUT, ERR_STEP_LIMIT, ERR_OUTPUT_CAP); (j) comparison contract: split \n, strip \r, rstrip each line, compare; leading whitespace + blank lines significant; token mode = split \s+; (k) complexity annotation schema: expected_complexity enum {O(1),O(log n),O(n),O(n log n),O(n^2),O(n^3),O(2^n),other}, step_budget override optional; band formula expected = FORMULA(complexity, n_estimate) with n_estimate = whitespace-token count of input; COEFFICIENT TABLE (normative): O(1)=50 · O(log n)=50·log2(n+2) · O(n)=20n+50 · O(n log n)=20n·log2(n+2)+50 · O(n^2)=5n^2+50 · O(n^3)=2n^3+50 · O(2^n)=2^(n+4) · other ⇒ step_budget REQUIRED (no auto formula); logs floor to integer; band OK<1.5x, ALTA<4x, EXCESIVA else; hard step_budget = 2*expected + 1000. MUST NOT invent features absent from the official reference; every rule is the ONE rule the whole project follows.
  Parallelization: Wave 1 | Blocked by: 1 | Blocks: 3-9
  References: official syntax page https://pseint.sourceforge.net/index.php?page=pseudocodigo.php (fetched 2026-09-04; see Findings in draft); release-note facts https://pseint.sourceforge.net/?os=w32&page=actualizacion.php; `.omo/drafts/pseint-judge.md` M1-M6, M13; Diff-from-official decisions MUST be a dedicated section (deterministic type rules, AZAR seeding, formatting)
  Acceptance criteria (agent-executable): spec/SPEC.md exists and contains every section (a)-(k) with non-empty content; `grep -c "^## " spec/SPEC.md` >= 12; no section left as TODO/blank; each Diff-from-official decision has a one-line rationale
  QA scenarios: happy: automated checklist reads file and confirms section presence -> PASS; failure: a section missing -> script exits 1 listing it. Evidence .omo/evidence/task-2-pseint-judge.txt
  Commit: Y | docs(spec): pin PseInt dialect spec

- [x] 3. Implement the lexer with tests
  What to do / Must NOT do: engine/src/pseint_engine/lexer.py: token types per SPEC (keywords + synonyms, identifiers w/ accents/eñes, integers, reals ('.' separator), strings with " and ' quotes, operators <- = == <> < > <= >= + - * / ^ % MOD & | ~ , ; ( ) :), // comments to EOL; case-insensitive keywords; reserved-word rule for identifiers; token positions (line, col) for error mapping. Must NOT do Unicode normalization of identifiers beyond NFC; must NOT collapse distinct spellings before the parser decides.
  Parallelization: Wave 1 | Blocked by: 2 | Blocks: 4
  References: spec/SPEC.md §grammar + §keywords; draft M5/M6; pytest 8.x for tests
  Acceptance criteria (agent-executable): `cd engine && python -m pytest tests/test_lexer.py -q` — every row of the SPEC keyword table + synonyms has a parametrized case; identifier cases with eñe/accents; 20+ string/number edge cases; `ruff check` clean
  QA scenarios: happy: parametrized pass count matches table rows; failure: feed tokenizer an out-of-range error case (e.g., `1.2.3`) → parse-time error with correct line/col, test asserts it. Evidence .omo/evidence/task-3-pseint-judge.txt
  Commit: Y | feat(engine): lexer

- [x] 4. Implement the parser + AST with tests
  What to do / Must NOT do: engine/src/pseint_engine/parser.py + ast_nodes.py: recursive-descent parser over the lexer; all statements and expressions per EBNF; nested structures; flexible variants (HACER...MIENTRAS QUE, Dimensionar, DE OTRO MODO, Sin Saltar suffix on Escribir, Con Paso on Para); API `parse(source: str) -> Program` raising `ParseError(code, message, line, col)`; public `parse(source)` returning Program on success. Cycle-limit on whitespace recovery (max 1000 tokens to fail fast). Must NOT implement semantic checks here (types/bounds are the evaluator's job).
  Parallelization: Wave 1 | Blocked by: 3 | Blocks: 5
  References: spec/SPEC.md EBNF; draft M1 (CE comes from this phase); golden corpus tier-1 files (created in todo 8) must parse
  Acceptance criteria (agent-executable): `cd engine && python -m pytest tests/test_parser.py -q` green: one test per statement kind, nested permutations, each flexible variant, error-position tests (wrong line/col), reserved-word misuse -> CE
  QA scenarios: happy: parse all 10 tier-1 corpus .psc files → Program objects; failure: `Si x Entonces` without FinSi → ParseError with exact line/col; test asserts both. Evidence .omo/evidence/task-4-pseint-judge.txt
  Commit: Y | feat(engine): parser and AST

- [x] 5. Implement the evaluator core with tests
  What to do / Must NOT do: engine/src/pseint_engine/evaluator.py + runtime.py: Env with scopes; implicit typing + SPEC conversion matrix enforcement; assignment; Escribir (formatting table exactly; Sin Saltar; multi-arg no separator) -> program output lines; Leer (token split, inference, EOF -> RE); Si/Segun/Mientras/Repetir/Para semantics; step counter increments exactly per SPEC §steps; recursion depth cap 500 (SPEC) -> RE ERR_RECURSION. Must NOT apply step budgets here (hard limit is a runner-level option; evaluator only counts).
  Parallelization: Wave 1 | Blocked by: 4 | Blocks: 6,7
  References: spec/SPEC.md §types §steps §formatting; draft M3/M6; 3 golden formatting examples from SPEC must pass verbatim
  Acceptance criteria (agent-executable): `cd engine && python -m pytest tests/test_evaluator.py -q` green covering every control structure, conversion-matrix row, formatting example, step-count assertions (exact counts for small programs), recursion-cap RE
  QA scenarios: happy: run sum-of-n loop program steps == asserted count; failure: int division by zero -> ERR_DIV0 RE with message; tests assert both + metrics. Evidence .omo/evidence/task-5-pseint-judge.txt
  Commit: Y | feat(engine): evaluator core

- [x] 6. Implement SubProceso/Funcion, arrays, built-ins with tests
  What to do / Must NOT do: SubProceso/Funcion (params, Por Valor/Por Referencia; simple-by-value + arrays-by-reference defaults per official rules); recursion (respects depth cap); Dimension (max 3 dims, max elements 1_000_000 per array, per-run total array elements cap 4_000_000 -> ERR_DIM); built-ins exactly per SPEC list: RC ABS LN EXP SEN COS ATAN TRUNC REDON AZAR(seedable) + string/logical set pinned in SPEC (Longitud, SubCadena, Mayusculas, Minusculas, Concatenar, ConvertirANumero, ConvertirATexto); AZAR seeded deterministically. Must NOT add built-ins absent from SPEC.
  Parallelization: Wave 1 | Blocked by: 5 | Blocks: 7,8
  References: spec/SPEC.md §builtins §arrays; official examples (evoclub manual mirrors official behavior; treat as secondary); draft M4 (AZAR seed policy)
  Acceptance criteria (agent-executable): `cd engine && python -m pytest tests/test_subprocesos_arrays_builtins.py -q` green; AZAR(100) with seed 0 pinned constant in test; array bounds + dim caps -> RE; array-by-reference mutation visible at caller
  QA scenarios: happy: recursive factorial(10) == 3628800 with steps recorded; failure: Dimension arreglo(10000000) -> ERR_DIM RE. Evidence .omo/evidence/task-6-pseint-judge.txt
  Commit: Y | feat(engine): subprocesos, arrays, built-ins

- [x] 7. Implement the CLI runner + JSON report contract + validate subcommand
  What to do / Must NOT do: engine CLI (console_scripts entry `pseint-engine`): `run <source.psc> [--input file] [--seed N] [--step-budget N] [--max-steps N] [--max-output-bytes N] [--max-array-elements N] [--report out.json]` — program stdout written to stdout (raw, no wrapping); report JSON to --report with {steps, error: {code,message,line,col}|null, exit_ok, output_bytes}; `validate <source.psc>` prints JSON {ok, errors:[{code,message,line,col}]} (consumed by frontend inline errors, todo 29). Input sources: --input <file> when given, else stdin — the single contract the worker/sandbox wrapper (todo 34) uses. MUST NOT print report to stdout (stdout belongs to program output). Deterministic exit codes: 0 ok, 2 runtime-error, 3 step-limit, 4 output-cap.
  Parallelization: Wave 1 | Blocked by: 5,6 | Blocks: 8,9,10,29
  References: spec/SPEC.md runtime-error taxonomy; draft M3 (budgets); exact CLI flags become the single contract used by worker (todo 34) and validate endpoint (todo 29)
  Acceptance criteria (agent-executable): `cd engine && python -m pytest tests/test_cli.py -q` green; 3 golden programs round-trip run+report with byte-exact stdout and parsed JSON report; validate returns errors with line/col on bad input
  QA scenarios: happy: `echo "1 2" | pseint-engine run suma.psc --seed 0 --report r.json` → stdout matches .out, r.json steps>0; failure: step-budget exceeded → exit 3, report.error.code=ERR_STEP_LIMIT. Evidence .omo/evidence/task-7-pseint-judge.txt
  Commit: Y | feat(engine): CLI runner and report contract

- [x] 8. Build the golden corpus + harness
  What to do / Must NOT do: engine/tests/corpus/ with >=25 cases: `name.psc` (source), `name.in` (input), `name.out` (expected output), `name.json` (expected report subset: steps exact or range, error|null); coverage: all control structures, arrays/matrices, recursion, all built-ins incl. pinned AZAR sequence, flexible synonyms, Escribir formatting goldens (from SPEC), negative cases (div0, type error, bounds, EOF input, recursion cap, step-limit, output-cap — >=5 negative); harness `tests/test_corpus.py` discovers corpus/ and asserts stdout byte-exact + report fields; runner subcommand `pseint-engine corpus` optional. MUST NOT add a case without a one-line comment linking it to a SPEC section. Optional non-blocking hardening: 3-5 manual differential runs against a real PSeInt binary on the developer's machine, with each divergence recorded in SPEC Diff-from-official (documented as optional; not required for any gate).
  Parallelization: Wave 1 | Blocked by: 6,7 | Blocks: 9
  References: spec/SPEC.md (each case cites its section); draft M3 (bands), M4 (AZAR pin), M5 (comparison)
  Acceptance criteria (agent-executable): `cd engine && python -m pytest tests/test_corpus.py -q` — all >=25 cases green (>=5 negative); counts printed; every SPEC feature ≤ 1 case short of covering it
  QA scenarios: happy: full corpus run → 25 passed, 0 failed; failure: mutate one .out by a trailing space → that single case fails, proving byte-exactness. Evidence .omo/evidence/task-8-pseint-judge.txt
  Commit: Y | test(engine): golden corpus

- [x] 9. Harden the engine (property + edge tests)
  What to do / Must NOT do: hypothesis property tests on expressions (bounded depth) asserting no crash beyond documented RE; edge matrix: negative Mod, int/float division, huge string ops, deep recursion (cap), array bounds sweep, Leer EOF, output cap enforcement, step budget enforcement; each case must terminate <2s. MUST NOT test hangs (budgets guarantee termination) without also proving the budget fires.
  Parallelization: Wave 1 | Blocked by: 8 | Blocks: (wave gate) 10
  References: spec/SPEC.md §recovery/error taxonomy; draft M13 (output cap 1MB)
  Acceptance criteria (agent-executable): `cd engine && python -m pytest tests/test_hardening.py -q` green; hypothesis run default deadline passes; `ruff check src` clean
  QA scenarios: happy: property fuzz 5 minutes no unexpected exception (all RE documented); failure: any crash with a message not in the error taxonomy fails the suite. Evidence .omo/evidence/task-9-pseint-judge.txt
  Commit: Y | test(engine): hardening and property tests

### Wave 2 - Judge + scoring engine (C2)
- [x] 10. Implement submission runner (parse-once, run-N)
  What to do / Must NOT do: judge/src/pseint_judge/runner.py: `judge_submission(source, problem, test_cases, mode)` — parse ONCE (via engine parse()) → CE short-circuits (M1, no test cases run); per test case invoke engine CLI as subprocess with per-case seed + budgets; collect {verdict, steps, wall_ms, cpu_ms, output} per case; lazy rules (M2): CF-style stops at first non-AC; IOI-style + assignments run ALL cases; practice-mode passthrough (single run w/ user input, no grading). Must NOT run any test case when parse fails.
  Parallelization: Wave 2 | Blocked by: 7,8 | Blocks: 11-15 | Can parallelize with: 16
  References: spec/SPEC.md comparison + errors; draft M1/M2; CLI contract from todo 7
  Acceptance criteria (agent-executable): `cd judge && python -m pytest tests/test_runner.py -q` green: CE case → no engine subprocess spawned (spy); per-case seeding visible; lazy-stop vs run-all behavior per mode
  QA scenarios: happy: 3-case problem, 2nd case WA in CF mode → 2 results only; failure: same in IOI mode → 3 results (partial points). Evidence .omo/evidence/task-10-pseint-judge.txt
  Commit: Y | feat(judge): submission runner

- [x] 11. Implement output comparison
  What to do / Must NOT do: judge/src/pseint_judge/compare.py: exact-line mode (split \n, strip \r, rstrip each line, compare; leading whitespace + blank lines significant) and token mode (split \s+); returns {equal, first_diff_line, expected_line, got_line}; compare_mode per problem (default exact). MUST NOT trim trailing blank lines below the program's printed content (a trailing newline from the last Escribir is part of output).
  Parallelization: Wave 2 | Blocked by: 10 | Blocks: 12
  References: spec/SPEC.md §comparison; draft M5
  Acceptance criteria (agent-executable): `cd judge && python -m pytest tests/test_compare.py -q` green: CRLF, trailing spaces, blank-line significance, token mode, multi-line diffs
  QA scenarios: happy: exact-match golden passes; failure: expected "5\n" got "5" → not equal (documented); both asserted. Evidence .omo/evidence/task-11-pseint-judge.txt
  Commit: Y | feat(judge): output comparison

- [x] 12. Implement verdict classification
  What to do / Must NOT do: verdicts.py: map engine report codes + comparison + budget outcomes to AC/WA/TLE(step)/TLE(wall, worker-side)/RE(code)/CE; priority table documented in module docstring; per-case verdict record. Must NOT emit verdicts outside this taxonomy.
  Parallelization: Wave 2 | Blocked by: 10,11 | Blocks: 13,14
  References: spec/SPEC.md error taxonomy; draft M1/M2; DOMjudge wall-vs-cpu practice (draft Findings)
  Acceptance criteria (agent-executable): `cd judge && python -m pytest tests/test_verdicts.py -q` green: one test per taxonomy row + priority conflicts (e.g., step-limit beats comparison)
  QA scenarios: happy: correct output → AC with steps; failure: engine ERR_DIV0 + wrong output → RE (priority) not WA. Evidence .omo/evidence/task-12-pseint-judge.txt
  Commit: Y | feat(judge): verdict classification

- [x] 13. Implement complexity bands
  What to do / Must NOT do: complexity.py: per-test expected steps = FORMULA(expected_complexity, n_estimate) using the SPEC coefficient table (todo 2 §k is NORMATIVE: O(1)=50, O(n)=20n+50, O(n^2)=5n^2+50, O(2^n)=2^(n+4), ...; 'other' requires problem.step_budget); band = steps/expected → OK (<1.5) / ALTA (<4) / EXCESIVA; hard step_budget = 2*expected + 1000 (or problem.step_budget override) → TLE(step). Output: per-case {steps, expected_steps, band}. Must NOT fail AC on high band (correctness first; band is a signaled metric).
  Parallelization: Wave 2 | Blocked by: 10,12,2 | Blocks: 14
  References: spec/SPEC.md §complexity schema; draft M3
  Acceptance criteria (agent-executable): `cd judge && python -m pytest tests/test_complexity.py -q` green: O(1)/O(n)/O(n^2)/O(2^n) formula rows assert EXACT integers from the SPEC coefficient table; planted bubble-vs-merge on n=500 → boundary bands correct
  QA scenarios: happy: O(n^2) impl on n=300 → EXCESIVA band but AC verdict; failure: step_budget exceeded → TLE(step) regardless of output. Evidence .omo/evidence/task-13-pseint-judge.txt
  Commit: Y | feat(judge): complexity bands

- [x] 14. Implement scoring engines + scoreboard
  What to do / Must NOT do: scoring.py + scoreboard.py: CF-style (problem solved iff any submission AC; penalty = sum(AC_time_min) + 20 × wrong attempts on solved problems; rank solves desc, penalty asc; teams: solve_time = first AC by any member, wrong attempts = union of team attempts); IOI-style (points = sum per problem of MAX points across submissions; rank points desc); assignment best (per problem: submission with max AC cases, tie-break min steps; resubmissions allowed until deadline); team IOI = max over members. Scoreboard recompute on ANY verdict/points change (CF: AC flip; IOI: per-case point delta; assignment: best-rating change) + nightly batch reconcile (M12). Pinned scoring edges: penalty time = whole minutes since contest start_at; wrong-attempt count EXCLUDES attempts before start_at and attempts after a problem's first AC (and infra retries); team roster locked once the contest starts (no mid-contest edits). Must NOT mix modes; must NOT freeze scoreboards.
  Parallelization: Wave 2 | Blocked by: 12,13 | Blocks: 15
  References: draft D8/D14/D16, M12; CF/IOI scoring norms (draft Findings: DOMjudge/CMS)
  Acceptance criteria (agent-executable): `cd judge && python -m pytest tests/test_scoring.py -q` green: CF penalty arithmetic, teams CF/IOI, IOI max-points, assignment best, tie-breaks (CF solves desc/penalty asc; IOI points desc), same-score ranks stable, IOI partial-update test (a later WA changing points moves the row; CF solved-state unchanged)
  QA scenarios: happy: two students, one solves 2 with 40min penalty vs other solves 1 in 5min → correct order; failure: team member submits WA then teammate AC → solve time = first AC, penalty includes WA. Evidence .omo/evidence/task-14-pseint-judge.txt
  Commit: Y | feat(judge): scoring and scoreboard

- [x] 15. Wire determinism + budgets end-to-end
  What to do / Must NOT do: budget/source/input constants module (source ≤64KB, input ≤64KB, output cap 1MB, wall 5s/cpu 3s/mem 128MB defaults, per-problem overrides); per-run seed plumbing (test_case.seed → engine --seed; contest/assignment runs default 0); rejudge stability test (identical submission twice → byte-identical report+verdicts); practice-mode quota constants (10 runs/min/user). Must NOT randomize anything; must NOT add SSE fallback.
  Parallelization: Wave 2 | Blocked by: 10,14 | Blocks: (wave gate), 18
  References: draft M4/M13/D9; juggling 5: worker consumes these constants (todo 34)
  Acceptance criteria (agent-executable): `cd judge && python -m pytest tests/test_determinism.py -q` green: double-run equality for 5 corpus programs; FechaActual program renders fixed stub value
  QA scenarios: happy: same submission twice → identical JSON; failure: AZAR program without seed change → same output (seeded) asserted. Evidence .omo/evidence/task-15-pseint-judge.txt
  Commit: Y | feat(judge): determinism and budgets

### Wave 3 - Persistence + auth + API (C5)
- [x] 16. PostgreSQL schema + Alembic migrations + bootstrap admin
  What to do / Must NOT do: web/api/src/pseint_api/ with models.py (SQLAlchemy 2.x): tables from Scope IN C5 (all 15); columns: problems.expected_complexity (enum), problems.step_budget (int|null), problems.compare_mode (exact|token); test_cases.seed (int default 0) + points + order + is_public (bool default false — visible to students) + is_sample (bool — exactly one per problem, drives the practice Run sample); classes.anticheat_threshold (float default 0.85, consumed by todo 39); contests.scoring_mode (cf|ioi), teams_enabled (bool default false), start_at/end_at; runs.kind (practice|assignment|contest) + status + summary_verdict; test_results.verdict/steps/wall_ms; forum_threads.contest_id nullable + phase rules implied; similarity_pairs (run_a_id, run_b_id, score, scope); alembic initial revision; bootstrap admin from env ADMIN_USERNAME/ADMIN_PASSWORD at first `alembic upgrade head` (M12). Must NOT use SQLite in prod; engine/judge packages must not import web code.
  Parallelization: Wave 3 | Blocked by: 1 | Blocks: 17,18 | Can parallelize with: 10
  References: draft M12 (schema ownership), D10 (roles), MySQL-out (D3 answer: PostgreSQL)
  Acceptance criteria (agent-executable): fresh DB via `docker compose up -d postgres` then `cd web/api && alembic upgrade head` exit 0; `pytest tests/test_models.py -q` green (CRUD round-trips + unique constraints); bootstrap admin row exists after migrate with env creds
  QA scenarios: happy: migrate on clean DB → 0 errors, tables list matches models; failure: duplicate class code insert → IntegrityError asserted. Evidence .omo/evidence/task-16-pseint-judge.txt
  Commit: Y | feat(api): schema and migrations

- [x] 17. Auth: registration, login, JWT, roles
  What to do / Must NOT do: pwdlib argon2 hashing; register (username, display_name, password ≥8 chars, class_code → joins class; wrong code → 400); login → JWT access token 24h (python-jose or pyjwt); middleware dependency enforcing admin>teacher>student; teacher creation admin-only; password reset by admin (no emails). Must NOT implement refresh tokens, email, or password change email flows.
  Parallelization: Wave 3 | Blocked by: 16 | Blocks: 18
  References: draft D10, M13 (password policy); FastAPI security docs
  Acceptance criteria (agent-executable): `cd web/api && pytest tests/test_auth.py -q` green: register with valid/invalid code, duplicate username 409, login ok/wrong-password 401, JWT expiry test (short-lived override), role guards 403 (student→create problem, teacher→bootstrap)
  QA scenarios: happy: full register→login→authed GET /api/me; failure: student POST /api/problems → 403 body role required. Evidence .omo/evidence/task-17-pseint-judge.txt
  Commit: Y | feat(api): auth and roles

- [x] 18. REST API v1 + integration tests
  What to do / Must NOT do: routers for problems, test-cases (teacher), classes/codes, assignments, contests (+register participant, +teams CRUD when teams_enabled), runs (POST submit → enqueue; list history), validate (POST /api/validate {source} → {ok, errors:[{code,message,line,col}]} thin wrapper over engine validate from todo 7; consumed by todo 22 sample-run CE check and todo 29 inline errors; rate-limited + 64KB cap per todo 20), forums (threads/posts; contest-phase lock: teacher-only posting during live window, D15 + todo 33 phase-lock rule), similarity report endpoints (teacher), scoreboard GET (contest/assignment); Pydantic v2 schemas + status codes; submission flow: POST /api/runs (mode=assignment|contest|practice) → 202 {run_id} → worker (todo 35) → WS event (todo 19); assignment deadline rule: submissions after deadline → 422 ASSIGNMENT_CLOSED (teacher rejudge exempt); practice submissions never graded. Must NOT embed judging; API only enqueues.
  Parallelization: Wave 3 | Blocked by: 16,17 | Blocks: 19,20,22-26,27-33 | Can parallelize with: 15
  References: draft C5/D8/D14/D16, M12; REST conventions; httpx ASGI test patterns
  Acceptance criteria (agent-executable): `cd web/api && pytest tests/test_api.py -q` green (>120 assertions): CRUD per resource, permission matrix, submit→202→run row queued, validate ok/errors + 64KB cap, assignment deadline 422, practice ungraded, scoreboard GET shape per mode, forum lock during contest
  QA scenarios: happy: teacher creates problem+2 cases, student submits → 202, after worker finishes GET run → per-case results; failure: submit with source >64KB → 413. Evidence .omo/evidence/task-18-pseint-judge.txt
  Commit: Y | feat(api): REST v1

- [x] 19. WebSocket push for live results
  What to do / Must NOT do: /ws/submissions endpoint: JWT on handshake (query param token); events {type: submission|run, run_id, status, per_case:[...]} ordered by (run_id, case_index); reconnect with backoff + resume: on connect server replays last 20 submitted runs of the user (M8). Must NOT use SSE; must not multicast between users (only owner/teacher-watching-contest).
  Parallelization: Wave 3 | Blocked by: 18 | Blocks: 27-33 | Can parallelize with: 20
  References: draft M8/D12; starlette WebSocket + asyncio patterns
  Acceptance criteria (agent-executable): `cd web/api && pytest tests/test_ws.py -q` green: handshake with/without token, event ordering, replay-on-connect, broadcast to contest observer limited to participants
  QA scenarios: happy: client receives per-case verdicts as worker finishes; failure: stale token → 4408 close code. Evidence .omo/evidence/task-19-pseint-judge.txt
  Commit: Y | feat(api): websocket push

- [x] 20. Rate limiting + request validation
  What to do / Must NOT do: starlette/redis-backed middleware: per-user runs ≤10/min, submissions ≤30/min; per-IP 60 req/min; 429 + Retry-After; payload caps (source ≤64KB via run schema, input ≤64KB); Validate endpoint (todo 18) reuses the same limits. Must NOT rate-limit healthchecks or static assets.
  Parallelization: Wave 3 | Blocked by: 16,18 | Blocks: (wave gate) | Can parallelize with: 19
  References: draft M13; slowapi or hand-rolled middleware (choose hand-rolled Redis counters, no new dep beyond redis-py)
  Acceptance criteria (agent-executable): `cd web/api && pytest tests/test_ratelimit.py -q` green: burst of 11 practice runs in a minute → 10 ok + 1×429 with Retry-After; per-IP cap tested
  QA scenarios: happy: normal student flow unaffected (assert no 429 under threshold); failure: burst → 429 body describes limit. Evidence .omo/evidence/task-20-pseint-judge.txt
  Commit: Y | feat(api): rate limiting

- [x] 21. Listing/polish endpoints
  What to do / Must NOT do: problemset list with per-user solved state + best verdict; assignment list (deadline, best result, status open/closed); contest list (upcoming/running/ended + registered flag); pagination everywhere; eager-loading to avoid N+1 (selectinload). Must NOT compute scoreboards here (C2 does).
  Parallelization: Wave 3 | Blocked by: 18 | Blocks: (wave gate)
  References: draft C4 (student pages consume these); SQLAlchemy selectinload docs
  Acceptance criteria (agent-executable): `cd web/api && pytest tests/test_listings.py -q` green: list shapes + pagination limits + per-user solved flags
  QA scenarios: happy: 3 problems, 1 solved → solved=true only there; failure: page beyond range → empty list 200 (not 500). Evidence .omo/evidence/task-21-pseint-judge.txt
  Commit: Y | feat(api): listing endpoints

### Wave 4 - Teacher tooling (C3)
- [x] 22. Problem + test-case admin UI
  What to do / Must NOT do: React pages /admin/problems (+/:id): statement editor (markdown preview), expected_complexity select, step_budget override, compare_mode select, test-case table (input textarea, expected output, points, seed, order) + "run sample" button calling skip-judge validation (reuse /api/validate semantics via engine endpoint for CE check only). Must NOT expose student role to this route.
  Parallelization: Wave 4 | Blocked by: 18 | Blocks: 26 | Can parallelize with: 23,24
  References: draft C3; react-router + TanStack Query patterns; Vitest for components
  Acceptance criteria (agent-executable): `cd web/frontend && npx vitest run test/admin-problems.test.tsx` green; Playwright smoke: teacher saves a problem with 2 cases → row visible in list
  QA scenarios: happy: create problem → GET /api/problems reflects it; failure: save with empty expected output → inline validation blocks submit. Evidence .omo/evidence/task-22-pseint-judge.txt
  Commit: Y | feat(web): problem admin

- [x] 23. Classes, assignments, submissions admin
  What to do / Must NOT do: /admin/classes (+/:id): class CRUD + class code display/copy, member list (from self-registration), assignment create (problem + deadline), assignment submissions browser (per-student best, verdict, steps, source view), rejudge button (re-enqueue run). Must NOT allow editing another teacher's class.
  Parallelization: Wave 4 | Blocked by: 18 | Blocks: 26 | Can parallelize with: 22,24
  References: draft C3/D10; rejudge semantics from todo 15 tests
  Acceptance criteria (agent-executable): vitest suite green + Playwright: teacher views assignment results table after student submits
  QA scenarios: happy: rejudge changes result row; failure: teacher B opens teacher A's class → 403 screen. Evidence .omo/evidence/task-23-pseint-judge.txt
  Commit: Y | feat(web): classes and assignments admin

- [x] 24. Contests admin + live scoreboard view
  What to do / Must NOT do: /admin/contests (+/:id): create (title, start_at, end_at, scoring_mode cf|ioi, teams_enabled), problem set reorder, participants (add class/individual), teams CRUD (only when teams_enabled), status badge (upcoming/running/ended), live scoreboard rendering (CF/IOI + team rows), phase-based buttons disabled before start. Must NOT let a contest edit change persisted verdicts (recompute only via rejudge).
  Parallelization: Wave 4 | Blocked by: 18,15 | Blocks: 26,32 | Can parallelize with: 22,23
  References: draft D14/D16, M12 (tie-breaks)
  Acceptance criteria (agent-executable): vitest green + Playwright: teacher runs contest view, scoreboard reflects seeded results; teams mode toggle changes rows
  QA scenarios: happy: CF scoreboard sorts solves desc/penalty asc; failure: teams_enabled=false → team CRUD hidden. Evidence .omo/evidence/task-24-pseint-judge.txt
  Commit: Y | feat(web): contests admin

- [~] 25. Anticheat report UI (consumes todo 39 API)
  What to do / Must NOT do: /admin/anticheat: scope selector (class/contest/problem), threshold input (default 0.85), pairs table (run A, run B, score) sorted desc, same-team exclusion indicator (pre-applied server-side, M12), side-by-side diff viewer of ORIGINAL sources with differing tokens highlighted, CSV export. NOTE (trailing dep): blocks on todo 39 (Wave 7); exempt from the Wave-4 gate, completes after Wave 7 — see Execution strategy. Must NOT auto-penalize; must NOT show to students.
  Parallelization: Wave 4 | Blocked by: 18,39 | Blocks: 26
  References: draft D13/M12; report API contract from todo 39
  Acceptance criteria (agent-executable): vitest green + Playwright: with planted pair (todo 41 seed), teacher sees score ≥ threshold and diff view loads
  QA scenarios: happy: planted pair appears at top; failure: same-team submissions absent from list (exclusion verified). Evidence .omo/evidence/task-25-pseint-judge.txt
  Commit: Y | feat(web): anticheat reports

- [~] 26. Teacher dashboard + navigation
  What to do / Must NOT do: /admin overview: active assignments, upcoming/running contests, flagged-pair count badge, recent submissions; role-aware sidebar. Must NOT duplicate page logic (links only).
  Parallelization: Wave 4 | Blocked by: 22-25 | Blocks: (wave gate)
  References: draft C3; existing page hooks
  Acceptance criteria (agent-executable): vitest green; Playwright: dashboard shows counts that match DB after seeded actions
  QA scenarios: happy: dashboard renders seeded counts; failure: zero-data state renders empty-state text (not crash). Evidence .omo/evidence/task-26-pseint-judge.txt
  Commit: Y | feat(web): teacher dashboard

### Wave 5 - Student UX (C4)
- [x] 27. App shell, auth pages, routing
  What to do / Must NOT do: Vite + React 18 + TS; routes: /login, /register (username, display, password, class_code), / (problems), /problem/:id, /practice, /contest/:id, /submissions, /forum/... ; role-based route guards; token storage + axios interceptor + WS hook (connect/reconnect with backoff + resume refetch per M8); Spanish strings in src/i18n/es.ts (single source). MUST NOT hardcode UI strings outside es.ts.
  Parallelization: Wave 5 | Blocked by: 18,19 | Blocks: 29-33 | Can parallelize with: 28
  References: draft M8/D11; React Router v6, TanStack Query v5
  Acceptance criteria (agent-executable): `cd web/frontend && npx vitest run` green (routing + guards); Playwright: register with seeded class code → lands on /problems
  QA scenarios: happy: student login → authed pages render; failure: student on /admin → redirect /403. Evidence .omo/evidence/task-27-pseint-judge.txt
  Commit: Y | feat(web): app shell and auth

- [x] 28. CodeMirror PseInt language mode
  What to do / Must NOT do: @codemirror/lang-pseint (local package in web/frontend/src/lang): stream parser marking keywords (+synonyms), types, operators, numbers, strings, comments, Verdadero/Falso; NO AST/parse logic client-side (M11) — textmate-style tokenizer only.
  Parallelization: Wave 5 | Blocked by: - | Blocks: 29 | Can parallelize with: 27
  References: draft M11; CodeMirror 6 language authoring guide
  Acceptance criteria (agent-executable): vitest snapshot: tokenization of a representative .psc fixture colors every spec keyword; editor mounts in page
  QA scenarios: happy: syntax classes present for keywords; failure: unknown token left unstyled but page never crashes. Evidence .omo/evidence/task-28-pseint-judge.txt
  Commit: Y | feat(web): codemirror pseint mode

- [x] 29. Solve page + inline syntax errors
  What to do / Must NOT do: /problem/:id: statement pane (markdown) + CodeMirror pane + results pane; desktop 3-pane, mobile stacked (C4 responsiveness); debounced (400ms) POST /api/validate (engine parse from todo 7) → gutter + underline marks with Spanish messages; Submit button → POST /api/runs; assignment/contest context variants. Must NOT implement a client parser; must NOT block typing on validation latency.
  Parallelization: Wave 5 | Blocked by: 27,28,7 | Blocks: 30-33
  References: draft M11/D11; validate contract from todo 7; CodeMirror linter/annotations API
  Acceptance criteria (agent-executable): vitest + Playwright: type invalid code → error mark appears ≤1s after debounce; valid → marks clear; submit enqueues run (202)
  QA scenarios: happy: `Si x Entonces` without FinSi shows mark at line/col matching engine; failure: network down → transient warning, editor unaffected. Evidence .omo/evidence/task-29-pseint-judge.txt
  Commit: Y | feat(web): solve page with inline errors

- [x] 30. Practice sandbox (Run button)
  What to do / Must NOT do: /practice + Solve-page Run: modal for sample input → POST /api/runs {mode:practice} (single runs route per todo 18; never graded) → WS result → output panel + metrics (steps, wall_ms) + error display; sample input = the problem's is_sample test-case input (todo 16), fallback problem.test_cases[0].input for public problems; quota errors (429) shown as friendly notice. Must NOT grade practice runs.
  Parallelization: Wave 5 | Blocked by: 29,19 | Blocks: 31
  References: draft D8 (practice mode), M13 (run quotas)
  Acceptance criteria (agent-executable): Playwright: run with seeded input shows expected output; 10 rapid runs → 11th shows quota notice
  QA scenarios: happy: `Leer n; Escribir n*2` with "21" outputs 42; failure: step limit (infinite Mientras) → TLE(step) message w/ suggested fix. Evidence .omo/evidence/task-30-pseint-judge.txt
  Commit: Y | feat(web): practice sandbox

- [~] 31. Results + history pages
  What to do / Must NOT do: /submissions and /problem/:id/results: per-case table (verdict badge, steps, wall_ms), source viewer, assignment "best" badge (M7), pagination; WS live-updates open run; retry button for failed transport (infra) only. Must NOT allow student to see expected outputs of hidden cases.
  Parallelization: Wave 5 | Blocked by: 29 | Blocks: (wave gate) | Can parallelize with: 32,33
  References: draft M7/D8; run/test_results schema from todo 16
  Acceptance criteria (agent-executable): Playwright: after submit, table shows per-case verdicts + best badge updates on better AC
  QA scenarios: happy: WA case shows first-diff line info (safe subset: line number only); failure: hidden expected output never in payload (assert via network stub). Evidence .omo/evidence/task-31-pseint-judge.txt
  Commit: Y | feat(web): results and history

- [~] 32. Contest page + live scoreboard
  What to do / Must NOT do: /contest/:id: problem list, per-problem status (accepted attempts, score), submit in contest context, phase badges (upcoming/running/ended with countdown), participants list; live scoreboard component (WS-driven refresh on AC-change events, M12) rendering CF (solves/penalty) or IOI (points) incl. team rows when enabled; register button pre-start. Must NOT show scoreboard before contest start or to non-participants.
  Parallelization: Wave 5 | Blocked by: 29,24 | Blocks: (wave gate) | Can parallelize with: 31,33
  References: draft D14/D16/M12
  Acceptance criteria (agent-executable): Playwright: seeded contest shows correct CF ordering; WS event on AC → row moves without reload
  QA scenarios: happy: participant sees own solved count increment live; failure: non-participant GET scoreboard → 403 notice. Evidence .omo/evidence/task-32-pseint-judge.txt
  Commit: Y | feat(web): contest page and scoreboard

- [~] 33. Forums (per-problem threads) + moderation
  What to do / Must NOT do: thread page per problem (+contest problems): top-level posts + replies (parent_id), reply box (real accounts only), teacher actions: pin/edit/delete; contest-phase lock: during [start_at, end_at] contest-problem threads are teacher-post-only, opened automatically after end (M9 fix); pagination. Must NOT allow anonymous/anonymized posts or private messages.
  Parallelization: Wave 5 | Blocked by: 29 | Blocks: (wave gate) | Can parallelize with: 31,32
  References: draft D15/M9; forum tables from todo 16
  Acceptance criteria (agent-executable): Playwright: student posts → appears; during contest window student reply on contest problem blocked with explanatory toast; teacher pins post
  QA scenarios: happy: non-contest problem thread flows freely; failure: after contest ends, student reply succeeds (lock lifted). Evidence .omo/evidence/task-33-pseint-judge.txt
  Commit: Y | feat(web): per-problem forums

### Wave 6 - Sandbox + workers (C6)
- [~] 34. Engine container + hardened run wrapper
  What to do / Must NOT do: infra/Dockerfile.worker (python:3.11-slim + engine + judge, non-root user, no bash where possible MINIMAL deps); scripts/run_sandboxed.py: first run (or setup step) exports Docker's default seccomp profile to infra/seccomp/default.json (producer documented; the file is created by the script, not hand-assumed); docker run --network none --cap-drop ALL --security-opt=no-new-privileges:true --security-opt seccomp=infra/seccomp/default.json (pinned default profile) --memory 128m --cpus 0.5 --pids-limit 64 --read-only --tmpfs /tmp --user 65534:65534 --stop-timeout 8, input via stdin (docs: engine CLI input contract from todo 7 — --input file OR stdin are both supported; wrapper always uses stdin), wall-kill via --stop-timeout + CLI budgets (M9). Worker connects to the Docker socket via a dedicated management network OR documented host-socket mount with the root-equivalent risk called out in OPS.md (M9 requires hardened socket access — prefer the socket via TCP/TLS or a restricted bind-mount with read-only + no privileged scope); API container MUST NOT get the Docker socket. Unit test the wrapper with real engine run; isolation smoke: no network tooling present in image, no host mounts. Must NOT use nsjail; must NOT mount host paths (except a scratch tmpfs).
  Parallelization: Wave 6 | Blocked by: 7 | Blocks: 35,36
  References: draft M9; Docker run reference; CLI contract from todo 7
  Acceptance criteria (agent-executable): `python scripts/run_sandboxed.py <suma.psc` (input via stdin) returns output + report; `docker inspect --format '{{.HostConfig.NetworkMode}}'` == none; `docker inspect --format '{{.HostConfig.SecurityOpt}}'` contains no-new-privileges; image has no curl/wget
  QA scenarios: happy: golden program runs sandboxed → identical stdout; failure: CPU spin program → killed at cpu 3s with TLE. Evidence .omo/evidence/task-34-pseint-judge.txt
  Commit: Y | feat(infra): engine container and hardened run

- [~] 35. Worker pool (RQ)
  What to do / Must NOT do: infra/worker/worker.py: RQ workers (count from $REPLICAS env, default 3 — compose-managed per todo 36) consuming queue 'runs'; job executes judge_submission (todo 10) via the sandbox wrapper (todo 34) as ONE container per submission running all its test cases inside, M2 lazy rules enforced inside that container (parse-once CE short-circuit + CF lazy-stop; IOI/assignments run all); status transitions queued→running→done/failed persisted via API; retries: max 2 for container/infra errors ONLY, never on verdicts (M2); scoreboard recompute on ANY verdict/points change (CF AC flip, IOI point delta, assignment best-rating change — call C2 scoring fns from todo 14) + nightly batch reconcile job; anticheat enqueue trigger (on submission, throttled: run batch when ≥10 new submissions OR manual from report page). Must NOT judge inline in API process.
  Parallelization: Wave 6 | Blocked by: 34,16 | Blocks: 36
  References: draft C6/M12; RQ docs (redis queue patterns)
  Acceptance criteria (agent-executable): `docker compose up -d` then `python scripts/smoke_submit.py` (10 submissions via API) → all reach done with verdicts ≤90s; kill worker mid-job → job retried (≤2), no verdict loss
  QA scenarios: happy: 10/10 verdicts correct in DB; failure: container image missing → job marked infra-failed + retried, API returns 502-consistent status (not wrong verdict). Evidence .omo/evidence/task-35-pseint-judge.txt
  Commit: Y | feat(infra): worker pool

- [~] 36. docker-compose full stack
  What to do / Must NOT do: infra/docker-compose.yml: postgres (volume, healthcheck), redis, api (uvicorn, depends healthy), worker (replicas:$REPLICAS default 3), frontend (static build served by Caddy), caddy (auto-HTTPS via DOMAIN env; HTTP fallback when unset — this is the LOCAL mode used for all plan verification); .env.example documenting every var (incl. ADMIN_USERNAME/ADMIN_PASSWORD, SECRET_KEY, DB pass, REPLICAS); healthchecks each service; smoke script healthz. LOCAL-FIRST: the acceptance "fresh host" IS the developer laptop — `docker compose up -d` with DOMAIN unset must bring the whole stack green at http://localhost. Optional docker-compose.override.yml (gitignored? NO — commit it if local-only tweaks are wanted; keep base compose prod-ready). Must NOT bake secrets into the repo (env-file only, .env in .gitignore); must NOT require a domain or external infra for any acceptance here.
  Parallelization: Wave 6 | Blocked by: 34,35 | Blocks: 37,40
  References: draft D9 (UNAM single VM, internet-facing), M10 (Caddy)
  Acceptance criteria (agent-executable): `cd infra && docker compose config -q` exit 0; `docker compose up -d` on fresh host → all services healthy ≥2min; `curl -sf localhost:80/healthz` OK; `curl -sf localhost:80/readyz` OK once DB+Redis ready (readyz = liveness+readiness split per todo 40)
  QA scenarios: happy: full-stack healthz chain responds; failure: postgres down → api healthcheck reports degraded (not crash-loop silent). Evidence .omo/evidence/task-36-pseint-judge.txt
  Commit: Y | feat(infra): docker-compose stack

- [~] 37. Load/burst pass
  What to do / Must NOT do: scripts/loadtest.py: 200 submissions burst (mixed problems incl. an O(n^2) one) via API as 20 simulated students against the LOCAL compose stack (todo 36, HTTP localhost); assert: all reach done, DB run count == 200 (no loss), p95 verdict latency < 60s from enqueue, worker CPU < 80%; write LOAD.md with numbers + tuning notes (worker count = REPLICAS, memory). Must NOT scale workers mid-test (document instead); must NOT require any external infra.
  Parallelization: Wave 6 | Blocked by: 36 | Blocks: (wave gate)
  References: draft D9 (medium ~200, bursty); M2 (lazy judging reduces load)
  Acceptance criteria (agent-executable): `python scripts/loadtest.py` exits 0 printing the 4 assertions as PASS/FAIL; LOAD.md present with timings table
  QA scenarios: happy: 200/200 accounted with p95<60s; failure: any assertion FAIL → investigate (queue depth, DB pool) and rerun; evidence saved either way. Evidence .omo/evidence/task-37-pseint-judge.txt
  Commit: Y | perf(infra): load pass

### Wave 7 - Anticheat + deployment (C7)
- [~] 38. Anticheat similarity engine (text-level)
  What to do / Must NOT do: judge/src/pseint_judge/similarity.py: normalize(source) = strip // comments, strip all whitespace, lowercase, fold identifier tokens (regex \b[A-Za-z_]\w*\b → "N") (D13); pairwise difflib.SequenceMatcher ratio; scope = per problem within a class grouping or contest; EXCLUDE same-team pairs (M12/D16); batch job writes similarity_pairs (top-k per submission, dedupe); threshold default 0.85 (configurable per class via API). Must NOT use AST fingerprints (user chose minimal text-similarity); must NOT flag same-team pairs; must NOT decide penalties.
  Parallelization: Wave 7 | Blocked by: 10-12,16 | Blocks: 39
  References: draft D13/M12/D16; difflib docs
  Acceptance criteria (agent-executable): `cd judge && pytest tests/test_similarity.py -q` green: planted renamed-variable pair ≥0.85; two different algorithms (bubble vs merge) <0.85; same-team pair excluded
  QA scenarios: happy: copied-with-renames pair flagged; failure: legit different solutions not flagged (threshold boundary test). Evidence .omo/evidence/task-38-pseint-judge.txt
  Commit: Y | feat(judge): anticheat similarity engine

- [~] 39. Similarity report API + threshold config
  What to do / Must NOT do: API routes (teacher): GET /api/admin/anticheat?scope=&threshold= → pairs (run ids, usernames, score) desc; GET /api/admin/anticheat/pair/:a/:b → original sources + normalized render for diff UI (todo 25); POST /api/admin/classes/:id/anticheat-threshold; triggers: manual + automatic batch enqueue from worker (todo 35). Must NOT return normalization leaks (only original + flag).
  Parallelization: Wave 7 | Blocked by: 38 | Blocks: 25
  References: draft D13; similarity schema from todo 16
  Acceptance criteria (agent-executable): `cd web/api && pytest tests/test_similarity_api.py -q` green: seeded pair appears, threshold filter works, 403 for students
  QA scenarios: happy: teacher fetches pair diff payload; failure: non-teacher GET → 403. Evidence .omo/evidence/task-39-pseint-judge.txt
  Commit: Y | feat(api): similarity report API

- [~] 40. Deployment hardening (HTTPS, backups, ops) — LOCAL dry-run; UNAM execution is post-plan
  What to do / Must NOT do: Caddyfile (auto-HTTPS when DOMAIN set; security headers; CORS same-origin-only — API rejects cross-origin browser calls unless a CORS_ALLOW_ORIGINS env allowlist is set), ufw guide (default-deny inbound; allow 80/443 + SSH from admin scope; fail2ban for SSH), scripts/backup.sh (pg_dump daily, 7-day retention, cron install, off-host copy documented — external backup target direction in OPS.md), SECRET_KEY startup validation (refuse to boot with len<32 or default value), /healthz + /readyz endpoints + docker healthchecks, JSON structured logs, OPS.md runbook (deploy, upgrade, restore, worker resize, password reset, DB pool sizing, Docker-socket access model, backup restore drill). LOCAL-FIRST RULE: all artifacts above are written, committed and DRY-RUN-VALIDATED locally (config parses, runbook complete, health/ready endpoints green over HTTP); the ONLY prod-only actions (real auto-HTTPS via a real DOMAIN, ufw/fail2ban enforcement on the host, real off-host backup cron) are DOCUMENTED for the UNAM host and executed there only after the user provisions it — never during this plan. Must NOT rely on manual steps that the runbook doesn't document; must NOT commit any real secret.
  Parallelization: Wave 7 | Blocked by: 36 | Blocks: 41
  References: draft M10 (Caddy)/D9 (internet-facing UNAM)/M13 (backups)
  Acceptance criteria (agent-executable, LOCAL gate): `docker compose config --quiet` + `curl -sf http://localhost:80/healthz` → 200 and `curl -sf http://localhost:80/readyz` → 200 (once ready); backup.sh run → dump file exists, restore into fresh scratch DB works; OPS.md documents ufw default-deny, fail2ban, off-host backups, Docker-socket access model, SECRET_KEY validation message. UNAM-only verification (NOT plan acceptance, documented in OPS.md for post-plan): with real DOMAIN set, `curl -I https://<domain>/healthz` → 200 and `/readyz` → 200 (Caddy auto-renew note)
  QA scenarios: happy: restore drill on a scratch DB; failure: expired cert scenario documented (Caddy auto-renew note). Evidence .omo/evidence/task-40-pseint-judge.txt
  Commit: Y | feat(ops): deployment hardening

- [~] 41. Seed data + docs
  What to do / Must NOT do: scripts/seed.py: admin + teacher + 1 class w/ code + 20 students; 4 problems: HolaMundo (O(1), practice), Suma (assignment, O(1)), Primo (assignment, O(n) expected, step_budget from formula), Fibonacci (contest problem, expected O(n); planted O(n^2) and O(2^n) student solutions to demo bands), 1 contest CF-mode w/ participants + 1 planted copied pair (renamed vars, for todo 25 demo); README.md (LOCAL quickstart FIRST: clone → `docker compose up -d` (DOMAIN unset) → seed → open http://localhost; architecture diagram (mermaid); env vars; then the post-plan UNAM switch-over section); OPS.md already from 40. Must NOT seed passwords other than documented demo-credentials section.
  Parallelization: Wave 7 | Blocked by: 40,16 | Blocks: 42
  References: draft M13 (demo creds), C3/C4 flows; seed uses API models directly
  Acceptance criteria (agent-executable): `pip install -e web/api && python scripts/seed.py` exit 0; exact count check (table names per todo 16, never model-class names): `docker compose exec -T api python -c "from sqlalchemy import text; from pseint_api.db import engine; c=engine.connect(); print([c.execute(text(f'SELECT count(*) FROM {t}')).scalar() for t in ['users','classes','problems','contests']])"` → prints `[22, 1, 4, 1]` (users = 1 admin + 1 teacher + 20 students; 1 class; 4 problems; 1 contest)
  QA scenarios: happy: seeded login as teacher shows all 4 problems; failure: rerun seed → idempotent (no duplicates) asserted. Evidence .omo/evidence/task-41-pseint-judge.txt
  Commit: Y | docs: seed data and runbook

- [~] 42. Playwright E2E journeys
  What to do / Must NOT do: e2e/ journeys: (a) student registers w/ class code → sees assignment, opens solve page, gets inline error, fixes, Runs sample, submits → verdict shown; (b) assignment best-count: two submissions → best badge = better one; (c) contest: register pre-start, submit during, scoreboard updates live; (d) forum: post + teacher pin; contest-window lock blocks student reply; (e) teacher anticheat: report shows planted pair + diff viewer; (f) mobile viewport 375px solve page usable. Tests run against the LOCAL docker-compose stack (DOMAIN unset, http://localhost) with seeded data (todo 41); no external infra. Must NOT stub WS (real end-to-end).
  Parallelization: Wave 7 | Blocked by: 26,33,32,25,41 | Blocks: (final)
  References: draft C4 flows; Playwright docs; seeded fixtures
  Acceptance criteria (agent-executable): `cd web/frontend && npx playwright test e2e` — all 6 journeys green against the compose stack
  QA scenarios: happy: (a)-(f) assertions pass on desktop; failure: mobile journey (f) fails viewport overflow check → layout fix required. Evidence .omo/evidence/task-42-pseint-judge.txt
  Commit: Y | test(e2e): full journeys

## Final verification wave
> Runs in parallel after ALL todos. ALL must APPROVE. Surface results and wait for the user's explicit okay before declaring complete.
- [~] F1. Plan compliance audit
- [~] F2. Code quality review
- [~] F3. Real manual QA
- [~] F4. Scope fidelity

## Commit strategy
- Conventional Commits (feat/fix/test/docs/chore/perf with scope), one per todo as annotated. Branch strategy: work directly on `main` in this monorepo (single contributor), OR use a task-owned worktree via `$start-work --worktree <path>` when the user asks for PR/branch mode. Every commit must leave the tree green (tests pass) — no WIP commits.
- Tags: `engine-v1`, `judge-v1`, `api-v1`, `deploy-v1` at wave gates for rollback points.
- Secrets never committed; .env ignored.

## Success criteria
- LOCAL-FIRST (primary gate): on the developer's laptop, a fresh clone + `docker compose up -d` (DOMAIN unset, HTTP) + seed brings the whole platform online at http://localhost and passes the todo-42 E2E journeys — verified locally before ANY UNAM provisioning.
- UNAM switch-over is DOCUMENTED (OPS.md/README) and NOT executed in this plan; F1-F4 verify the LOCAL stack only (fresh clone → `git clone && docker compose up -d` on the developer laptop → seed → todo-42 journeys green at http://localhost).
- Engine corpus (>=25 golden cases) green; any change to the dialect spec requires a corpus case first (TDD lock).
- 200-submission burst completes with p95 < 60s and zero lost runs (todo 37 evidence).
- Complexity bands meaningfully separate planted bad algorithms (F3 spot-check; todo 13/41 evidence).
- Anticheat catches the planted renamed-variable copy and excludes teammates (todo 38/42 evidence).
- Mobile (375px) solve page usable; desktop 3-pane layout intact (todo 42).
- All final verification (F1-F4) APPROVE with receipts under .omo/evidence/ before the user is asked to declare completion.