"""Timeline API — game-level timeline queries."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.session import timeline
from app.infra.auth import get_current_user
from app.infra.db import get_db
from app.models.db_models import User

router = APIRouter(prefix="/api/games/{game_id}", tags=["timeline"])


@router.get("/timeline")
async def get_game_timeline(
    game_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = 50,
) -> dict:
    events = await timeline.get_game_timeline(db, game_id, limit=limit)
    return {
        "game_id": game_id,
        "events": [
            {
                "id": e.id,
                "session_id": e.session_id,
                "event_type": e.event_type,
                "actor_id": e.actor_id,
                "data": e.data_json,
                "result_data": e.result_data_json,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in events
        ],
    }
