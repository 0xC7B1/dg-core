"""Events API — unified game event submission endpoint."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.dispatcher import dispatch
from app.infra.auth import get_current_user
from app.infra.db import get_db
from app.infra.ws_manager import ws_manager
from app.models.db_models import User
from app.models.event import GameEvent

router = APIRouter(prefix="/api", tags=["events"])


@router.post("/events")
async def submit_event(
    event: GameEvent,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Submit a game event to the engine dispatcher.

    All game-affecting actions (gameplay + DM management) go through this endpoint.
    The dispatcher routes to the appropriate handler, records timeline, and
    returns an EngineResult. Results are broadcast to WebSocket clients.
    """
    result = await dispatch(db, event)
    await ws_manager.broadcast_to_game(event.game_id, result)
    return result.model_dump()
