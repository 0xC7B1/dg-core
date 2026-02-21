"""Characters API — patient/ghost CRUD, active character, abilities, archive unlock."""

from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import character, game as game_mod, permissions
from app.domain.character import buff as buff_mod
from app.api.deps import get_acting_user_id
from app.infra.auth import get_current_user
from app.infra.db import get_db
from app.models.db_models import GamePlayer, Ghost, User

router = APIRouter(prefix="/api/games/{game_id}", tags=["characters"])


# --- Request schemas ---

class CreatePatientRequest(BaseModel):
    user_id: str
    name: str
    soul_color: str
    gender: str | None = None
    age: int | None = None
    identity: str | None = None
    portrait_url: str | None = None
    personality_archives: dict | None = None
    ideal_projection: str | None = None


class CreateGhostRequest(BaseModel):
    origin_patient_id: str
    creator_user_id: str
    name: str
    soul_color: str
    appearance: str | None = None
    personality: str | None = None
    initial_hp: int = 10
    print_abilities: list[PrintAbilityInput] | None = None


class PrintAbilityInput(BaseModel):
    name: str
    color: str
    description: str | None = None
    ability_count: int = 1


CreateGhostRequest.model_rebuild()


class AssignCompanionRequest(BaseModel):
    patient_id: str


class SwitchCharacterRequest(BaseModel):
    patient_id: str


class UnlockArchiveRequest(BaseModel):
    fragment_id: str


# --- Patient CRUD ---

@router.post("/characters/patients")
async def create_patient(
    game_id: str,
    req: CreatePatientRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    patient = await character.create_patient(
        db,
        user_id=req.user_id,
        game_id=game_id,
        name=req.name,
        soul_color=req.soul_color,
        gender=req.gender,
        age=req.age,
        identity=req.identity,
        portrait_url=req.portrait_url,
        personality_archives=req.personality_archives,
        ideal_projection=req.ideal_projection,
    )
    swap = character.generate_swap_file(patient)
    return {"patient_id": patient.id, "name": patient.name, "swap_file": swap}


@router.get("/characters")
async def list_characters(
    game_id: str,
    acting_user_id: Annotated[str, Depends(get_acting_user_id)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    patients = await character.get_patients_in_game(db, game_id, user_id=acting_user_id)
    return {
        "game_id": game_id,
        "characters": [
            {"patient_id": p.id, "name": p.name, "soul_color": p.soul_color}
            for p in patients
        ],
    }


# --- Ghost CRUD ---

@router.post("/characters/ghosts")
async def create_ghost(
    game_id: str,
    req: CreateGhostRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    ghost = await character.create_ghost(
        db,
        origin_patient_id=req.origin_patient_id,
        creator_user_id=req.creator_user_id,
        game_id=game_id,
        name=req.name,
        soul_color=req.soul_color,
        appearance=req.appearance,
        personality=req.personality,
        initial_hp=req.initial_hp,
    )
    abilities = []
    if req.print_abilities:
        for pa in req.print_abilities:
            ability = await character.add_print_ability(
                db, ghost.id, pa.name, pa.color, pa.description, pa.ability_count
            )
            abilities.append({"id": ability.id, "name": ability.name, "color": ability.color})

    return {
        "ghost_id": ghost.id,
        "name": ghost.name,
        "cmyk": json.loads(ghost.cmyk_json),
        "hp": ghost.hp,
        "hp_max": ghost.hp_max,
        "print_abilities": abilities,
        "origin_snapshot": {
            "origin_name": ghost.origin_name,
            "origin_soul_color": ghost.origin_soul_color,
            "origin_identity": ghost.origin_identity,
            "origin_ideal_projection": ghost.origin_ideal_projection,
            "archive_unlock_state": json.loads(ghost.archive_unlock_json),
        },
    }


# --- Active character ---
# NOTE: static paths (/characters/active, /characters/unlock-archive) must be
# defined BEFORE /characters/{character_id} to avoid path param capture.

@router.get("/characters/active")
async def get_active_character(
    game_id: str,
    acting_user_id: Annotated[str, Depends(get_acting_user_id)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    gp_result = await db.execute(
        select(GamePlayer).where(
            GamePlayer.game_id == game_id,
            GamePlayer.user_id == acting_user_id,
        )
    )
    gp = gp_result.scalar_one_or_none()
    if gp is None:
        raise HTTPException(status_code=404, detail="Player not in game")
    if gp.active_patient_id is None:
        raise HTTPException(status_code=400, detail="No active character")

    patient = await character.get_patient(db, gp.active_patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found")

    ghost_result = await db.execute(
        select(Ghost).where(Ghost.current_patient_id == patient.id)
    )
    ghost = ghost_result.scalar_one_or_none()

    result: dict = {
        "patient": {
            "id": patient.id,
            "name": patient.name,
            "soul_color": patient.soul_color,
            "gender": patient.gender,
            "age": patient.age,
            "identity": patient.identity,
            "region_id": patient.current_region_id,
            "location_id": patient.current_location_id,
        },
    }

    if ghost:
        abilities = await character.get_print_abilities(db, ghost.id)
        buffs = await buff_mod.get_buffs(db, ghost.id)
        result["ghost"] = {
            "id": ghost.id,
            "name": ghost.name,
            "cmyk": json.loads(ghost.cmyk_json),
            "hp": ghost.hp,
            "hp_max": ghost.hp_max,
            "mp": ghost.mp,
            "mp_max": ghost.mp_max,
            "appearance": ghost.appearance,
            "personality": ghost.personality,
            "print_abilities": [
                {"id": a.id, "name": a.name, "color": a.color, "ability_count": a.ability_count}
                for a in abilities
            ],
            "buffs": [
                {"id": b.id, "name": b.name, "expression": b.expression, "remaining_rounds": b.remaining_rounds}
                for b in buffs
            ],
            "origin_data": character.get_unlocked_origin_data(ghost),
        }

    return result


@router.put("/characters/active")
async def switch_active_character(
    game_id: str,
    req: SwitchCharacterRequest,
    acting_user_id: Annotated[str, Depends(get_acting_user_id)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    try:
        gp = await game_mod.switch_character(db, game_id, acting_user_id, req.patient_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"active_patient_id": gp.active_patient_id}


# --- Archive unlock ---

@router.post("/characters/unlock-archive")
async def unlock_archive(
    game_id: str,
    req: UnlockArchiveRequest,
    acting_user_id: Annotated[str, Depends(get_acting_user_id)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    gp_result = await db.execute(
        select(GamePlayer).where(
            GamePlayer.game_id == game_id,
            GamePlayer.user_id == acting_user_id,
        )
    )
    gp = gp_result.scalar_one_or_none()
    if gp is None or gp.active_patient_id is None:
        raise HTTPException(status_code=400, detail="No active character")

    ghost_result = await db.execute(
        select(Ghost).where(Ghost.current_patient_id == gp.active_patient_id)
    )
    ghost = ghost_result.scalar_one_or_none()
    if ghost is None:
        raise HTTPException(status_code=400, detail="No companion ghost")

    try:
        unlock_result = await character.unlock_archive(db, req.fragment_id, ghost.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return unlock_result


# --- Patient by ID (dynamic path — MUST come after all static /characters/* routes) ---

@router.get("/characters/{patient_id}")
async def get_patient(
    game_id: str,
    patient_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    patient = await character.get_patient(db, patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found")

    result: dict = {
        "patient": {
            "id": patient.id,
            "name": patient.name,
            "soul_color": patient.soul_color,
            "gender": patient.gender,
            "age": patient.age,
            "identity": patient.identity,
            "current_region_id": patient.current_region_id,
            "current_location_id": patient.current_location_id,
        },
    }

    ghost_result = await db.execute(
        select(Ghost).where(Ghost.current_patient_id == patient.id)
    )
    ghost = ghost_result.scalar_one_or_none()
    if ghost:
        abilities = await character.get_print_abilities(db, ghost.id)
        buffs = await buff_mod.get_buffs(db, ghost.id)
        result["ghost"] = {
            "id": ghost.id,
            "name": ghost.name,
            "cmyk": json.loads(ghost.cmyk_json),
            "hp": ghost.hp,
            "hp_max": ghost.hp_max,
            "mp": ghost.mp,
            "mp_max": ghost.mp_max,
            "appearance": ghost.appearance,
            "personality": ghost.personality,
            "print_abilities": [
                {"id": a.id, "name": a.name, "color": a.color, "ability_count": a.ability_count}
                for a in abilities
            ],
            "buffs": [
                {"id": b.id, "name": b.name, "expression": b.expression, "remaining_rounds": b.remaining_rounds}
                for b in buffs
            ],
            "origin_data": character.get_unlocked_origin_data(ghost),
        }

    return result


@router.delete("/characters/{patient_id}")
async def delete_patient_endpoint(
    game_id: str,
    patient_id: str,
    acting_user_id: Annotated[str, Depends(get_acting_user_id)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    patient = await character.get_patient(db, patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    is_owner = patient.user_id == acting_user_id
    is_dm = False
    try:
        await permissions.require_dm(db, game_id, acting_user_id)
        is_dm = True
    except ValueError:
        pass
    if not is_owner and not is_dm:
        raise HTTPException(status_code=403, detail="Only DM or character owner can delete")
    try:
        await character.delete_patient(db, patient_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"deleted": patient_id}


# --- Ghost sub-resources ---

@router.put("/ghosts/{ghost_id}/companion")
async def assign_ghost_companion(
    game_id: str,
    ghost_id: str,
    req: AssignCompanionRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    ghost = await character.get_ghost(db, ghost_id)
    if ghost is None:
        raise HTTPException(status_code=404, detail="Ghost not found")
    ghost.current_patient_id = req.patient_id
    await db.flush()
    return {"ghost_id": ghost.id, "current_patient_id": ghost.current_patient_id}


@router.get("/ghosts/{ghost_id}/abilities")
async def list_abilities(
    game_id: str,
    ghost_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    ghost = await character.get_ghost(db, ghost_id)
    if ghost is None:
        raise HTTPException(status_code=404, detail="Ghost not found")
    abilities = await character.get_print_abilities(db, ghost_id)
    return {
        "ghost_id": ghost_id,
        "abilities": [
            {"id": a.id, "name": a.name, "color": a.color, "description": a.description, "ability_count": a.ability_count}
            for a in abilities
        ],
    }


@router.get("/ghosts/{ghost_id}/buffs")
async def list_buffs(
    game_id: str,
    ghost_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    ghost = await character.get_ghost(db, ghost_id)
    if ghost is None:
        raise HTTPException(status_code=404, detail="Ghost not found")
    buffs = await buff_mod.get_buffs(db, ghost_id)
    return {
        "ghost_id": ghost_id,
        "buffs": [
            {
                "id": b.id,
                "name": b.name,
                "expression": b.expression,
                "buff_type": b.buff_type,
                "remaining_rounds": b.remaining_rounds,
            }
            for b in buffs
        ],
    }
