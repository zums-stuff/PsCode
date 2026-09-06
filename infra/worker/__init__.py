"""Worker pool (RQ) for pseint-judge (todo 35).

The RQ workers in this package execute ``pseint_judge.runner.judge_submission``
for queued runs, persist per-case results, broadcast WebSocket events, and
trigger scoreboard recompute and anticheat batches.

See ``worker.py`` for the full docstring (M2 lazy rules, M12 scoreboard
recompute, one-container-per-submission goal).
"""

from __future__ import annotations
