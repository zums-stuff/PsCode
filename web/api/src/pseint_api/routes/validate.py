"""Source validation endpoint for pseint-api (todo 18).

POST /api/validate is a thin wrapper over the engine's parser (todo 7
validate contract): returns ``{ok, errors: [{code, message, line, col}]}``.
Consumed by the frontend inline-error flow (todo 29) and the problem-admin
sample-run CE check (todo 22).  Source cap 64KB -> 413.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..deps import get_current_user
from ..models import User

router = APIRouter(prefix="/api")

MAX_SOURCE_BYTES = 65536  # 64KB (M13 / todo 15 constants)


class ValidateRequest(BaseModel):
    source: str = Field(min_length=1)


@router.post("/validate")
def validate_source(
    req: ValidateRequest,
    user: User = Depends(get_current_user),
):
    if len(req.source.encode("utf-8")) > MAX_SOURCE_BYTES:
        raise HTTPException(
            status_code=413, detail="Source exceeds the 64KB limit"
        )
    from pseint_engine.lexer import LexError
    from pseint_engine.parser import ParseError, parse

    try:
        parse(req.source)
    except (LexError, ParseError) as e:
        return {
            "ok": False,
            "errors": [
                {
                    "code": "ERR_SYNTAX",
                    "message": e.message,
                    "line": e.line,
                    "col": e.col,
                }
            ],
        }
    return {"ok": True, "errors": []}
