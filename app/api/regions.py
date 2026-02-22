"""Regions API — region and location CRUD."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import world as region_mod
from app.infra.auth import get_current_user
from app.infra.db import get_db
from app.models.db_models import Patient, User
from app.models.responses import (
    CreateLocationResponse,
    CreateRegionResponse,
    ListLocationsResponse,
    ListRegionsResponse,
    LocationInfo,
    LocationPlayersResponse,
    PatientSummary,
    RegionInfo,
)

router = APIRouter(prefix="/api/games/{game_id}", tags=["regions"])


class CreateRegionRequest(BaseModel):
    code: str
    name: str
    description: str | None = None
    metadata: dict | None = None
    sort_order: int = 0


class CreateLocationRequest(BaseModel):
    name: str
    description: str | None = None
    content: str | None = None
    metadata: dict | None = None
    sort_order: int = 0


@router.post("/regions")
async def create_region(
    game_id: str,
    req: CreateRegionRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CreateRegionResponse:
    region = await region_mod.create_region(
        db, game_id=game_id, name=req.name, code=req.code,
        description=req.description, metadata=req.metadata, sort_order=req.sort_order,
    )
    return CreateRegionResponse(region_id=region.id, game_id=game_id, code=region.code, name=region.name)


@router.get("/regions")
async def list_regions(
    game_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    name: str | None = None,
) -> ListRegionsResponse:
    regions = await region_mod.get_regions(db, game_id, name=name)
    return ListRegionsResponse(
        game_id=game_id,
        regions=[
            RegionInfo(id=r.id, code=r.code, name=r.name, description=r.description)
            for r in regions
        ],
    )


@router.post("/regions/{region_id}/locations")
async def create_location(
    game_id: str,
    region_id: str,
    req: CreateLocationRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CreateLocationResponse:
    location = await region_mod.create_location(
        db, region_id=region_id, name=req.name,
        description=req.description, content=req.content,
        metadata=req.metadata, sort_order=req.sort_order,
    )
    return CreateLocationResponse(location_id=location.id, region_id=region_id, name=location.name)


@router.get("/regions/{region_id}/locations")
async def list_locations(
    game_id: str,
    region_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    name: str | None = None,
) -> ListLocationsResponse:
    locations = await region_mod.get_locations(db, region_id, name=name)
    return ListLocationsResponse(
        region_id=region_id,
        locations=[
            LocationInfo(id=loc.id, name=loc.name, description=loc.description)
            for loc in locations
        ],
    )


@router.get("/locations/{location_id}/players")
async def get_location_players(
    game_id: str,
    location_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LocationPlayersResponse:
    patients_result = await db.execute(
        select(Patient).where(
            Patient.game_id == game_id,
            Patient.current_location_id == location_id,
        )
    )
    patients = list(patients_result.scalars().all())
    return LocationPlayersResponse(
        location_id=location_id,
        players=[
            PatientSummary(patient_id=p.id, name=p.name, soul_color=p.soul_color)
            for p in patients
        ],
    )
