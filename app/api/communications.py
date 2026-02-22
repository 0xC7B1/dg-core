"""Communications API — read-only queries for communication requests."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_acting_user_id
from app.infra.db import get_db
from app.models.db_models import GamePlayer
from app.models.responses import ListPendingCommunicationsResponse, PendingCommInfo

router = APIRouter(prefix="/api/games/{game_id}/communications", tags=["communications"])


@router.get("/pending")
async def list_pending_communications(
    game_id: str,
    acting_user_id: Annotated[str, Depends(get_acting_user_id)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ListPendingCommunicationsResponse:
    from app.domain.mechanics import communication

    gp_result = await db.execute(
        select(GamePlayer).where(
            GamePlayer.game_id == game_id,
            GamePlayer.user_id == acting_user_id,
        )
    )
    gp = gp_result.scalar_one_or_none()
    if gp is None or gp.active_patient_id is None:
        raise HTTPException(status_code=400, detail="No active character")

    pending = await communication.get_pending_requests(db, game_id, gp.active_patient_id)
    return ListPendingCommunicationsResponse(
        pending_requests=[
            PendingCommInfo(
                id=r.id,
                initiator_patient_id=r.initiator_patient_id,
                initiator_patient_name=r.initiator_patient.name,
                target_patient_id=r.target_patient_id,
                target_patient_name=r.target_patient.name,
                status=r.status,
            )
            for r in pending
        ],
    )
