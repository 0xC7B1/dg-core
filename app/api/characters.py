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
from app.models.responses import (
    ActiveCharacterResponse,
    AssignCompanionResponse,
    BuffInfo,
    CreateGhostResponse,
    CreatePatientResponse,
    DeletePatientResponse,
    GhostDetail,
    GhostSummary,
    ListAbilitiesResponse,
    ListBuffsResponse,
    ListCharactersResponse,
    ListGhostsResponse,
    OriginSnapshot,
    PatientBrief,
    PatientDetailResponse,
    PatientFull,
    PatientSummary,
    PrintAbilityCreated,
    PrintAbilityInfo,
    SwitchCharacterResponse,
    UnlockArchiveResponse,
)

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
) -> CreatePatientResponse:
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
    return CreatePatientResponse(patient_id=patient.id, name=patient.name, swap_file=swap)


@router.get("/characters")
async def list_characters(
    game_id: str,
    acting_user_id: Annotated[str, Depends(get_acting_user_id)],
    db: Annotated[AsyncSession, Depends(get_db)],
    name: str | None = None,
    all: bool = False,
) -> ListCharactersResponse:
    if all:
        patients = await character.get_all_patients_in_game(db, game_id, name=name)
    else:
        patients = await character.get_patients_in_game(db, game_id, user_id=acting_user_id)
        if name:
            patients = [p for p in patients if name.lower() in p.name.lower()]
    return ListCharactersResponse(
        game_id=game_id,
        characters=[
            PatientSummary(patient_id=p.id, name=p.name, soul_color=p.soul_color)
            for p in patients
        ],
    )


# --- Ghost CRUD ---

@router.post("/characters/ghosts")
async def create_ghost(
    game_id: str,
    req: CreateGhostRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CreateGhostResponse:
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
            abilities.append(PrintAbilityCreated(id=ability.id, name=ability.name, color=ability.color))

    return CreateGhostResponse(
        ghost_id=ghost.id,
        name=ghost.name,
        cmyk=json.loads(ghost.cmyk_json),
        hp=ghost.hp,
        hp_max=ghost.hp_max,
        print_abilities=abilities,
        origin_snapshot=OriginSnapshot(
            origin_name=ghost.origin_name,
            origin_soul_color=ghost.origin_soul_color,
            origin_identity=ghost.origin_identity,
            origin_ideal_projection=ghost.origin_ideal_projection,
            archive_unlock_state=json.loads(ghost.archive_unlock_json),
        ),
    )


@router.get("/characters/ghosts")
async def list_ghosts(
    game_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    name: str | None = None,
) -> ListGhostsResponse:
    """List all ghosts in a game, optionally filtered by name."""
    ghosts = await character.get_ghosts_in_game(db, game_id, name=name)
    items = []
    for g in ghosts:
        cmyk = json.loads(g.cmyk_json) if g.cmyk_json else {"C": 0, "M": 0, "Y": 0, "K": 0}
        patient_name = None
        if g.current_patient_id:
            patient = await character.get_patient(db, g.current_patient_id)
            patient_name = patient.name if patient else None
        items.append(GhostSummary(
            ghost_id=g.id,
            name=g.name,
            current_patient_id=g.current_patient_id,
            current_patient_name=patient_name,
            cmyk=cmyk,
            hp=g.hp,
            hp_max=g.hp_max,
        ))
    return ListGhostsResponse(game_id=game_id, ghosts=items)


# --- Active character ---
# NOTE: static paths (/characters/active, /characters/unlock-archive) must be
# defined BEFORE /characters/{character_id} to avoid path param capture.

@router.get("/characters/active")
async def get_active_character(
    game_id: str,
    acting_user_id: Annotated[str, Depends(get_acting_user_id)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ActiveCharacterResponse:
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

    ghost_detail = None
    if ghost:
        abilities = await character.get_print_abilities(db, ghost.id)
        buffs = await buff_mod.get_buffs(db, ghost.id)
        ghost_detail = GhostDetail(
            id=ghost.id,
            name=ghost.name,
            cmyk=json.loads(ghost.cmyk_json),
            hp=ghost.hp,
            hp_max=ghost.hp_max,
            mp=ghost.mp,
            mp_max=ghost.mp_max,
            appearance=ghost.appearance,
            personality=ghost.personality,
            print_abilities=[
                PrintAbilityInfo(id=a.id, name=a.name, color=a.color, ability_count=a.ability_count)
                for a in abilities
            ],
            buffs=[
                BuffInfo(id=b.id, name=b.name, expression=b.expression, remaining_rounds=b.remaining_rounds)
                for b in buffs
            ],
            origin_data=character.get_unlocked_origin_data(ghost),
        )

    return ActiveCharacterResponse(
        patient=PatientBrief(
            id=patient.id,
            name=patient.name,
            soul_color=patient.soul_color,
            gender=patient.gender,
            age=patient.age,
            identity=patient.identity,
            region_id=patient.current_region_id,
            location_id=patient.current_location_id,
        ),
        ghost=ghost_detail,
    )


@router.put("/characters/active")
async def switch_active_character(
    game_id: str,
    req: SwitchCharacterRequest,
    acting_user_id: Annotated[str, Depends(get_acting_user_id)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SwitchCharacterResponse:
    try:
        gp = await game_mod.switch_character(db, game_id, acting_user_id, req.patient_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return SwitchCharacterResponse(active_patient_id=gp.active_patient_id)


# --- Archive unlock ---

@router.post("/characters/unlock-archive")
async def unlock_archive(
    game_id: str,
    req: UnlockArchiveRequest,
    acting_user_id: Annotated[str, Depends(get_acting_user_id)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UnlockArchiveResponse:
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

    return UnlockArchiveResponse(**unlock_result)


# --- Patient by ID (dynamic path — MUST come after all static /characters/* routes) ---

@router.get("/characters/{patient_id}")
async def get_patient(
    game_id: str,
    patient_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PatientDetailResponse:
    patient = await character.get_patient(db, patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found")

    ghost_result = await db.execute(
        select(Ghost).where(Ghost.current_patient_id == patient.id)
    )
    ghost = ghost_result.scalar_one_or_none()

    ghost_detail = None
    if ghost:
        abilities = await character.get_print_abilities(db, ghost.id)
        buffs = await buff_mod.get_buffs(db, ghost.id)
        ghost_detail = GhostDetail(
            id=ghost.id,
            name=ghost.name,
            cmyk=json.loads(ghost.cmyk_json),
            hp=ghost.hp,
            hp_max=ghost.hp_max,
            mp=ghost.mp,
            mp_max=ghost.mp_max,
            appearance=ghost.appearance,
            personality=ghost.personality,
            print_abilities=[
                PrintAbilityInfo(id=a.id, name=a.name, color=a.color, ability_count=a.ability_count)
                for a in abilities
            ],
            buffs=[
                BuffInfo(id=b.id, name=b.name, expression=b.expression, remaining_rounds=b.remaining_rounds)
                for b in buffs
            ],
            origin_data=character.get_unlocked_origin_data(ghost),
        )

    return PatientDetailResponse(
        patient=PatientFull(
            id=patient.id,
            name=patient.name,
            soul_color=patient.soul_color,
            gender=patient.gender,
            age=patient.age,
            identity=patient.identity,
            current_region_id=patient.current_region_id,
            current_location_id=patient.current_location_id,
        ),
        ghost=ghost_detail,
    )


@router.delete("/characters/{patient_id}")
async def delete_patient_endpoint(
    game_id: str,
    patient_id: str,
    acting_user_id: Annotated[str, Depends(get_acting_user_id)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DeletePatientResponse:
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
    return DeletePatientResponse(deleted=patient_id)


# --- Ghost sub-resources ---

@router.put("/ghosts/{ghost_id}/companion")
async def assign_ghost_companion(
    game_id: str,
    ghost_id: str,
    req: AssignCompanionRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AssignCompanionResponse:
    try:
        await permissions.require_dm(db, game_id, current_user.id)
    except ValueError:
        raise HTTPException(status_code=403, detail="Only DM can assign companions")

    ghost = await character.get_ghost(db, ghost_id)
    if ghost is None:
        raise HTTPException(status_code=404, detail="Ghost not found")
    if ghost.game_id != game_id:
        raise HTTPException(status_code=400, detail="Ghost not in this game")

    patient = await character.get_patient(db, req.patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    if patient.game_id != game_id:
        raise HTTPException(status_code=400, detail="Patient not in this game")

    # Check no other ghost is already assigned to this patient
    existing = await db.execute(
        select(Ghost).where(
            Ghost.current_patient_id == req.patient_id,
            Ghost.id != ghost_id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="Patient already has a companion ghost")

    # Set via relationship so SQLAlchemy updates both sides of back_populates
    ghost.current_patient = patient
    await db.flush()
    return AssignCompanionResponse(ghost_id=ghost.id, current_patient_id=ghost.current_patient_id)


@router.get("/ghosts/{ghost_id}/abilities")
async def list_abilities(
    game_id: str,
    ghost_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ListAbilitiesResponse:
    ghost = await character.get_ghost(db, ghost_id)
    if ghost is None:
        raise HTTPException(status_code=404, detail="Ghost not found")
    abilities = await character.get_print_abilities(db, ghost_id)
    return ListAbilitiesResponse(
        ghost_id=ghost_id,
        abilities=[
            PrintAbilityInfo(id=a.id, name=a.name, color=a.color, description=a.description, ability_count=a.ability_count)
            for a in abilities
        ],
    )


@router.get("/ghosts/{ghost_id}/buffs")
async def list_buffs(
    game_id: str,
    ghost_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ListBuffsResponse:
    ghost = await character.get_ghost(db, ghost_id)
    if ghost is None:
        raise HTTPException(status_code=404, detail="Ghost not found")
    buffs = await buff_mod.get_buffs(db, ghost_id)
    return ListBuffsResponse(
        ghost_id=ghost_id,
        buffs=[
            BuffInfo(
                id=b.id,
                name=b.name,
                expression=b.expression,
                buff_type=b.buff_type,
                remaining_rounds=b.remaining_rounds,
            )
            for b in buffs
        ],
    )
