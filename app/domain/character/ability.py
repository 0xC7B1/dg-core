"""PrintAbility CRUD — add, get, list, use abilities."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db_models import PrintAbility


async def add_print_ability(
    db: AsyncSession,
    ghost_id: str,
    name: str,
    color: str,
    description: str | None = None,
    ability_count: int = 1,
) -> PrintAbility:
    ability = PrintAbility(
        ghost_id=ghost_id,
        name=name,
        description=description,
        color=color.upper(),
        ability_count=ability_count,
    )
    db.add(ability)
    await db.flush()
    return ability


async def get_print_abilities(db: AsyncSession, ghost_id: str) -> list[PrintAbility]:
    result = await db.execute(
        select(PrintAbility).where(PrintAbility.ghost_id == ghost_id)
    )
    return list(result.scalars().all())


async def get_print_ability(db: AsyncSession, ability_id: str) -> PrintAbility | None:
    result = await db.execute(select(PrintAbility).where(PrintAbility.id == ability_id))
    return result.scalar_one_or_none()


async def use_print_ability(db: AsyncSession, ability: PrintAbility) -> bool:
    """Consume one use of a print ability. Returns True if successful."""
    if ability.ability_count <= 0:
        return False
    ability.ability_count -= 1
    await db.flush()
    return True
