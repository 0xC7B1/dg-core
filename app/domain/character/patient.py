"""Patient CRUD — create, get, list, delete patients."""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db_models import GamePlayer, Ghost, Patient

_DEFAULT_ARCHIVE_UNLOCK = '{"C":false,"M":false,"Y":false,"K":false}'


async def create_patient(
    db: AsyncSession,
    user_id: str,
    game_id: str,
    name: str,
    soul_color: str,
    gender: str | None = None,
    age: int | None = None,
    height: str | None = None,
    weight: str | None = None,
    identity: str | None = None,
    appearance: str | None = None,
    statement: str | None = None,
    portrait_url: str | None = None,
    personality_archives: dict | None = None,
    ideal_projection: str | None = None,
) -> Patient:
    patient = Patient(
        user_id=user_id,
        game_id=game_id,
        name=name,
        soul_color=soul_color.upper(),
        gender=gender,
        age=age,
        height=height,
        weight=weight,
        identity=identity,
        appearance=appearance,
        statement=statement,
        portrait_url=portrait_url,
        personality_archives_json=json.dumps(personality_archives) if personality_archives else None,
        ideal_projection=ideal_projection,
    )
    db.add(patient)
    await db.flush()

    # Auto-activate if this is the player's first patient in the game
    gp_result = await db.execute(
        select(GamePlayer).where(
            GamePlayer.game_id == game_id,
            GamePlayer.user_id == user_id,
        )
    )
    gp = gp_result.scalar_one_or_none()
    if gp is not None and gp.active_patient_id is None:
        gp.active_patient_id = patient.id
        await db.flush()

    return patient


async def get_patient(db: AsyncSession, patient_id: str) -> Patient | None:
    result = await db.execute(select(Patient).where(Patient.id == patient_id))
    return result.scalar_one_or_none()


def generate_swap_file(patient: Patient) -> dict:
    """Generate the SWAP file for ghost creation: soul_color + ideal_projection + one archive entry."""
    archives = json.loads(patient.personality_archives_json) if patient.personality_archives_json else {}
    # SWAP reveals only the soul_color archive
    revealed_archive = {}
    color_key = patient.soul_color.upper()
    if color_key in archives:
        revealed_archive[color_key] = archives[color_key]

    return {
        "type": "SWAP",
        "soul_color": patient.soul_color,
        "ideal_projection": patient.ideal_projection,
        "revealed_archive": revealed_archive,
    }


async def get_patients_in_game(
    db: AsyncSession, game_id: str, user_id: str
) -> list[Patient]:
    """List all of a user's patients in a game."""
    result = await db.execute(
        select(Patient).where(
            Patient.game_id == game_id,
            Patient.user_id == user_id,
        )
    )
    return list(result.scalars().all())


async def get_all_patients_in_game(
    db: AsyncSession, game_id: str, name: str | None = None,
) -> list[Patient]:
    """List all patients in a game (no user filter), optionally filtered by name."""
    stmt = select(Patient).where(Patient.game_id == game_id)
    if name is not None:
        stmt = stmt.where(Patient.name.ilike(f"%{name}%"))
    stmt = stmt.order_by(Patient.name)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def delete_patient(db: AsyncSession, patient_id: str) -> None:
    """Delete a patient. Validates no ghost is currently attached."""
    patient = await get_patient(db, patient_id)
    if patient is None:
        raise ValueError(f"Patient {patient_id} not found")

    # Check no ghost currently paired with this patient
    ghost_result = await db.execute(
        select(Ghost).where(Ghost.current_patient_id == patient_id)
    )
    if ghost_result.scalar_one_or_none() is not None:
        raise ValueError("Cannot delete patient: a ghost is currently paired with them")

    # Clear active_patient_id references
    gp_result = await db.execute(
        select(GamePlayer).where(GamePlayer.active_patient_id == patient_id)
    )
    for gp in gp_result.scalars().all():
        gp.active_patient_id = None

    await db.delete(patient)
    await db.flush()
