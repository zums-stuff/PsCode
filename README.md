# pseint-judge

Codeforces-style online judge for PseInt pseudocode. The system consists of a deterministic interpreter engine (tokenizer → AST → executor with step counter, seeded Azar, and complexity bands), a judge module that grades submissions as AC/WA/TLE/RE/CE, a FastAPI + Postgres + Redis API layer, a React teacher/student web frontend, and Docker-sandboxed execution. Everything runs locally-first via `docker compose up -d` on the developer's laptop; UNAM production deployment is a separate post-plan switch-over.
