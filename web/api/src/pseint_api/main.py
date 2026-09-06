"""FastAPI application factory for pseint-api (todo 17)."""

from __future__ import annotations

from fastapi import FastAPI

from .routes import auth


def create_app() -> FastAPI:
    app = FastAPI(title="pseint-api")
    app.include_router(auth.router)
    return app
