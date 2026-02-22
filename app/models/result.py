"""Engine result schemas — output from the engine dispatcher."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class DiceRollResult(BaseModel):
    dice_count: int
    dice_type: int
    results: list[int]
    total: int
    difficulty: int
    success: bool
    rerolled: bool = False
    reroll_results: list[int] | None = None


class DiceExpressionRollResult(BaseModel):
    """Result of evaluating a dice expression (richer than DiceRollResult)."""

    expression: str
    dice_count: int
    dice_sides: int
    individual_rolls: list[int]
    kept_rolls: list[int] | None = None
    subtotal: int
    modifier: int
    total: int
    is_cmyk: bool = False
    cmyk_color: str | None = None


class StateChange(BaseModel):
    entity_type: str  # "ghost", "patient", "game", "game_player", "print_ability"
    entity_id: str
    field: str
    old_value: str | None = None
    new_value: str | None = None


class PlayerSnapshot(BaseModel):
    """Point-in-time snapshot of a player's state for timeline events."""

    user_id: str
    username: str
    role: str  # "DM" or "PL"
    patient_id: str | None = None
    patient_name: str | None = None
    soul_color: str | None = None
    ghost_id: str | None = None
    ghost_name: str | None = None
    hp: int | None = None
    hp_max: int | None = None
    mp: int | None = None
    mp_max: int | None = None
    cmyk: dict[str, int] | None = None
    region_id: str | None = None
    location_id: str | None = None
    buffs: list[dict[str, Any]] | None = None

    @property
    def display_name(self) -> str:
        if self.role == "DM":
            return self.username
        parts = []
        if self.patient_name:
            parts.append(f"[患者]{self.patient_name}")
        if self.ghost_name:
            parts.append(f"[幽灵]{self.ghost_name}")
        return "/".join(parts) if parts else self.username


class EngineResult(BaseModel):
    success: bool
    event_type: str
    data: dict[str, Any] = Field(default_factory=dict)
    narrative: str | None = None
    state_changes: list[StateChange] = []
    rolls: list[DiceRollResult] = []
    error: str | None = None
