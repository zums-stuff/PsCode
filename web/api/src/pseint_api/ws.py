"""WebSocket live-results endpoint for pseint-api (todo 19).

``WS /ws/submissions?token=<JWT>[&contest_id=<id>]`` streams per-case run
events to the run owner; teachers/admins (or the contest creator) may pass
``contest_id`` to observe ALL runs of that contest (D12).  On connect the
server replays the last 20 submitted runs of the user (M8) BEFORE live
subscription takes effect.

The worker (todo 35) pushes events by calling ``broadcast_run_event``; tests
call it directly to simulate worker events.  Broadcast is in-memory
(single-host per plan) — Redis pub/sub is a later scaling option.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import auth, config
from .deps import get_db
from .events import make_run_event
from .models import Contest, Run, TestResult, User

logger = logging.getLogger(__name__)

router = APIRouter()

# M8: replay the last 20 submitted runs on connect.
REPLAY_LIMIT = 20

# Plan QA scenario "stale token -> 4408 close code".
AUTH_CLOSE_CODE = 4408

# user_id -> set[WebSocket] (run owners).
_connections: dict[int, set[WebSocket]] = defaultdict(set)

# contest_id -> set[WebSocket] (contest observers, D12).
_contest_observers: dict[int, set[WebSocket]] = defaultdict(set)

_lock = asyncio.Lock()


async def _subscribe(user_id: int, websocket: WebSocket) -> None:
    async with _lock:
        _connections[user_id].add(websocket)


async def _unsubscribe(user_id: int, websocket: WebSocket) -> None:
    async with _lock:
        sockets = _connections.get(user_id)
        if sockets is not None:
            sockets.discard(websocket)
            if not sockets:
                _connections.pop(user_id, None)


async def _subscribe_contest(contest_id: int, websocket: WebSocket) -> None:
    async with _lock:
        _contest_observers[contest_id].add(websocket)


async def _unsubscribe_contest(contest_id: int, websocket: WebSocket) -> None:
    async with _lock:
        sockets = _contest_observers.get(contest_id)
        if sockets is not None:
            sockets.discard(websocket)
            if not sockets:
                _contest_observers.pop(contest_id, None)


async def broadcast_run_event(
    run_id: int,
    user_id: int,
    event_dict: dict,
    contest_id: int | None = None,
) -> None:
    """Push ``event_dict`` to the run owner's sockets and contest observers.

    The worker (todo 35) calls this after writing TestResult rows; tests call
    it directly to simulate worker events.  ``contest_id`` routes the event to
    contest observers (D12) — the worker passes it for contest-mode runs.
    """
    async with _lock:
        sockets = list(_connections.get(user_id, ()))
        if contest_id is not None:
            sockets += list(_contest_observers.get(contest_id, ()))
    # dict.fromkeys dedupes a socket that is both owner and observer.
    for websocket in dict.fromkeys(sockets):
        try:
            await websocket.send_json(event_dict)
        except Exception:
            logger.warning(
                "dropping dead websocket while broadcasting run %s", run_id,
                exc_info=True,
            )


def _run_event_from_row(db: Session, run: Run) -> dict:
    """Build a ``run`` event for a persisted run (replay path)."""
    results = db.scalars(
        select(TestResult)
        .where(TestResult.run_id == run.id)
        .order_by(TestResult.case_index)
    ).all()
    return make_run_event(
        run.id,
        run.status,
        per_case=[
            {
                "case_index": r.case_index,
                "verdict": r.verdict,
                "steps": r.steps,
                "wall_ms": r.wall_ms,
            }
            for r in results
        ],
    )


@router.websocket("/ws/submissions")
async def ws_submissions(
    websocket: WebSocket, db: Session = Depends(get_db)
) -> None:
    """Stream run events to the authenticated owner (and contest observers)."""
    token = websocket.query_params.get("token")
    if token is None:
        await websocket.close(code=AUTH_CLOSE_CODE)
        return
    try:
        user_id = auth.decode_token(token, config.secret_key())
    except HTTPException:
        await websocket.close(code=AUTH_CLOSE_CODE)
        return

    user = db.get(User, user_id)
    if user is None:
        await websocket.close(code=AUTH_CLOSE_CODE)
        return

    contest_id: int | None = None
    raw_contest_id = websocket.query_params.get("contest_id")
    if raw_contest_id is not None:
        try:
            contest_id = int(raw_contest_id)
        except ValueError:
            await websocket.close(code=AUTH_CLOSE_CODE)
            return
        contest = db.get(Contest, contest_id)
        if contest is None:
            await websocket.close(code=AUTH_CLOSE_CODE)
            return
        # D12: only the contest creator or a teacher/admin may observe.
        if user.role not in ("teacher", "admin") and contest.created_by != user.id:
            await websocket.close(code=AUTH_CLOSE_CODE)
            return

    await websocket.accept()

    # M8: replay the last 20 runs BEFORE live subscription takes effect.
    runs = db.scalars(
        select(Run)
        .where(Run.user_id == user_id)
        .order_by(Run.created_at.desc())
        .limit(REPLAY_LIMIT)
    ).all()
    for run in runs:
        await websocket.send_json(_run_event_from_row(db, run))

    await _subscribe(user_id, websocket)
    if contest_id is not None:
        await _subscribe_contest(contest_id, websocket)

    try:
        # Keep the connection open; client messages are ignored (server-push).
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await _unsubscribe(user_id, websocket)
        if contest_id is not None:
            await _unsubscribe_contest(contest_id, websocket)
