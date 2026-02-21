"""dg-core — FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager
from importlib.metadata import version, PackageNotFoundError

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from app.admin import setup_admin
from app.api import auth
from app.api import (
    characters,
    communications,
    dice,
    events,
    games,
    items,
    rag,
    regions,
    sessions,
    ws,
)
from app.infra.db import async_session_factory
from app.infra.init_admin import ensure_default_admin

logger = logging.getLogger("dg-core")

try:
    __version__ = version("dg-core")
except PackageNotFoundError:
    __version__ = "0.0.0-dev"


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    # Schema managed by Alembic — run `alembic upgrade head` before starting.
    try:
        await ensure_default_admin(async_session_factory)
    except Exception:
        logger.warning(
            "Could not create default admin user. "
            "Ensure Alembic migrations have been applied (`alembic upgrade head`).",
            exc_info=True,
        )
    yield


app = FastAPI(
    title="dg-core",
    description="Digital Ghost World Engine — TRPG game engine service",
    version=__version__,
    lifespan=lifespan,
)


def custom_openapi() -> dict:  # type: ignore[no-untyped-def]
    """Add security schemes to OpenAPI schema."""
    if app.openapi_schema:
        return app.openapi_schema
    
    openapi_schema = get_openapi(
        title="dg-core",
        version=__version__,
        description="Digital Ghost World Engine — TRPG game engine service",
        routes=app.routes,
    )
    
    # Define security schemes (preserve any existing ones)
    if "components" not in openapi_schema:
        openapi_schema["components"] = {}
    
    if "securitySchemes" not in openapi_schema["components"]:
        openapi_schema["components"]["securitySchemes"] = {}
    
    openapi_schema["components"]["securitySchemes"].update({
        "bearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "JWT access token from /api/auth/register or login endpoints",
        },
        "apiKey": {
            "type": "apiKey",
            "in": "header",
            "name": "X-API-Key",
            "description": "API key for bot clients (64-char hex)",
        },
    })
    
    # Add security requirements to authenticated endpoints.
    # Endpoints using get_current_user() parse headers manually, so FastAPI
    # can't auto-detect them as secured — we annotate them here.
    # Public paths (/health, /api/auth/register, /api/auth/login/*) are excluded.
    _public_paths = {
        "/health",
        "/api/auth/register",
        "/api/auth/login/password",
        "/api/auth/login/api-key",
    }
    for path, path_item in openapi_schema.get("paths", {}).items():
        if path in _public_paths:
            continue
        if path.startswith("/api/"):
            for method, operation in path_item.items():
                if isinstance(operation, dict) and "security" not in operation:
                    operation["security"] = [
                        {"bearerAuth": []},
                        {"apiKey": []},
                    ]
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi

app.include_router(auth.router)

# Resource-based routers
app.include_router(events.router)
app.include_router(games.router)
app.include_router(characters.router)
app.include_router(communications.router)
app.include_router(sessions.router)
app.include_router(regions.router)
app.include_router(items.router)
app.include_router(dice.router)
app.include_router(ws.router)
app.include_router(rag.router)

setup_admin(app)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "engine": "dg-core", "version": __version__}
