"""Items API — item definition CRUD and inventory queries."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import permissions
from app.domain.character import items as inventory
from app.infra.auth import get_current_user
from app.infra.db import get_db
from app.models.db_models import GamePlayer, User

router = APIRouter(prefix="/api/games/{game_id}/items", tags=["items"])


class CreateItemRequest(BaseModel):
    name: str
    description: str | None = None
    item_type: str = "generic"
    effect: dict | None = None
    stackable: bool = True


@router.post("/definitions")
async def create_item_definition(
    game_id: str,
    req: CreateItemRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    user_id: str | None = None,
) -> dict:
    acting_user_id = user_id or current_user.id
    try:
        await permissions.require_dm(db, game_id, acting_user_id)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    item_def = await inventory.create_item_definition(
        db, game_id=game_id, name=req.name,
        description=req.description, item_type=req.item_type,
        effect=req.effect, stackable=req.stackable,
    )
    return {"id": item_def.id, "name": item_def.name, "item_type": item_def.item_type}


@router.get("/definitions")
async def list_item_definitions(
    game_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    items = await inventory.get_item_definitions(db, game_id)
    return {
        "game_id": game_id,
        "definitions": [
            {"id": i.id, "name": i.name, "item_type": i.item_type, "description": i.description}
            for i in items
        ],
    }


@router.get("/inventory")
async def list_inventory(
    game_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    user_id: str | None = None,
) -> dict:
    acting_user_id = user_id or current_user.id
    gp_result = await db.execute(
        select(GamePlayer).where(
            GamePlayer.game_id == game_id,
            GamePlayer.user_id == acting_user_id,
        )
    )
    gp = gp_result.scalar_one_or_none()
    if gp is None or gp.active_patient_id is None:
        raise HTTPException(status_code=400, detail="No active character")
    items = await inventory.get_inventory(db, gp.active_patient_id)
    return {
        "patient_id": gp.active_patient_id,
        "items": [
            {"item_def_id": pi.item_def_id, "count": pi.count}
            for pi in items
        ],
    }
