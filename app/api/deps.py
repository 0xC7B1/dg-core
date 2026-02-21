"""Shared API dependencies — acting user resolution, admin checks."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException

from app.infra.auth import get_current_user
from app.models.db_models import User


async def get_acting_user_id(
    current_user: Annotated[User, Depends(get_current_user)],
    user_id: str | None = None,
) -> str:
    """Bot proxy mode: use provided user_id, else use authenticated user's ID."""
    return user_id or current_user.id


async def require_admin_dep(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Admin role check for system-level operations."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")
    return current_user
