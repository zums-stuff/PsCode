# infra/seccomp/

This directory holds the Docker seccomp profile that `scripts/run_sandboxed.py`
pins with `--security-opt seccomp=infra/seccomp/default.json` (todo 34).

`default.json` is **not** committed — it is exported by the script itself:

    python scripts/run_sandboxed.py --export-seccomp

which runs a one-shot `docker:dind` container and pipes
`/etc/docker/seccomp/default.json` to disk. The producer is documented in
OPS.md (M9), the file is the pinned output of that export. Re-run whenever
the host Docker engine is upgraded so the profile matches the new runtime
defaults.
