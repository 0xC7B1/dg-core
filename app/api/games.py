"""Games API — game CRUD, player management, and queries."""

from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import game as game_mod
from app.domain.session import timeline
from app.infra.auth import get_current_user
from app.infra.db import get_db
from app.models.db_models import User
from app.models.responses import (
    AddPlayerResponse,
    CreateGameResponse,
    GameDetailResponse,
    GamePlayerInfo,
    GameTimelineResponse,
    TimelineEventInfo,
)

router = APIRouter(prefix="/api/games", tags=["games"])


# --- Request schemas ---

class CreateGameRequest(BaseModel):
    name: str
    config: dict | None = None


class UpdateGameRequest(BaseModel):
    name: str | None = None
    status: str | None = None
    config: dict | None = None


class AddPlayerRequest(BaseModel):
    user_id: str
    role: str = "PL"


class UpdatePlayerRoleRequest(BaseModel):
    role: str


# --- Endpoints ---

@router.post("")
async def create_game(
    req: CreateGameRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CreateGameResponse:
    """Create a new game. Creator automatically becomes DM."""
    game = await game_mod.create_game(db, req.name, current_user.id, req.config)
    return CreateGameResponse(game_id=game.id, name=game.name, status=game.status)


@router.get("/{game_id}")
async def get_game(
    game_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> GameDetailResponse:
    """Get game details including player list."""
    game = await game_mod.get_game(db, game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    players = await game_mod.get_game_players(db, game_id)
    return GameDetailResponse(
        game_id=game.id,
        name=game.name,
        status=game.status,
        config=json.loads(game.config_json) if game.config_json else None,
        players=[
            GamePlayerInfo(
                user_id=p.user_id,
                username=p.user.username if p.user else None,
                role=p.role,
                active_patient_id=p.active_patient_id,
                active_patient_name=p.active_patient.name if p.active_patient else None,
            )
            for p in players
        ],
    )


@router.put("/{game_id}")
async def update_game(
    game_id: str,
    req: UpdateGameRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CreateGameResponse:
    """Update game properties. DM only."""
    game = await game_mod.get_game(db, game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    if req.name is not None:
        game.name = req.name
    if req.status is not None:
        game.status = req.status
    if req.config is not None:
        game.config_json = json.dumps(req.config)
    await db.flush()
    return CreateGameResponse(game_id=game.id, name=game.name, status=game.status)


@router.post("/{game_id}/players")
async def add_player_to_game(
    game_id: str,
    req: AddPlayerRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AddPlayerResponse:
    """Add a player to a game. DM only."""
    link = await game_mod.join_game(db, game_id, req.user_id, req.role)
    return AddPlayerResponse(game_id=game_id, user_id=req.user_id, role=link.role)


@router.put("/{game_id}/players/{user_id}/role")
async def update_player_role(
    game_id: str,
    user_id: str,
    req: UpdatePlayerRoleRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AddPlayerResponse:
    """Update a player's role. DM only."""
    link = await game_mod.update_player_role(db, game_id, user_id, req.role)
    return AddPlayerResponse(game_id=game_id, user_id=user_id, role=link.role)


@router.get("/{game_id}/timeline")
async def get_game_timeline(
    game_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = 50,
) -> GameTimelineResponse:
    """Get game-wide timeline across all sessions."""
    events = await timeline.get_game_timeline(db, game_id, limit=limit)
    return GameTimelineResponse(
        game_id=game_id,
        events=[
            TimelineEventInfo(
                id=e.id,
                session_id=e.session_id,
                event_type=e.event_type,
                actor_id=e.actor_id,
                data=e.data_json,
                result_data=e.result_json,
                created_at=e.created_at.isoformat() if e.created_at else None,
            )
            for e in events
        ],
    )
