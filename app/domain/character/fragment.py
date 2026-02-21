"""ColorFragment — apply fragments and unlock origin archives."""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.character.ghost import get_cmyk, get_ghost
from app.models.db_models import ColorFragment, Ghost


async def apply_color_fragment(
    db: AsyncSession, ghost: Ghost, color: str, value: int = 1
) -> dict:
    """Apply a color fragment: increment the CMYK value and record the fragment.

    Returns dict with updated cmyk and fragment_id (usable as archive unlock key).
    """
    cmyk = get_cmyk(ghost)
    old_val = cmyk.get(color.upper(), 0)
    cmyk[color.upper()] = old_val + value
    ghost.cmyk_json = json.dumps(cmyk)

    fragment = ColorFragment(
        game_id=ghost.game_id,
        holder_ghost_id=ghost.id,
        color=color.upper(),
        value=float(value),
    )
    db.add(fragment)
    await db.flush()
    return {"cmyk": cmyk, "fragment_id": fragment.id}


async def unlock_archive(db: AsyncSession, fragment_id: str, ghost_id: str) -> dict:
    """Redeem a color fragment to unlock the corresponding origin archive.

    Returns dict with the unlocked color and archive content.
    """
    from datetime import datetime, timezone

    result = await db.execute(
        select(ColorFragment).where(ColorFragment.id == fragment_id)
    )
    fragment = result.scalar_one_or_none()
    if fragment is None:
        raise ValueError(f"Fragment {fragment_id} not found")
    if fragment.holder_ghost_id != ghost_id:
        raise ValueError("Fragment does not belong to this ghost")
    if fragment.redeemed:
        raise ValueError("Fragment has already been redeemed")

    ghost = await get_ghost(db, ghost_id)
    if ghost is None:
        raise ValueError(f"Ghost {ghost_id} not found")

    color = fragment.color.upper()
    unlock_state = json.loads(ghost.archive_unlock_json)
    if unlock_state.get(color, False):
        raise ValueError(f"Archive for color {color} is already unlocked")

    # Mark fragment as redeemed
    fragment.redeemed = True
    fragment.redeemed_at = datetime.now(timezone.utc)

    # Unlock the archive
    unlock_state[color] = True
    ghost.archive_unlock_json = json.dumps(unlock_state)
    await db.flush()

    # Return the unlocked archive content
    archives = json.loads(ghost.origin_archives_json) if ghost.origin_archives_json else {}
    return {
        "color": color,
        "archive_content": archives.get(color),
        "archive_unlock_state": unlock_state,
    }
