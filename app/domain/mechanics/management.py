"""DM management handlers — buff, item, event, attribute, and ability operations."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import character
from app.domain.character import buff as buff_mod, items as items_mod
from app.domain.dispatcher import register_handler
from app.domain.permissions import require_dm
from app.domain.session import event_def, timeline
from app.models.event import (
    AbilityAddPayload,
    AttributeSetPayload,
    BuffAddPayload,
    BuffRemovePayload,
    EventDeactivatePayload,
    EventDefinePayload,
    GameEvent,
    ItemGrantPayload,
)
from app.models.result import EngineResult


def _require_session(event: GameEvent) -> str:
    if not event.session_id:
        raise ValueError("session_id is required for this event type")
    return event.session_id


async def _handle_buff_add(db: AsyncSession, event: GameEvent) -> EngineResult:
    await require_dm(db, event.game_id, event.user_id)
    payload: BuffAddPayload = event.payload  # type: ignore[assignment]

    ghost = await character.get_ghost(db, payload.ghost_id)
    if ghost is None:
        return EngineResult(
            success=False, event_type="buff_add", error="Ghost not found"
        )

    buff = await buff_mod.add_buff(
        db,
        ghost_id=ghost.id,
        game_id=event.game_id,
        name=payload.name,
        expression=payload.expression,
        remaining_rounds=payload.remaining_rounds,
        created_by=event.user_id,
    )

    if event.session_id:
        await timeline.append_event(
            db, session_id=event.session_id, game_id=event.game_id,
            event_type="buff_add", actor_id=event.user_id,
            data={
                "ghost_id": payload.ghost_id,
                "buff_id": buff.id,
                "name": payload.name,
            },
        )

    return EngineResult(
        success=True,
        event_type="buff_add",
        data={
            "buff_id": buff.id,
            "ghost_id": payload.ghost_id,
            "name": buff.name,
            "expression": buff.expression,
            "buff_type": buff.buff_type,
            "remaining_rounds": buff.remaining_rounds,
        },
    )


async def _handle_buff_remove(db: AsyncSession, event: GameEvent) -> EngineResult:
    await require_dm(db, event.game_id, event.user_id)
    payload: BuffRemovePayload = event.payload  # type: ignore[assignment]

    await buff_mod.remove_buff(db, payload.buff_id)

    if event.session_id:
        await timeline.append_event(
            db, session_id=event.session_id, game_id=event.game_id,
            event_type="buff_remove", actor_id=event.user_id,
            data={"buff_id": payload.buff_id},
        )

    return EngineResult(
        success=True,
        event_type="buff_remove",
        data={"deleted": payload.buff_id},
    )


async def _handle_item_grant(db: AsyncSession, event: GameEvent) -> EngineResult:
    await require_dm(db, event.game_id, event.user_id)
    payload: ItemGrantPayload = event.payload  # type: ignore[assignment]

    pi = await items_mod.grant_item(
        db,
        patient_id=payload.patient_id,
        item_def_id=payload.item_def_id,
        count=payload.count,
    )

    if event.session_id:
        await timeline.append_event(
            db, session_id=event.session_id, game_id=event.game_id,
            event_type="item_grant", actor_id=event.user_id,
            data={
                "patient_id": payload.patient_id,
                "item_def_id": payload.item_def_id,
                "count": payload.count,
            },
        )

    return EngineResult(
        success=True,
        event_type="item_grant",
        data={
            "patient_id": pi.patient_id,
            "item_def_id": pi.item_def_id,
            "count": pi.count,
        },
    )


async def _handle_event_define(db: AsyncSession, event: GameEvent) -> EngineResult:
    await require_dm(db, event.game_id, event.user_id)
    sid = _require_session(event)
    payload: EventDefinePayload = event.payload  # type: ignore[assignment]

    ed = await event_def.set_event(
        db,
        session_id=sid,
        game_id=event.game_id,
        name=payload.name,
        expression=payload.expression,
        color_restriction=payload.color_restriction,
        created_by=event.user_id,
    )

    await timeline.append_event(
        db, session_id=sid, game_id=event.game_id,
        event_type="event_define", actor_id=event.user_id,
        data={
            "event_def_id": ed.id,
            "name": payload.name,
            "expression": payload.expression,
        },
    )

    return EngineResult(
        success=True,
        event_type="event_define",
        data={
            "event_def_id": ed.id,
            "name": ed.name,
            "expression": ed.expression,
            "color_restriction": ed.color_restriction,
            "is_active": ed.is_active,
        },
    )


async def _handle_event_deactivate(db: AsyncSession, event: GameEvent) -> EngineResult:
    await require_dm(db, event.game_id, event.user_id)
    payload: EventDeactivatePayload = event.payload  # type: ignore[assignment]

    await event_def.deactivate_event_by_id(db, payload.event_def_id)

    if event.session_id:
        await timeline.append_event(
            db, session_id=event.session_id, game_id=event.game_id,
            event_type="event_deactivate", actor_id=event.user_id,
            data={"event_def_id": payload.event_def_id},
        )

    return EngineResult(
        success=True,
        event_type="event_deactivate",
        data={"deactivated": payload.event_def_id},
    )


async def _handle_attribute_set(db: AsyncSession, event: GameEvent) -> EngineResult:
    await require_dm(db, event.game_id, event.user_id)
    payload: AttributeSetPayload = event.payload  # type: ignore[assignment]

    ghost = await character.get_ghost(db, payload.ghost_id)
    if ghost is None:
        return EngineResult(
            success=False, event_type="attribute_set", error="Ghost not found"
        )

    await character.set_ghost_attribute(db, ghost, payload.attribute, payload.value)

    if event.session_id:
        await timeline.append_event(
            db, session_id=event.session_id, game_id=event.game_id,
            event_type="attribute_set", actor_id=event.user_id,
            data={
                "ghost_id": payload.ghost_id,
                "attribute": payload.attribute,
                "value": payload.value,
            },
        )

    return EngineResult(
        success=True,
        event_type="attribute_set",
        data={
            "ghost_id": payload.ghost_id,
            "attribute": payload.attribute,
            "value": payload.value,
        },
    )


async def _handle_ability_add(db: AsyncSession, event: GameEvent) -> EngineResult:
    await require_dm(db, event.game_id, event.user_id)
    payload: AbilityAddPayload = event.payload  # type: ignore[assignment]

    ghost = await character.get_ghost(db, payload.ghost_id)
    if ghost is None:
        return EngineResult(
            success=False, event_type="ability_add", error="Ghost not found"
        )

    ability = await character.add_print_ability(
        db,
        ghost_id=ghost.id,
        name=payload.name,
        color=payload.color,
        description=payload.description,
        ability_count=payload.ability_count,
    )

    if event.session_id:
        await timeline.append_event(
            db, session_id=event.session_id, game_id=event.game_id,
            event_type="ability_add", actor_id=event.user_id,
            data={
                "ghost_id": payload.ghost_id,
                "ability_id": ability.id,
                "name": payload.name,
                "color": payload.color,
            },
        )

    return EngineResult(
        success=True,
        event_type="ability_add",
        data={
            "ability_id": ability.id,
            "ghost_id": payload.ghost_id,
            "name": ability.name,
            "color": ability.color,
            "description": ability.description,
            "ability_count": ability.ability_count,
        },
    )


# --- Self-registration ---

register_handler("buff_add", _handle_buff_add)
register_handler("buff_remove", _handle_buff_remove)
register_handler("item_grant", _handle_item_grant)
register_handler("event_define", _handle_event_define)
register_handler("event_deactivate", _handle_event_deactivate)
register_handler("attribute_set", _handle_attribute_set)
register_handler("ability_add", _handle_ability_add)
