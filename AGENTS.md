# PROJECT KNOWLEDGE BASE — pseint-judge

**Generated:** 2026-09-05
**Commit:** none — NOT a git repo yet (`git init` = Todo 1 of the plan)
**Branch:** none

## OVERVIEW
Codeforces-style online judge for PseInt pseudocode: our own deterministic interpreter engine (step counter grades correctness + complexity bands OK/ALTA/EXCESIVA) + judge (AC/WA/TLE/RE/CE) + FastAPI/Postgres/Redis API + React teacher/student web + Docker sandbox + CF/IOI contests + minimal text-similarity plagiarism report. **LOCAL-FIRST**: everything is built and verified on the developer's laptop (`docker compose up -d`, DOMAIN unset → `http://localhost`); UNAM production wiring is documented as a post-plan switch-over, never executed during the plan.

## THE PLAN IS THE BRAIN — READ IT FIRST
- **`.omo/plans/pseint-judge.md`** — the authoritative, DECISION-COMPLETE, REVIEW-APPROVED plan: 42 todos across 7 waves + dependency matrix + final verification F1–F4 + success criteria. **Any agent doing anything on this project reads this file first.**
- **`.omo/drafts/pseint-judge.md`** — decision ledger (D1–D17) + Metis resolutions (M1–M13) + review registry (5 rounds). Read when a "why" is needed.
- **`.omo/evidence/`** — created during execution; per-task evidence receipts and final F1–F4 receipts land here.
- `.omo/run-continuation/*.json` — agent session traces (noise; not project content, ignore).

## CURRENT STATE
- Working directory is **empty except `.omo/`** — zero code exists yet. `git init`, corpus, engine, all of it is Todo 1+ of the plan.
- Plan status: **APPROVED** by dual review (5 rounds rr-01…rr-05; rounds 3 and 5 unconditional APPROVE). Delivery state: `plan-approved` in the draft.
- **Plan mode is STICKY**: planners/reviewers never implement, never spawn agents that edit product code. Execution happens only in a worker session the USER starts via `/start-work pseint-judge` (optionally `--worktree`). Do not start work on your own; the plan file is the deliverable.

## TARGET STRUCTURE (from plan — what the worker will build)
```
{root}/
├── engine/            # Python interpreter: tokenizer → AST → executor (step counter, Azar seeded=0, FechaActual/HoraActual stubs, Esperar=1 step)
├── judge/             # verdict logic: correctness (test cases) + complexity (normative FORMULA coefficients, todo 2 §k)
├── api/               # pseint_api: FastAPI; run/validate/assignment/contest/scoreboard/anticheat endpoints; rate limits 10runs/30subs/60req per min
├── web/frontend/      # React+TS+Vite, CodeMirror 6 PseInt mode; teacher + student + (no exam) modes
├── e2e/               # Playwright journeys (6; run against local compose stack, real WS, no stubs)
├── infra/             # docker-compose (postgres/redis/api/worker:replicas $REPLICAS default 3/caddy), worker RQ, seccomp profile
├── scripts/           # seed.py (→ [22,1,4,1] count check), loadtest.py (200-burst p95<60s), backup.sh
└── .omo/evidence/     # execution receipts
```

## CONVENTIONS (binding — from the plan)
- **TDD lock**: any change to the PseInt dialect spec REQUIRES a golden corpus case first (≥25 cases); engine corpus must stay green.
- **FORMULA coefficients are NORMATIVE** (todo 2 §k): O(1)=50 · O(log n)=50·log2(n+2) · O(n)=20n+50 · O(n log n)=20n·log2(n+2)+50 · O(n²)=5n²+50 · O(n³)=2n³+50 · O(2ⁿ)=2^(n+4) · unclassified ⇒ step_budget REQUIRED.
- **One container per submission**, all its test cases run inside it; M2 lazy rules (CE short-circuit, CF lazy-stop) enforced in-container.
- **Determinism**: Azar seeded per run (default 0); FechaActual/HoraActual fixed stubs; Esperar = 1 step; wall-clock + step budgets both enforced.
- **LOCAL-FIRST rule**: every acceptance command runs on the developer laptop over HTTP; `curl -I https://<domain>/…` checks are UNAM-only verification documented in OPS.md, NOT plan acceptance. No acceptance may require a domain/TLS/external infra.
- **Scale**: stateless RQ workers + Redis; worker count from `$REPLICAS` (default 3, compose-managed). Single-host only — multi-node is OUT.
- **Commit strategy**: Conventional Commits with scope, one commit per todo, tree always green, no WIP commits; tags `engine-v1`/`judge-v1`/`api-v1`/`deploy-v1` at wave gates.
- **Admin**: deployment via Docker sandbox only; API container NEVER gets the Docker socket.
- **Secrets**: never committed; `.env` gitignored; SECRET_KEY<32 chars refuses boot.

## ANTI-PATTERNS (THIS PROJECT — explicitly forbidden)
- No multi-tenant/public SaaS; no multi-node/shared-nothing deployment.
- NO nsjail — Docker sandbox only.
- No automatic plagiarism penalties (report-only; threshold 0.85, same-team excluded).
- No proctoring, no auto-penalty for leaving the page, no email service.
- No stubbing of WS in E2E — real end-to-end.
- No secrets in commits; no `decide:`/unresolved judgment calls — the plan must stay zero-interview-executable.
- Planner/reviewer agents must never edit product code or spawn implementers.

## COMMANDS (future worker's daily loop — targets from the plan)
```bash
docker compose up -d                                  # full local stack, DOMAIN unset → http://localhost
python scripts/seed.py                                # seed; then count check → [22, 1, 4, 1]
python scripts/loadtest.py                            # 200-burst; p95 < 60s, zero lost runs
npx playwright test e2e                               # 6 journeys, local stack, seeded data
docker compose config --quiet                         # todo 40 local gate
curl -sf localhost:80/healthz && curl -sf localhost:80/readyz
```

## NOTES / GOTCHAS
- Do NOT spawn background `librarian` subagents for research — they fail with `ProviderModelNotFoundError` (opencode/qwen3.6-plus-free). Research directly (web/context7/codegraph).
- The plan's Acceptance criteria lines are `(agent-executable)` — asserting those is the definition of done per todo; evidence goes to `.omo/evidence/task-NN-pseint-judge.txt`.
- Success-criteria gate for declaring completion: all F1–F4 APPROVE with receipts in `.omo/evidence/` — then the user is asked, never assumed.
- **BOOTSTRAP (worker, first action)**: promote this file to the repo root as `./AGENTS.md` (copy verbatim) so every agent and subagent gets this context from the standard root location; commit it in the first commit (Todo 1, `chore: init repo + AGENTS.md`).