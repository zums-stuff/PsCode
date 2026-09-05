---
slug: pseint-judge
status: review-round-active
intent: clear
review_required: true
pending-action: review .omo/plans/pseint-judge.md
approach: Build the pseint-judge monorepo: Python interpreter core (pinned canonical-modern PseInt dialect, deterministic semantics, built-in step counter) + React/TypeScript web frontend + FastAPI backend + PostgreSQL + Redis queue + sandboxed worker pool; judge grades correctness per test case plus measured operation-steps against the teacher-annotated expected complexity (wall-clock + step budgets as safety); TDD with a golden .psc conformance corpus throughout.
---

# Draft: pseint-judge

## Components (topology ledger)
<!-- Lock the SHAPE before depth. One row per top-level component that can succeed or fail independently. -->
<!-- id | outcome (one line) | status: active|deferred | evidence path -->
<!-- Topology confirmed by user 2026-09-04 (answers a,a,a,d,a; no amendments). -->

- C1 Interpreter core | lexer -> parser -> AST -> evaluator for the pinned PseInt dialect, deterministic semantics, step counter, runtime-error taxonomy | active | .psc dialect pinned from official docs + suite
- C2 Judge + scoring engine | per-submission parse once, run N test cases, inject input, capture output, compare, emit verdicts (AC/WA/TLE/RE) + step/time metrics; contest scoring rules (CF-style / IOI-style, configurable); scoreboard computation | active | DOMjudge/DMOJ practices
- C3 Teacher tooling | problems CRUD, test cases, expected-complexity annotation, classes & class codes, assignments, contests (CRUD, participant lists, schedule), forum moderation, anticheat reports, scoreboard admin | active | depends on C1..C2, C5
- C4 Student UX | responsive (desktop+phone) app: problem list, solve page with CodeMirror editor + inline syntax feedback, Run button (practice), submit, live result via WS, history, contest page with live scoreboard, forum threads/comments | active | depends on C1..C2, C5
- C5 Persistence + auth + API | users(admin/teacher/student), classes, problems, assignments, contests, submissions, results, forum data, anticheat reports; REST + WebSocket push | active | standard
- C6 Sandboxing + workers | isolated execution of the engine per submission, no network, CPU/mem caps, queue/worker pool (3 workers, horizontal-ready), anticheat + scoreboard batch jobs, hardened for internet-facing UNAM host | active | nsjail/Docker + cgroups/rlimits
- C7 Anticheat engine | minimal text-similarity only (user pick): normalized-source comparison (comments/whitespace/case-insensitive, identifier-insensitive), pairwise scores per problem/class/contest, flag thresholds, teacher report + side-by-side diff viewer (own module, background job) | active | MOSS-style approach, text-level

## Open assumptions (announced defaults)
<!-- Record any default you adopt instead of asking, so the user can veto it at the gate. -->
<!-- assumption | adopted default | rationale | reversible? -->

- Platform UI language | Spanish | entire PseInt ecosystem is Spanish; students are Spanish-speaking (CISCO/Aula context) | yes
- Engine implementation language | Python (D4, confirmed) | interpreter consumes program text as data; safety enforced inside interpreter + OS sandbox; Python = velocity + readability | yes
- Teacher provisioning | bootstrap admin creates teacher accounts (students self-register via class code per user answer) | simplest-secure for UNAM deployment | yes
- Output comparison | exact per-line after trimming trailing whitespace; optional token-based mode per problem | matches how Escribir formats output | yes
- Repo layout | monorepo: engine/ (package), judge/, web/, infra/ | | yes
- Not a git repo yet | plan includes git init + commit strategy | | yes

## Findings (cited - path:lines)
<!-- Verify: (1) syntax page fetched | (2) wikipedia entry | (3) sourceforge actualizacion | (4) domjudge docs | (5) nsjail README -->

- Research done directly by planner: background librarian subagents unavailable in this environment (ProviderModelNotFoundError), so primary sources fetched/verified directly.
- Official PseInt syntax reference (https://pseint.sourceforge.net/index.php?page=pseudocodigo.php): warnings that flexible syntax/profiles exist; original grammar only 3 base types (numeric, char/string, logical); structures Proceso/FinProceso, <- assignment, Leer, Escribir, Dimension (multi-dim arrays), Si/Entonces/SiNo/FinSi, Segun/De Otro Modo/FinSegun, Mientras/Hacer/FinMientras, Repetir/Hasta Que, Para/Con Paso/Hacer/FinPara; operators > < = <= >= & | ~ + - * / ^ % ; built-ins RC ABS LN EXP SEN COS ATAN TRUNC REDON AZAR; // comments; identifiers letters+digits start letter, no reserved words; char constants in double quotes; Verdadero/Falso.
- PSeInt is GUI (GTK, C++, GPL v2) for Windows/macOS/Linux; Linux = tgz, run ./pseint (https://pseint.sourceforge.net/?page=descargas.php). Docs page admits "muy desactualizado"; real reference = built-in help + release notes.
- Release notes (https://pseint.sourceforge.net/?os=w32&page=actualizacion.php): profiles (perfiles) per university, flexible syntax synonyms (Dimensionar, HACER...MIENTRAS QUE, acentos/eñes option), added primitives over time (Redimensionar, Esperar, FechaActual, HoraActual), interpreter+GUI are separate executables that talk to each other ("Destripando PSeInt" blog, 2012). Tests exist in upstream for control structures.
- DOMjudge judging docs (https://www.domjudge.org/docs/manual/main/judging.html): time limits enforced primarily in CPU time with a laxer wall-clock hard cap (soft/hard pair), per-language time factors, cgroups memory limits, lazy judging stops at first non-AC result, rejudging semantics.
- nsjail (https://github.com/google/nsjail): namespaces (pid/mount/net/user/cgroup), seccomp-bpf (Kafel), rlimits (cpu/as/nofile/nproc), cgroup v1+v2 integration, wall-time limit. IOI isolate used by judge0 similarly (CPU limit + extra time + wall limit).
- No established deterministic Big-O grader exists (websearch: TimeComplexity.ai, BigOCalc = AI heuristics; step-count method is textbook, GeeksforGeeks). => custom deterministic op-count inside interpreter is the defensible approach.

## Decisions (with rationale)

- D1 Time semantics (user answer a): judging = deterministic operation-step counting against teacher-annotated expected complexity per problem, PLUS wall-clock timeout + step budget as safety caps. Rationale: interpreted pseudocode on small inputs is near-zero wall-clock; steps carry the "algorithm quality" signal. Verdict taxonomy: AC / WA / TLE (wall or budget) / RE (runtime error incl. step-limit, recursion-depth, array-bounds, division-by-zero, type error) / CE (syntax/parse error).
- D2 Form factor (user answer a): full multi-user web platform, responsive for phones + desktop. Teacher + student roles, classes/groups, assignments with deadlines, problem CRUD, scoreboard.
- D3 Dialect (user answer a): canonical modern PseInt core as OUR pinned spec: Spanish keywords, Definir/Dimension/SubProceso/Funcion/Segun/Mientras/Repetir/Para/Esperar, built-ins (RC ABS LN EXP SEN COS ATAN TRUNC REDON AZAR + string/logical functions), flexible-syntax variants on (synonyms, accents/eñes in identifiers), Verdadero/Falso; documented in a SPEC.md + golden conformance corpus of .psc files. Diff-from-official decisions recorded explicitly (deterministic type rules; Escribir formatting).
- D4 Stack (user answer d -> planner picked a, confirmed by user): Python-first. Interpreter core = Python package; API = FastAPI + Pydantic; DB = PostgreSQL (SQLAlchemy/Alembic); queue = Redis + RQ workers; frontend = React + TypeScript (Vite); sandbox = Docker hardened (no network, dropped caps, non-root, cgroups cpu/mem) + internal interpreter budgets.
- D5 Test strategy (user answer a): TDD. Lexer/parser/evaluator unit tests; golden corpus programs with expected stdout; judge-engine tests per verdict; API integration tests; frontend vitest + Playwright smoke.
- D6 UI language: Spanish. Output comparison: per-line exact after trailing-whitespace trim; per-problem optional token-based mode (adopted default, veto at gate).
- D7 One plan covering C1-C7 in dependency waves (anticheat engine lands after judge + schema); repo git-init at start (adopted default; folder is not a repo yet).
- D8 Submission modes (user, revised): (i) PRACTICE = unrated sandbox section: free experimentation, "Run" button executes with user-provided sample input, no test-case grading; (ii) ASSIGNMENT = deadline + unlimited resubmissions, best submission counts; (iii) CONTEST = Codeforces-style: problem set, start/end time, live scoreboard, participants = class(es)/registered list, scoreboard visible to participants, no freeze (classroom scale). User override: the earlier "EXAM single-submission" idea is dropped; contests were the original motivation.
- D13 Anticheat (user, minimal): normalized text-similarity module. Normalize each submission (strip comments + whitespace, lowercase, optional identifier-fold), pairwise similarity per problem scope (class/contest wide), flag above teacher-set thresholds, report UI with side-by-side diff. Reports only — no automatic penalties. Separate from API-rate limiting (contest hygiene, not similarity).
- D14 Contest scoring (user): both modes configurable per contest — Codeforces-style (full AC per problem, penalty time = sum of solve-times + 20min per wrong attempt on solved problems) OR IOI-style (partial points per test case, no penalty). Scoreboard computation supports both; UI shows chosen format.
- D15 Forums (user): per-problem discussion threads (one thread per problem, incl. contest problems) with threaded replies, student posting, teacher answer + pin, role-based moderation (edit/delete by teachers), real accounts only. No general board, no private messaging.
- D16 Teams in contests (user): OPTIONAL, not default. Per-contest setting teams_enabled (default false). When on: contest admin (teacher) creates named teams from registered participants; each participant in at most one team per contest; any team member may submit and every submission counts toward the team; scoreboard ranks teams instead of individuals; forums remain per-account. Team scoring: CF-team solve_time = first AC by ANY member; wrong attempts = union of team attempts on that problem; IOI-team points = max across members. Sub-decisions adopted (veto at gate): team creation by teacher only; same-team submissions excluded from anticheat pairwise comparison (C7 + Scope IN C7).
- D17 Deployment tiers (user scope change 2026-09-04): LOCAL-FIRST. Tier 0 = developer laptop: `docker compose up -d` with DOMAIN unset (plain HTTP at localhost), full stack incl. sandbox judging; all plan acceptances (todo 36/37/41/42, F1-F4) run locally. Tier 1 = UNAM production wiring (real DOMAIN auto-HTTPS, ufw/fail2ban, off-host backups) is DOCUMENTED in todo 40 as dry-run-validated artifacts and executed ONLY when the user provisions the host — post-plan, never during plan execution. Scale path = stateless RQ workers behind Redis, REPLICAS env raises count; multi-host OUT (M10).

## Metis fold-in resolutions (2026-09-04, gap analysis ses_f9033e694ffebpw9PEAZ2pzO1E)
- M1 CE verdict: parse-once phase yields CE, no test cases run. C2 emits AC/WA/TLE/RE/CE.
- M2 Lazy judging: applies to CF-style only; IOI-style and assignments run ALL test cases (partial points/max need them).
- M3 Step semantics: SPEC.md defines the counting-rules table; expected-complexity annotation schema = complexity enum {O(1),O(log n),O(n),O(n log n),O(n^2),O(n^3),O(2^n),other} + optional per-problem step_budget override; grading rule = correctness first; steps = quality band (OK/ALTA/EXCESIVA vs budget-derived expectation); step budget itself is a HARD TLE safety. Formula: per-test expected = FORMULA(complexity, n_estimate) where n_estimate = whitespace-token count of input; band = steps/expected (OK <1.5, ALTA <4, EXCESIVA else); step_budget = 2×expected + 1000.
- M4 AZAR determinism: RNG seeded per run with test_case.seed (default 0); SPEC pins AZAR(100) sequence; FechaActual/HoraActual = deterministic stubs (fixed ISO values documented in SPEC); Esperar = no-op with step cost.
- M5 Comparison contract: split on \n, strip \r, rstrip each line, compare; leading whitespace and blank lines SIGNIFICANT; token mode = split on \s+ (per-problem compare_mode field). Escribir formatting table + 3 golden examples mandatory in SPEC.
- M6 Type rules: SPEC requires Definir optionality rule (default: flexible profile — typing inferred; Definir accepted), conversion matrix, / semantics (int/int → real), type-error → RE cases, each with a golden .psc example.
- M7 Assignment 'best': rating per problem = AC > partial (IOI-style points on assignment? assignments use pass/fail per test + steps; rating = AC primary (all cases pass), then min steps among ACs; simplest: best = submission with max cases AC, tie-break min steps.
- M8 Transport pinned: native WebSocket (FastAPI) with JWT handshake; reconnect with backoff + resume via history refetch; events ordered by (submission_id, case_index). SSE dropped.
- M9 Sandbox pinned: Docker only (nsjail rejected): --network none --cap-drop ALL --memory 128m --cpus 0.5 --pids-limit 64 --read-only --tmpfs /tmp --user 65534:65534; defaults wall 5s / cpu 3s / mem 128MB / output 1MB; per-problem overrides; source ≤64KB, input ≤64KB.
- M10 Proxy + scope: Caddy (auto-HTTPS) only, nginx rejected. 'Horizontal-ready' = stateless workers + Redis queue only; multi-node deployment OUT.
- M11 Inline errors: debounced (400ms) POST /api/validate reusing the SAME engine parser (no JS reimplementation); CodeMirror does keyword highlighting only.
- M12 Schema/ownership: add contest_teams/contest_team_members tables; problem.expected_complexity + problem.step_budget + test_case.seed columns; bootstrap admin via env (ADMIN_USERNAME/ADMIN_PASSWORD) at first migrate; rate limiting owned by C5 API middleware; scoreboard = live recompute on AC change (C2) + nightly batch reconcile (C6); tie-breaks CF: solves desc, penalty asc; IOI: points desc.
- M13 Runtime guardrails (LOW items adopted as defaults): password min 8 chars; JWT 24h; run quotas (10 runs/min/user, 30 submissions/min/user, 60 req/min/IP); output cap 1MB; backups pg_dump daily + 7-day retention.
- D9 Deployment (user): internet-facing, hosted on UNAM infrastructure (single Linux VM expected; docker-compose). Includes reverse proxy + HTTPS (Let's Encrypt), rate limiting, hardened sandboxing (no network, dropped capabilities, non-root user, seccomp/cgroup limits), DB backups, health monitoring. Medium scale (~200 students, bursty at deadlines): Redis queue + 3 workers, lazy judging (stop at first failing case), design ready to add workers horizontally.
- D10 Accounts (user): students self-register with a class code (no email); teachers provisioned by a bootstrap admin (adopted default, veto at gate).
- D11 Frontend (user): editor = CodeMirror 6 with PseInt keyword highlighting + inline span error marks; layout = Codeforces-minimal desktop (problem statement | editor | results) collapsing to stacked mobile.
- D12 Backend live updates (user): WebSocket/SSE push of verdicts from worker -> API -> browser; teacher admin = custom in-app admin pages (not auto-generated).

## Scope IN

- C1 Interpreter: lexer, parser (pinned dialect incl. flexible-syntax variants), AST, evaluator, step counter, runtime-error taxonomy, Escribir/Leer semantics, Dimension/arrays (bounds + caps), SubProceso/Funcion (value/ref params, recursion depth cap), built-ins.
- C2 Judge engine: parse-once/run-N, input injection, output capture, comparison (exact-line default, token option), verdicts, per-test metrics (steps, wall, cpu).
- C3 Teacher: problem CRUD, test-case CRUD, expected-complexity + budget annotation, classes & class codes, assignments, contests (CRUD, participant registration, schedule), forum moderation, anticheat reports, scoreboard admin, submission detail, bulk view.
- C4 Student: responsive UI (desktop + phone), problem list by assignment, solve page (CodeMirror editor + live syntax errors), practice Run button with sample input, submit, per-test result + steps, history, contest page with live scoreboard, forum threads/comments.
- C5 Auth/API: roles (admin/teacher/student), self-registration with class code, JWT sessions, REST + WebSocket push; DB schema via migrations; contest/forum/anticheat-report tables.
- C6 Sandbox/workers: Redis queue, worker pool (3, horizontal-ready), per-submission isolation (no network, dropped caps, non-root, cgroups cpu/mem, wall/step budgets), anticheat + scoreboard batch jobs, retries, status propagation.
- C7 Anticheat: text-similarity module — normalize (strip comments/whitespace, lowercase, optional identifier fold), pairwise scores per problem scope, thresholds, teacher report with side-by-side diff. No automatic penalties. API rate limits = separate contest-hygiene concern.
- Forums: per-problem thread + threaded comments, student/teacher posting, teacher moderation (edit/delete/pin), real accounts.
- Contests: model + registration + live scoreboard + per-contest scoring config (CF-style full-clear + penalty OR IOI-style partial points) + optional teams (teams_enabled per contest, default off; teacher-created teams, any-member submissions count, team-scoreboard, same-team pairs excluded from anticheat).
- Deployment: docker-compose on UNAM Linux VM; Caddy/nginx reverse proxy + HTTPS (Let's Encrypt); rate limiting; backups; health checks.
- Tests: TDD golden corpus + unit + integration + Playwright smoke; seed data with 4 example problems + 1 sample contest + a planted copied-submission pair to demo anticheat.
- Docs: SPEC.md (dialect), README, docker-compose deploy.

## Scope OUT (Must NOT have)

- No graphs/flowchart rendering (PSeInt's diagram editor is out of scope).
- No user-uploaded code execution beyond the pinned dialect (no arbitrary-language judging).
- No multi-tenant public SaaS launch: single-institution deployment on UNAM infra (self-hosted, one server).
- No email flows: no email verification, no password reset-by-email (students use class-code self-registration; admin resets passwords).
- Anticheat guardrails: no camera/webcam proctoring, no IP tracking, no "AI-written code" detection (novice pseudocode makes it meaningless), no automatic penalties from similarity (reports only — teacher decides).
- Contests guardrails: teams OPTIONAL per contest (default individual — user decision); no CF-style rating system, no scoreboard freeze (classroom scale).
- Forums guardrails: role-gated posting and moderation; no anonymous posting; no private messaging.
- No in-browser execution of pseudocode; all judging server-side (keeps one source of truth for verdicts).
- No exported .psc diagrams or code-generation to C/Java/JS/Python (PSeInt feature, out of scope here).

## Open questions

- All resolved (interview completed 2026-09-04, three turns). Remaining decisions are planner-level and recorded above.

## Approval gate
status: approved
approved_by: user ("Proceed.") 2026-09-04
approach: <see frontmatter> 
next: write .omo/plans/pseint-judge.md (Metis gap analysis first, then scaffold-equivalent + todos + TL;DR), then deliver handoff (review not required; offer start-or-review question).
<!-- The durable record is the loop guard: on a later turn read it and resume at the gate instead of re-running exploration. -->

## High-accuracy review round (requested by user 2026-09-04)
### Round 1 (rr-20260904-01) — COMPLETE: changes_requested (both reviewers)
binding: workspace_root /home/zum/Documents/Aula CISCO/Interprete, target .omo/plans/pseint-judge.md, runtime_home /home/zum
- momus (ses_f902b20e8ffeKIwY3dpU22hD62): CHANGES_REQUESTED — 6 findings
- independent/oracle (ses_f902af891ffeJLrx9ytmqiHAcO): CHANGES_REQUESTED — 7 findings
- Fix summary (all folded into .omo/plans/pseint-judge.md, no plan restructure needed):
  1. [B×2] POST /api/validate has an owner: todo 18 now builds it (thin wrapper over engine validate, rate-limited, 64KB cap); todo 18 acceptance asserts ok/errors + cap; consumers todo 22 + todo 29 cite the endpoint.
  2. [B] Todo 35 decision deferred → pinned: ONE container per submission running all its test cases inside (M2 lazy rules enforced in-container; CF lazy-stop, IOI/assignment run all); todo 34 wrapper text + matrix row updated.
  3. [B] Schema gaps closed: todo 16 adds test_cases.is_public + is_sample and classes.anticheat_threshold (0.85); todo 30 practice sample uses is_sample; todo 39 consumes the column.
  4. [M] FORMULA coefficients pinned as NORMATIVE table in todo 2 §k (O(1)=50, O(log n)=50·log2(n+2), O(n)=20n+50, O(n log n)=20n·log2(n+2)+50, O(n^2)=5n^2+50, O(n^3)=2n^3+50, O(2^n)=2^(n+4), other→step_budget REQUIRED); todo 13 asserts exact integers from it.
  5. [M] Scoreboard recompute → ANY verdict/points change (CF AC flip, IOI point delta, assignment best-rating) in todos 14 + 35; IOI partial-update test added to todo 14 acceptance.
  6. [M] Assignment late rule pinned: todo 18 → 422 ASSIGNMENT_CLOSED after deadline (teacher rejudge exempt); acceptance test added.
  7. [M] Sandbox hardening: todo 34 adds --security-opt=no-new-privileges:true + pinned default seccomp + Docker-socket access model (API container never gets the socket; OPS.md documents the risk); todo 40 adds SECRET_KEY startup validation, ufw default-deny + fail2ban, off-host backup, DB pool sizing; acceptances assert NoNewPrivileges + OPS.md sections.
  8. [m] todo 41 `...` placeholder → exact sqlalchemy counts query (22 1 4 1 expected).
  9. [m] todo 18 M-9 citation → D15 + todo 33 phase-lock rule.
  10. [m] Practice route unified: POST /api/runs {mode:practice} single route (todos 18 + 30).
  11. [m] todo 25 marked trailing (blocks on Wave-7 todo 39; exempt from Wave-4 gate); matrix rows 25/26 + Wave-4 bullet updated.
  12. [m] todo 7 input contract clarified (--input file OR stdin; wrapper uses stdin); todo 36 healthz+readyz aligned with todo 40.
- Round-1 receipts recorded; both verdicts were CHANGES_REQUESTED with fully resolved items.

### Round 2 (rr-20260904-02) — COMPLETE: approved by both (unconditional), then 3 minor pins applied
- momus (ses_f90250153ffeHzQlyWpIxYjFu1): APPROVE unconditional — all 12 fix items VERIFIED, no new findings
- independent/oracle (ses_f9024e1c7ffeY0lAkz00lk5gn0): APPROVE unconditional — all 12 VERIFIED; 3 worker-resolvable minors suggested (no re-approval required by reviewer)
- Post-approval pins applied (ORACLE minors, folded for zero-executor-judgment):
  1. Todo 40: CORS same-origin-only + CORS_ALLOW_ORIGINS env allowlist.
  2. Todo 34: seccomp profile producer documented (script exports Docker default to infra/seccomp/default.json).
  3. Todo 41: count check now uses table names per todo 16 (users/classes/problems/contests) → [22, 1, 4, 1], no model-class names / no placeholder.
- Plan changed after round-2 approvals ⇒ lanes invalidated per lifecycle ⇒ round 3 = re-validation of the final file.

### Round 3 (rr-20260904-03) — COMPLETE: APPROVED by both (unconditional)
- momus (ses_f902396e0ffemvpWB3DORtm8wH): APPROVE unconditional — pins 1-3 VERIFIED, whole plan structurally sound (42 todos, matrix consistent, zero executor judgment calls)
- independent/oracle (ses_f9023872dffegBKpi2GOKwlbiw): APPROVE unconditional — pins 1-3 VERIFIED, "zero-interview executable for a downstream worker"
- Final-file binding: 474 lines, 42 `- [ ] N.` rows, F1-F4 rows, filled TL;DR (Effort XL / Medium risk), all at .omo/plans/pseint-judge.md
- Review REQUIRED (user request 2026-09-04) — SATISFIED: 3 rounds, all fix items resolved, final live-file approvals received.

### Round 4 (rr-20260904-04) — COMPLETE: changes_requested (both reviewers), all fixed
- Trigger: user scope change 2026-09-04 "start by doing everything on local to experiment" → plan edited (Scope guardrail, Execution strategy waves, todo 36 local mode, todo 37 local load, todo 40 local dry-run rule, todo 41 local quickstart, todo 42 local E2E, Success criteria local-first gate, TL;DR, machine TL;DR, draft D17). Every plan change invalidates both lanes ⇒ fresh round.
- momus (ses_f8e9c45efffew6qjJLsfbcDndb): CHANGES_REQUESTED — pins 1-10 verified present, 2 issues
- independent/oracle (ses_f8e9c20d9ffeIjgI8pI4KSFbeZ): CHANGES_REQUESTED — pins verified, 2 issues + 1 minor
- Fix summary (all folded into .omo/plans/pseint-judge.md, wording-only, no structural change; Effort ~Quick per oracle):
  1. [M] Todo 40 acceptance now LOCAL gate: `docker compose config --quiet` + `curl -sf http://localhost:80/healthz`/`readyz` → 200 + backup restore into scratch DB; the `https://<domain>` check explicitly marked UNAM-only verification, NOT plan acceptance.
  2. [M] Success-criteria UNAM bullet rewritten: UNAM switch-over DOCUMENTED (OPS.md/README) and NOT executed in this plan; F1-F4 verify the LOCAL stack only (fresh clone → `git clone && docker compose up -d` → seed → journeys green at localhost).
  3. [m] Todo 35 workers now `count from $REPLICAS env, default 3 — compose-managed per todo 36` (matches Execution strategy + D17 scale story).
- Plan changed after round-4 findings ⇒ lanes invalidated per lifecycle ⇒ round 5 = re-validation of the final file.

### Round 5 (rr-20260904-05) — COMPLETE: APPROVED by both (unconditional) — FINAL
- momus (ses_f8e8b4b66ffe6NVKVFgxlXsqV7): APPROVE unconditional — pins 1-3 VERIFIED, no new inconsistency (42 todos intact, matrix 36→37,40 / 40→41 / 41→42 holds, LOCAL-FIRST gate holds across Scope/waves/todos/success)
- independent/oracle (ses_f8e8b3638ffegZduIeLCyPch77): APPROVE unconditional — pins 1-3 VERIFIED, structure spot-check clean
- Final-file binding: 478 lines, 42 `- [ ] N.` rows, F1-F4 rows, filled TL;DR (Effort XL / Medium risk), all at .omo/plans/pseint-judge.md
- Review REQUIRED (user request 2026-09-04) — SATISFIED: 5 rounds; round-4 findings (2×M + 1×m) resolved; final live-file approvals received.
review:
  momus: { status: approved, launch_id: rr-20260904-05-momus, target: .omo/plans/pseint-judge.md, result: APPROVE }
  independent: { status: approved, launch_id: rr-20260904-05-oracle, target: .omo/plans/pseint-judge.md, result: APPROVE }

## Delivery state
- status: plan-approved (review complete — 5 rounds, final APPROVE by both on the local-first file)
- Handoff ready: present plan summary + review receipts to user (Phase 4 delivery format). Execution stays in a worker session via `$start-work pseint-judge` — never run by the planner.
- AGENTS.md bootstrap (init-deep, 2026-09-05): knowledge base written at `.omo/AGENTS.md` (planner file-space restriction prevented writing `./AGENTS.md` directly). WORKER MUST, in its first action before/with Todo 1: copy `.omo/AGENTS.md` verbatim to `./AGENTS.md` at the repo root and commit it in the first commit (`chore: init repo + AGENTS.md`). This is a setup step, NOT a plan change — no plan/edit touched since rr-05.