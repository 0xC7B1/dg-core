"""State handlers — fragment, HP, region/location transitions, item use."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import character, world as region_mod
from app.domain.character import items as inventory
from app.domain.dispatcher import register_handler
from app.domain.resolution import find_player_ghost, resolve_patient_for_event
from app.domain.session import timeline
from app.domain.session.timeline import create_player_snapshot
from app.models.event import (
    ApplyFragmentPayload,
    GameEvent,
    HPChangePayload,
    ItemUsePayload,
    LocationTransitionPayload,
    RegionTransitionPayload,
)
from app.models.result import EngineResult, StateChange


def _require_session(event: GameEvent) -> str:
    """Return session_id or raise if missing."""
    if not event.session_id:
        raise ValueError("session_id is required for this event type")
    return event.session_id


async def _handle_apply_fragment(db: AsyncSession, event: GameEvent) -> EngineResult:
    sid = _require_session(event)
    payload: ApplyFragmentPayload = event.payload  # type: ignore[assignment]
    ghost = await character.get_ghost(db, payload.ghost_id)
    if ghost is None:
        return EngineResult(
            success=False, event_type="apply_fragment", error="Ghost not found"
        )
    fragment_result = await character.apply_color_fragment(db, ghost, payload.color, payload.value)
    new_cmyk = fragment_result["cmyk"]
    # Snapshot after state change (ghost CMYK changed)
    await create_player_snapshot(db, event.game_id, event.user_id, ghost=ghost)
    await timeline.append_event(
        db, session_id=sid, game_id=event.game_id,
        event_type="apply_fragment",
        user_id=event.user_id,
        data={"ghost_id": payload.ghost_id, "color": payload.color, "value": payload.value},
    )
    return EngineResult(
        success=True,
        event_type="apply_fragment",
        data={"ghost_id": payload.ghost_id, "cmyk": new_cmyk, "fragment_id": fragment_result["fragment_id"]},
        state_changes=[
            StateChange(
                entity_type="ghost",
                entity_id=payload.ghost_id,
                field=f"cmyk.{payload.color.upper()}",
                new_value=str(new_cmyk[payload.color.upper()]),
            )
        ],
    )


async def _handle_hp_change(db: AsyncSession, event: GameEvent) -> EngineResult:
    sid = _require_session(event)
    payload: HPChangePayload = event.payload  # type: ignore[assignment]
    ghost = await character.get_ghost(db, payload.ghost_id)
    if ghost is None:
        return EngineResult(
            success=False, event_type="hp_change", error="Ghost not found"
        )
    old_hp = ghost.hp
    new_hp, collapsed = await character.change_hp(db, ghost, payload.delta)
    await timeline.append_event(
        db, session_id=sid, game_id=event.game_id,
        event_type="hp_change",
        user_id=event.user_id,
        data={"ghost_id": payload.ghost_id, "delta": payload.delta, "reason": payload.reason},
        result_data={"new_hp": new_hp, "collapsed": collapsed},
    )
    return EngineResult(
        success=True,
        event_type="hp_change",
        data={
            "ghost_id": payload.ghost_id,
            "old_hp": old_hp,
            "new_hp": new_hp,
            "collapsed": collapsed,
        },
        state_changes=[
            StateChange(
                entity_type="ghost",
                entity_id=payload.ghost_id,
                field="hp",
                old_value=str(old_hp),
                new_value=str(new_hp),
            )
        ],
    )


async def _handle_region_transition(db: AsyncSession, event: GameEvent) -> EngineResult:
    payload: RegionTransitionPayload = event.payload  # type: ignore[assignment]
    region_id = payload.target_region_id
    if region_id is None:
        region = await region_mod.get_region_by_name(db, event.game_id, payload.target_region_name)  # type: ignore[arg-type]
        if region is None:
            return EngineResult(
                success=False,
                event_type="region_transition",
                error=f"Region '{payload.target_region_name}' not found in this game",
            )
        region_id = region.id
    patient = await region_mod.move_character(
        db, event.game_id, event.user_id, region_id=region_id
    )
    if event.session_id:
        # Snapshot after state change (patient position changed)
        await create_player_snapshot(db, event.game_id, event.user_id, patient=patient)
        await timeline.append_event(
            db, session_id=event.session_id, game_id=event.game_id,
            event_type="region_transition", user_id=event.user_id,
            data={"target_region_id": region_id},
        )
    return EngineResult(
        success=True,
        event_type="region_transition",
        data={"user_id": event.user_id, "region_id": region_id},
        state_changes=[
            StateChange(
                entity_type="patient",
                entity_id=patient.id,
                field="current_region_id",
                new_value=region_id,
            )
        ],
    )


async def _handle_location_transition(db: AsyncSession, event: GameEvent) -> EngineResult:
    payload: LocationTransitionPayload = event.payload  # type: ignore[assignment]
    location_id = payload.target_location_id
    if location_id is None:
        location = await region_mod.get_location_by_name(db, event.game_id, payload.target_location_name)  # type: ignore[arg-type]
        if location is None:
            return EngineResult(
                success=False,
                event_type="location_transition",
                error=f"Location '{payload.target_location_name}' not found in this game",
            )
        location_id = location.id
    patient = await region_mod.move_character(
        db, event.game_id, event.user_id, location_id=location_id
    )
    if event.session_id:
        # Snapshot after state change (patient position changed)
        await create_player_snapshot(db, event.game_id, event.user_id, patient=patient)
        await timeline.append_event(
            db, session_id=event.session_id, game_id=event.game_id,
            event_type="location_transition", user_id=event.user_id,
            data={"target_location_id": location_id},
        )
    return EngineResult(
        success=True,
        event_type="location_transition",
        data={"user_id": event.user_id, "location_id": location_id},
        state_changes=[
            StateChange(
                entity_type="patient",
                entity_id=patient.id,
                field="current_location_id",
                new_value=location_id,
            )
        ],
    )


async def _handle_item_use(db: AsyncSession, event: GameEvent) -> EngineResult:
    sid = _require_session(event)
    payload: ItemUsePayload = event.payload  # type: ignore[assignment]

    patient = await resolve_patient_for_event(db, event)
    if patient is None:
        return EngineResult(
            success=False, event_type="item_use",
            error="No active character found",
        )

    ghost = await find_player_ghost(db, patient_id=patient.id)
    if ghost is None:
        return EngineResult(
            success=False, event_type="item_use",
            error="Player has no ghost in this game",
        )

    result = await inventory.use_item(
        db,
        game_id=event.game_id,
        patient_id=patient.id,
        item_def_id=payload.item_def_id,
        ghost=ghost,
    )

    if result.success:
        await timeline.append_event(
            db, session_id=sid, game_id=event.game_id,
            event_type="item_use", user_id=event.user_id,
            data={"item_def_id": payload.item_def_id},
            result_data=result.data,
        )

    return result


# --- Self-registration ---

register_handler("apply_fragment", _handle_apply_fragment)
register_handler("hp_change", _handle_hp_change)
register_handler("region_transition", _handle_region_transition)
register_handler("location_transition", _handle_location_transition)
register_handler("item_use", _handle_item_use)
