"""Timeline — append and query event records, player state snapshots."""

from __future__ import annotations

import json
import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.db_models import (
    GamePlayer,
    Ghost,
    Patient,
    TimelineEvent,
    TimelinePlayerSnapshot,
    User,
)
from app.modules.memory.short_term import short_term_memory

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Snapshot helpers
# ---------------------------------------------------------------------------


def _serialize_buffs(buffs: list) -> str | None:
    """Serialize active buffs for snapshot. Sorted by name for consistency."""
    if not buffs:
        return None
    entries = sorted(
        [
            {
                "name": b.name,
                "expression": b.expression,
                "buff_type": b.buff_type,
                "remaining_rounds": b.remaining_rounds,
            }
            for b in buffs
        ],
        key=lambda x: x["name"],
    )
    return json.dumps(entries, ensure_ascii=False, separators=(",", ":"))


async def _collect_player_state(
    db: AsyncSession,
    game_id: str,
    user_id: str,
    patient: Patient | None = None,
    ghost: Ghost | None = None,
) -> dict:
    """Gather all player state fields needed for a snapshot.

    If patient/ghost are provided (common in handlers), uses them directly.
    Otherwise resolves from user_id + game_id.
    """
    # 1. User
    user_result = await db.execute(select(User).where(User.id == user_id))
    user_obj = user_result.scalar_one_or_none()

    # 2. GamePlayer
    gp_result = await db.execute(
        select(GamePlayer).where(
            GamePlayer.game_id == game_id,
            GamePlayer.user_id == user_id,
        )
    )
    gp = gp_result.scalar_one_or_none()
    role = gp.role if gp else "PL"

    # 3. Resolve patient
    if patient is None and gp and gp.active_patient_id:
        p_result = await db.execute(
            select(Patient).where(Patient.id == gp.active_patient_id)
        )
        patient = p_result.scalar_one_or_none()

    # 4. Resolve ghost — from patient or ghost.current_patient_id
    if ghost is not None and patient is None and ghost.current_patient_id:
        p_result = await db.execute(
            select(Patient).where(Patient.id == ghost.current_patient_id)
        )
        patient = p_result.scalar_one_or_none()
    elif ghost is None and patient is not None:
        g_result = await db.execute(
            select(Ghost).where(Ghost.current_patient_id == patient.id)
        )
        ghost = g_result.scalar_one_or_none()

    # 5. Buffs
    buffs_json = None
    if ghost is not None:
        from app.domain.character.buff import get_buffs

        buffs = await get_buffs(db, ghost.id)
        buffs_json = _serialize_buffs(buffs)

    return {
        "game_id": game_id,
        "user_id": user_id,
        "username": user_obj.username if user_obj else "unknown",
        "role": role,
        "patient_id": patient.id if patient else None,
        "patient_name": patient.name if patient else None,
        "soul_color": patient.soul_color if patient else None,
        "ghost_id": ghost.id if ghost else None,
        "ghost_name": ghost.name if ghost else None,
        "hp": ghost.hp if ghost else None,
        "hp_max": ghost.hp_max if ghost else None,
        "mp": ghost.mp if ghost else None,
        "mp_max": ghost.mp_max if ghost else None,
        "cmyk_json": ghost.cmyk_json if ghost else None,
        "region_id": patient.current_region_id if patient else None,
        "location_id": patient.current_location_id if patient else None,
        "buffs_json": buffs_json,
    }


async def create_player_snapshot(
    db: AsyncSession,
    game_id: str,
    user_id: str,
    patient: Patient | None = None,
    ghost: Ghost | None = None,
) -> TimelinePlayerSnapshot:
    """Create a new player state snapshot and set it as current on GamePlayer.

    Called explicitly by state-changing handlers after they modify state.
    """
    state = await _collect_player_state(db, game_id, user_id, patient, ghost)
    snapshot = TimelinePlayerSnapshot(**state)
    db.add(snapshot)
    await db.flush()

    # Update GamePlayer.current_snapshot_id
    gp_result = await db.execute(
        select(GamePlayer).where(
            GamePlayer.game_id == game_id,
            GamePlayer.user_id == user_id,
        )
    )
    gp = gp_result.scalar_one_or_none()
    if gp is not None:
        gp.current_snapshot_id = snapshot.id

    return snapshot


# ---------------------------------------------------------------------------
# Timeline event recording
# ---------------------------------------------------------------------------


async def _next_seq(db: AsyncSession, session_id: str) -> int:
    result = await db.execute(
        select(func.coalesce(func.max(TimelineEvent.seq), 0)).where(
            TimelineEvent.session_id == session_id
        )
    )
    return result.scalar_one() + 1


async def append_event(
    db: AsyncSession,
    session_id: str,
    game_id: str,
    event_type: str,
    user_id: str | None = None,
    data: dict | None = None,
    result_data: dict | None = None,
    narrative: str | None = None,
) -> TimelineEvent:
    """Record a timeline event. Auto-reads current snapshot from GamePlayer.

    If the player has no snapshot yet (first event), creates an initial one.
    """
    seq = await _next_seq(db, session_id)

    player_snapshot_id = None
    if user_id is not None:
        gp_result = await db.execute(
            select(GamePlayer).where(
                GamePlayer.game_id == game_id,
                GamePlayer.user_id == user_id,
            )
        )
        gp = gp_result.scalar_one_or_none()
        if gp is not None:
            if gp.current_snapshot_id is None:
                # Lazy init — first event from this player
                snap = await create_player_snapshot(db, game_id, user_id)
                player_snapshot_id = snap.id
            else:
                player_snapshot_id = gp.current_snapshot_id

    event = TimelineEvent(
        session_id=session_id,
        game_id=game_id,
        seq=seq,
        event_type=event_type,
        actor_id=user_id,  # deprecated, kept for backward compat
        player_snapshot_id=player_snapshot_id,
        data_json=json.dumps(data) if data else None,
        result_json=json.dumps(result_data) if result_data else None,
        narrative=narrative,
    )
    db.add(event)
    await db.flush()

    # Also push to short-term memory
    summary = f"{event_type}"
    if narrative:
        summary += f" — {narrative[:80]}"
    short_term_memory.add(session_id, seq, event_type, summary)

    return event


# ---------------------------------------------------------------------------
# Timeline queries
# ---------------------------------------------------------------------------


async def get_timeline(
    db: AsyncSession,
    session_id: str,
    limit: int = 50,
    offset: int = 0,
) -> list[TimelineEvent]:
    result = await db.execute(
        select(TimelineEvent)
        .where(TimelineEvent.session_id == session_id)
        .options(joinedload(TimelineEvent.player_snapshot))
        .order_by(TimelineEvent.seq)
        .limit(limit)
        .offset(offset)
    )
    return list(result.unique().scalars().all())


async def get_game_timeline(
    db: AsyncSession,
    game_id: str,
    limit: int = 100,
    offset: int = 0,
) -> list[TimelineEvent]:
    """Get timeline events across all sessions in a game."""
    result = await db.execute(
        select(TimelineEvent)
        .where(TimelineEvent.game_id == game_id)
        .options(joinedload(TimelineEvent.player_snapshot))
        .order_by(TimelineEvent.created_at)
        .limit(limit)
        .offset(offset)
    )
    return list(result.unique().scalars().all())
