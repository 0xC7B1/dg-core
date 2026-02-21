"""Dice API — standalone dice rolling."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.auth import get_current_user
from app.infra.db import get_db
from app.models.db_models import User
from app.modules.dice.parser import roll_expression


router = APIRouter(prefix="/api/dice", tags=["dice"])


class RollRequest(BaseModel):
    expression: str
    game_id: str | None = None


@router.post("/roll")
async def roll_dice(
    req: RollRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    try:
        result = roll_expression(req.expression)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "expression": result.expression,
        "individual_rolls": result.individual_rolls,
        "total": result.total,
    }
