"""Resolution helpers — resolve patient and ghost for game events."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db_models import GamePlayer, Ghost, Patient, Session
from app.models.event import GameEvent


async def resolve_patient_for_event(
    db: AsyncSession, event: GameEvent
) -> Patient | None:
    """Hybrid character resolution: session region → patient, or fallback to active_patient_id."""
    if event.session_id:
        # Resolve by session region
        session_result = await db.execute(
            select(Session).where(Session.id == event.session_id)
        )
        session = session_result.scalar_one_or_none()
        if session is not None and session.region_id is not None:
            patient_result = await db.execute(
                select(Patient).where(
                    Patient.user_id == event.user_id,
                    Patient.game_id == event.game_id,
                    Patient.current_region_id == session.region_id,
                )
            )
            return patient_result.scalar_one_or_none()

    # Fallback: use active_patient_id from GamePlayer
    gp_result = await db.execute(
        select(GamePlayer).where(
            GamePlayer.game_id == event.game_id,
            GamePlayer.user_id == event.user_id,
        )
    )
    gp = gp_result.scalar_one_or_none()
    if gp is None or gp.active_patient_id is None:
        return None

    patient_result = await db.execute(
        select(Patient).where(Patient.id == gp.active_patient_id)
    )
    return patient_result.scalar_one_or_none()


async def find_player_ghost(
    db: AsyncSession,
    game_id: str | None = None,
    user_id: str | None = None,
    patient_id: str | None = None,
) -> Ghost | None:
    """Find the ghost for a patient. Accepts direct patient_id or resolves via GamePlayer."""
    if patient_id is None:
        if game_id is None or user_id is None:
            return None
        gp_result = await db.execute(
            select(GamePlayer).where(
                GamePlayer.game_id == game_id,
                GamePlayer.user_id == user_id,
            )
        )
        gp = gp_result.scalar_one_or_none()
        if gp is None or gp.active_patient_id is None:
            return None
        patient_id = gp.active_patient_id

    result = await db.execute(
        select(Ghost).where(Ghost.current_patient_id == patient_id)
    )
    return result.scalar_one_or_none()
