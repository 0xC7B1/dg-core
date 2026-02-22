"""Lifecycle handlers — game and session start/end, player join/leave."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import game as game_mod, session as session_mod
from app.domain.dispatcher import register_handler
from app.domain.session import timeline
from app.models.event import (
    GameEvent,
    PlayerJoinPayload,
    SessionStartPayload,
)
from app.models.result import EngineResult


def _require_session(event: GameEvent) -> str:
    """Return session_id or raise if missing."""
    if not event.session_id:
        raise ValueError("session_id is required for this event type")
    return event.session_id


async def _handle_game_start(db: AsyncSession, event: GameEvent) -> EngineResult:
    game = await game_mod.start_game(db, event.game_id)
    return EngineResult(
        success=True,
        event_type="game_start",
        data={"game_id": game.id, "status": game.status},
    )


async def _handle_game_end(db: AsyncSession, event: GameEvent) -> EngineResult:
    game = await game_mod.end_game(db, event.game_id)
    return EngineResult(
        success=True,
        event_type="game_end",
        data={"game_id": game.id, "status": game.status},
    )


async def _handle_player_join(db: AsyncSession, event: GameEvent) -> EngineResult:
    payload: PlayerJoinPayload = event.payload  # type: ignore[assignment]
    link = await game_mod.join_game(
        db, event.game_id, event.user_id, role=payload.role
    )
    return EngineResult(
        success=True,
        event_type="player_join",
        data={"game_id": event.game_id, "user_id": event.user_id, "role": link.role},
    )


async def _handle_player_leave(db: AsyncSession, event: GameEvent) -> EngineResult:
    return EngineResult(
        success=True,
        event_type="player_leave",
        data={"user_id": event.user_id},
    )


async def _handle_session_start(db: AsyncSession, event: GameEvent) -> EngineResult:
    payload: SessionStartPayload = event.payload  # type: ignore[assignment]
    s = await session_mod.start_session(
        db,
        game_id=event.game_id,
        started_by=event.user_id,
        region_id=payload.region_id,
        location_id=payload.location_id,
    )
    await timeline.append_event(
        db, session_id=s.id, game_id=event.game_id,
        event_type="session_start", user_id=event.user_id,
    )
    return EngineResult(
        success=True,
        event_type="session_start",
        data={
            "session_id": s.id,
            "game_id": event.game_id,
            "status": s.status,
            "location_id": s.location_id,
        },
    )


async def _handle_session_end(db: AsyncSession, event: GameEvent) -> EngineResult:
    sid = _require_session(event)
    s = await session_mod.end_session(db, sid)
    await timeline.append_event(
        db, session_id=sid, game_id=event.game_id,
        event_type="session_end", user_id=event.user_id,
    )
    return EngineResult(
        success=True,
        event_type="session_end",
        data={"session_id": s.id, "status": s.status},
    )


# --- Self-registration ---

register_handler("game_start", _handle_game_start)
register_handler("game_end", _handle_game_end)
register_handler("player_join", _handle_player_join)
register_handler("player_leave", _handle_player_leave)
register_handler("session_start", _handle_session_start)
register_handler("session_end", _handle_session_end)
