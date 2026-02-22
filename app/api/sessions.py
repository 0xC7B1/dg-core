"""Sessions API — session management and queries."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import permissions, session as session_mod
from app.domain.session import event_def, timeline
from app.infra.auth import get_current_user
from app.infra.db import get_db
from app.models.db_models import User
from app.models.responses import (
    AddSessionPlayerResponse,
    EventDefinitionInfo,
    ListEventDefinitionsResponse,
    RemoveSessionPlayerResponse,
    SessionInfoResponse,
    SessionStatusResponse,
    SessionTimelineResponse,
    TimelineEventInfo,
)

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


class AddSessionPlayerRequest(BaseModel):
    patient_id: str


@router.get("/{session_id}")
async def get_session_info(
    session_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SessionInfoResponse:
    try:
        info = await session_mod.get_session_info(db, session_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return SessionInfoResponse(**info)


@router.post("/{session_id}/pause")
async def pause_session(
    session_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    user_id: str | None = None,
) -> SessionStatusResponse:
    acting_user_id = user_id or current_user.id
    s = await session_mod.get_session(db, session_id)
    if s is None:
        raise HTTPException(status_code=404, detail="Session not found")
    try:
        await permissions.require_dm(db, s.game_id, acting_user_id)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    try:
        s = await session_mod.pause_session(db, session_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return SessionStatusResponse(session_id=s.id, status=s.status)


@router.post("/{session_id}/resume")
async def resume_session(
    session_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    user_id: str | None = None,
) -> SessionStatusResponse:
    acting_user_id = user_id or current_user.id
    s = await session_mod.get_session(db, session_id)
    if s is None:
        raise HTTPException(status_code=404, detail="Session not found")
    try:
        await permissions.require_dm(db, s.game_id, acting_user_id)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    try:
        s = await session_mod.resume_session(db, session_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return SessionStatusResponse(session_id=s.id, status=s.status)


@router.post("/{session_id}/players")
async def add_session_player(
    session_id: str,
    req: AddSessionPlayerRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    user_id: str | None = None,
) -> AddSessionPlayerResponse:
    acting_user_id = user_id or current_user.id
    s = await session_mod.get_session(db, session_id)
    if s is None:
        raise HTTPException(status_code=404, detail="Session not found")
    try:
        await permissions.require_dm(db, s.game_id, acting_user_id)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    try:
        sp = await session_mod.add_player_to_session(db, session_id, req.patient_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return AddSessionPlayerResponse(session_id=session_id, patient_id=sp.patient_id)


@router.delete("/{session_id}/players/{patient_id}")
async def remove_session_player(
    session_id: str,
    patient_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    user_id: str | None = None,
) -> RemoveSessionPlayerResponse:
    acting_user_id = user_id or current_user.id
    s = await session_mod.get_session(db, session_id)
    if s is None:
        raise HTTPException(status_code=404, detail="Session not found")
    try:
        await permissions.require_dm(db, s.game_id, acting_user_id)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    try:
        await session_mod.remove_player_from_session(db, session_id, patient_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return RemoveSessionPlayerResponse(removed=patient_id)


@router.get("/{session_id}/event-definitions")
async def list_event_definitions(
    session_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ListEventDefinitionsResponse:
    events = await event_def.get_active_events(db, session_id)
    return ListEventDefinitionsResponse(
        session_id=session_id,
        events=[
            EventDefinitionInfo(
                id=e.id,
                name=e.name,
                expression=e.expression,
                color_restriction=e.color_restriction,
                target_roll_total=e.target_roll_total,
            )
            for e in events
        ],
    )


@router.get("/{session_id}/timeline")
async def get_session_timeline(
    session_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = 50,
) -> SessionTimelineResponse:
    events = await timeline.get_timeline(db, session_id, limit=limit)
    return SessionTimelineResponse(
        session_id=session_id,
        events=[
            TimelineEventInfo(
                id=e.id,
                event_type=e.event_type,
                actor_id=e.actor_id,
                data=e.data_json,
                result_data=e.result_json,
                created_at=e.created_at.isoformat() if e.created_at else None,
            )
            for e in events
        ],
    )
