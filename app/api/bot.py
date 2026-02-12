"""Bot API — game event submission and state queries."""

from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import game as game_mod, session as session_mod, timeline
from app.domain.dispatcher import dispatch
from app.infra.db import get_db
from app.models.event import GameEvent

router = APIRouter(prefix="/api/bot", tags=["bot"])


@router.post("/events")
async def submit_event(
    event: GameEvent,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Submit a game event to the engine dispatcher."""
    result = await dispatch(db, event)
    return result.model_dump()


@router.get("/games/{game_id}")
async def get_game(
    game_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    game = await game_mod.get_game(db, game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    players = await game_mod.get_game_players(db, game_id)
    return {
        "game_id": game.id,
        "name": game.name,
        "status": game.status,
        "config": json.loads(game.config_json) if game.config_json else None,
        "players": [
            {"player_id": p.player_id, "role": p.role}
            for p in players
        ],
    }


@router.get("/sessions/{session_id}/timeline")
async def get_session_timeline(
    session_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = 50,
    offset: int = 0,
) -> dict:
    session = await session_mod.get_session(db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    events = await timeline.get_timeline(db, session_id, limit=limit, offset=offset)
    return {
        "session_id": session_id,
        "events": [
            {
                "id": e.id,
                "seq": e.seq,
                "event_type": e.event_type,
                "actor_id": e.actor_id,
                "data": json.loads(e.data_json) if e.data_json else None,
                "result": json.loads(e.result_json) if e.result_json else None,
                "narrative": e.narrative,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in events
        ],
    }


@router.get("/games/{game_id}/timeline")
async def get_game_timeline(
    game_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = 100,
    offset: int = 0,
) -> dict:
    events = await timeline.get_game_timeline(db, game_id, limit=limit, offset=offset)
    return {
        "game_id": game_id,
        "events": [
            {
                "id": e.id,
                "seq": e.seq,
                "event_type": e.event_type,
                "actor_id": e.actor_id,
                "data": json.loads(e.data_json) if e.data_json else None,
                "result": json.loads(e.result_json) if e.result_json else None,
                "narrative": e.narrative,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in events
        ],
    }
