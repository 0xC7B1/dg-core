"""Event definition management — DM-set event CRUD for sessions."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db_models import EventDefinition


async def set_event(
    db: AsyncSession,
    session_id: str,
    game_id: str,
    name: str,
    expression: str,
    color_restriction: str | None = None,
    created_by: str | None = None,
) -> EventDefinition:
    """DM creates/replaces an event definition for the current session."""
    # Deactivate any existing active event with the same name
    existing = await get_active_event(db, session_id, name)
    if existing is not None:
        existing.is_active = False

    event_def = EventDefinition(
        session_id=session_id,
        game_id=game_id,
        name=name,
        expression=expression,
        color_restriction=color_restriction.upper() if color_restriction else None,
        created_by=created_by,
    )
    db.add(event_def)
    await db.flush()
    return event_def


async def get_active_event(
    db: AsyncSession, session_id: str, event_name: str
) -> EventDefinition | None:
    result = await db.execute(
        select(EventDefinition).where(
            EventDefinition.session_id == session_id,
            EventDefinition.name == event_name,
            EventDefinition.is_active == True,  # noqa: E712
        )
    )
    return result.scalar_one_or_none()


async def get_active_events(
    db: AsyncSession, session_id: str
) -> list[EventDefinition]:
    result = await db.execute(
        select(EventDefinition).where(
            EventDefinition.session_id == session_id,
            EventDefinition.is_active == True,  # noqa: E712
        )
    )
    return list(result.scalars().all())


async def deactivate_event(
    db: AsyncSession, session_id: str, event_name: str
) -> EventDefinition:
    event_def = await get_active_event(db, session_id, event_name)
    if event_def is None:
        raise ValueError(f"No active event '{event_name}' in session")
    event_def.is_active = False
    await db.flush()
    return event_def


async def deactivate_event_by_id(
    db: AsyncSession, event_def_id: str
) -> EventDefinition:
    result = await db.execute(
        select(EventDefinition).where(EventDefinition.id == event_def_id)
    )
    event_def = result.scalar_one_or_none()
    if event_def is None:
        raise ValueError(f"Event definition {event_def_id} not found")
    event_def.is_active = False
    await db.flush()
    return event_def
