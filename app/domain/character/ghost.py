"""Ghost CRUD — create, get, CMYK attributes, HP/MP management."""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.character.patient import get_patient
from app.models.db_models import Ghost


async def create_ghost(
    db: AsyncSession,
    origin_patient_id: str,
    creator_user_id: str,
    game_id: str,
    name: str,
    soul_color: str,
    appearance: str | None = None,
    personality: str | None = None,
    initial_hp: int = 10,
) -> Ghost:
    # Fetch origin patient for snapshot
    origin = await get_patient(db, origin_patient_id)
    if origin is None:
        raise ValueError(f"Origin patient {origin_patient_id} not found")

    # Initialize CMYK: soul_color starts at 1, others at 0
    cmyk = {"C": 0, "M": 0, "Y": 0, "K": 0}
    cmyk[soul_color.upper()] = 1

    # Initialize archive unlock — soul_color archive unlocked at creation (SWAP reveals it)
    archive_unlock = {"C": False, "M": False, "Y": False, "K": False}
    archive_unlock[soul_color.upper()] = True

    ghost = Ghost(
        current_patient_id=None,  # companion assigned later via admin
        origin_patient_id=origin_patient_id,
        creator_user_id=creator_user_id,
        game_id=game_id,
        name=name,
        appearance=appearance,
        personality=personality,
        cmyk_json=json.dumps(cmyk),
        hp=initial_hp,
        hp_max=initial_hp,
        # Origin data snapshot
        origin_name=origin.name,
        origin_identity=origin.identity,
        origin_soul_color=origin.soul_color,
        origin_ideal_projection=origin.ideal_projection,
        origin_archives_json=origin.personality_archives_json,
        archive_unlock_json=json.dumps(archive_unlock),
        origin_name_unlocked=False,
        origin_identity_unlocked=False,
    )
    db.add(ghost)
    await db.flush()
    return ghost


async def get_ghost(db: AsyncSession, ghost_id: str) -> Ghost | None:
    result = await db.execute(select(Ghost).where(Ghost.id == ghost_id))
    return result.scalar_one_or_none()


async def get_ghosts_in_game(db: AsyncSession, game_id: str) -> list[Ghost]:
    result = await db.execute(select(Ghost).where(Ghost.game_id == game_id))
    return list(result.scalars().all())


def get_cmyk(ghost: Ghost) -> dict[str, int]:
    return json.loads(ghost.cmyk_json)


def get_color_value(ghost: Ghost, color: str) -> int:
    cmyk = get_cmyk(ghost)
    return cmyk.get(color.upper(), 0)


async def set_color_value(db: AsyncSession, ghost: Ghost, color: str, value: int) -> None:
    cmyk = get_cmyk(ghost)
    cmyk[color.upper()] = max(0, value)
    ghost.cmyk_json = json.dumps(cmyk)
    await db.flush()


def get_unlocked_origin_data(ghost: Ghost) -> dict:
    """Return origin patient data filtered by unlock state.

    soul_color and ideal_projection are always visible (shared via SWAP).
    Archives are gated by archive_unlock_json.
    Name/identity are gated by explicit unlock flags.
    """
    result: dict = {
        "origin_soul_color": ghost.origin_soul_color,
        "origin_ideal_projection": ghost.origin_ideal_projection,
    }
    if ghost.origin_name_unlocked:
        result["origin_name"] = ghost.origin_name
    if ghost.origin_identity_unlocked:
        result["origin_identity"] = ghost.origin_identity

    unlock_state = json.loads(ghost.archive_unlock_json) if ghost.archive_unlock_json else {}
    archives = json.loads(ghost.origin_archives_json) if ghost.origin_archives_json else {}
    result["origin_archives"] = {
        color: archives.get(color)
        for color, unlocked in unlock_state.items()
        if unlocked and archives.get(color) is not None
    }
    return result


async def change_hp(db: AsyncSession, ghost: Ghost, delta: int) -> tuple[int, bool]:
    """Change ghost HP. Returns (new_hp, collapsed)."""
    ghost.hp = max(0, min(ghost.hp + delta, ghost.hp_max))
    collapsed = ghost.hp <= 0
    await db.flush()
    return ghost.hp, collapsed


async def change_mp(db: AsyncSession, ghost: Ghost, delta: int) -> tuple[int, bool]:
    """Change ghost MP. Returns (new_mp, depleted)."""
    ghost.mp = max(0, min(ghost.mp + delta, ghost.mp_max))
    depleted = ghost.mp <= 0
    await db.flush()
    return ghost.mp, depleted


async def set_ghost_attribute(
    db: AsyncSession, ghost: Ghost, attribute: str, value: int
) -> None:
    """Set a ghost attribute (hp, mp, hp_max, mp_max, or cmyk.X).

    For CMYK: use attribute="cmyk.C", "cmyk.M", etc.
    """
    if attribute == "hp":
        ghost.hp = max(0, value)
    elif attribute == "mp":
        ghost.mp = max(0, value)
    elif attribute == "hp_max":
        ghost.hp_max = max(1, value)
    elif attribute == "mp_max":
        ghost.mp_max = max(1, value)
    elif attribute.startswith("cmyk."):
        color = attribute[5:].upper()
        if color not in ("C", "M", "Y", "K"):
            raise ValueError(f"Invalid CMYK color: {color}")
        await set_color_value(db, ghost, color, value)
        return
    else:
        raise ValueError(f"Unknown attribute: {attribute}")
    await db.flush()
