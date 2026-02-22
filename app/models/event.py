"""Game event schemas — input to the engine dispatcher."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, model_validator


class EventType(str, Enum):
    # Game lifecycle events
    GAME_START = "game_start"
    GAME_END = "game_end"
    PLAYER_JOIN = "player_join"
    PLAYER_LEAVE = "player_leave"

    # Session lifecycle events
    SESSION_START = "session_start"
    SESSION_END = "session_end"

    # Event check system
    EVENT_CHECK = "event_check"
    REROLL = "reroll"
    HARD_REROLL = "hard_reroll"

    # Combat events
    ATTACK = "attack"
    DEFEND = "defend"

    # Communication events
    COMM_REQUEST = "comm_request"
    COMM_ACCEPT = "comm_accept"
    COMM_REJECT = "comm_reject"
    COMM_CANCEL = "comm_cancel"

    # Item events
    ITEM_USE = "item_use"

    # State events
    APPLY_FRAGMENT = "apply_fragment"
    HP_CHANGE = "hp_change"
    REGION_TRANSITION = "region_transition"
    LOCATION_TRANSITION = "location_transition"

    # DM management events
    BUFF_ADD = "buff_add"
    BUFF_REMOVE = "buff_remove"
    ITEM_GRANT = "item_grant"
    EVENT_DEFINE = "event_define"
    EVENT_DEACTIVATE = "event_deactivate"
    ATTRIBUTE_SET = "attribute_set"
    ABILITY_ADD = "ability_add"


# --- Payload models ---


class GameStartPayload(BaseModel):
    event_type: Literal["game_start"] = "game_start"


class GameEndPayload(BaseModel):
    event_type: Literal["game_end"] = "game_end"


class PlayerJoinPayload(BaseModel):
    event_type: Literal["player_join"] = "player_join"
    role: str = "PL"  # "DM" or "PL"


class PlayerLeavePayload(BaseModel):
    event_type: Literal["player_leave"] = "player_leave"


class SessionStartPayload(BaseModel):
    event_type: Literal["session_start"] = "session_start"
    region_id: str | None = None
    location_id: str | None = None


class SessionEndPayload(BaseModel):
    event_type: Literal["session_end"] = "session_end"


# --- Event check payloads ---


class EventCheckPayload(BaseModel):
    event_type: Literal["event_check"] = "event_check"
    event_name: str
    color: str | None = None  # Override color; if omitted, uses soul_color


class RerollPayload(BaseModel):
    event_type: Literal["reroll"] = "reroll"
    event_name: str
    ability_id: str  # Same-color PrintAbility to consume


class HardRerollPayload(BaseModel):
    event_type: Literal["hard_reroll"] = "hard_reroll"
    event_name: str
    ability_id: str  # Any-color PrintAbility to consume (costs 1 MP)


# --- Combat payloads ---


class AttackPayload(BaseModel):
    event_type: Literal["attack"] = "attack"
    attacker_ghost_id: str
    target_ghost_id: str
    color_used: str  # C/M/Y/K


class DefendPayload(BaseModel):
    event_type: Literal["defend"] = "defend"
    defender_ghost_id: str
    color_used: str  # C/M/Y/K


# --- Communication payloads ---


class CommRequestPayload(BaseModel):
    event_type: Literal["comm_request"] = "comm_request"
    target_patient_id: str


class CommAcceptPayload(BaseModel):
    event_type: Literal["comm_accept"] = "comm_accept"
    request_id: str
    ability_id: str | None = None  # Required if target has multiple abilities


class CommRejectPayload(BaseModel):
    event_type: Literal["comm_reject"] = "comm_reject"
    request_id: str


class CommCancelPayload(BaseModel):
    event_type: Literal["comm_cancel"] = "comm_cancel"
    request_id: str


# --- Item payloads ---


class ItemUsePayload(BaseModel):
    event_type: Literal["item_use"] = "item_use"
    item_def_id: str


# --- State payloads ---


class ApplyFragmentPayload(BaseModel):
    event_type: Literal["apply_fragment"] = "apply_fragment"
    ghost_id: str
    color: str  # C/M/Y/K
    value: int = 1


class HPChangePayload(BaseModel):
    event_type: Literal["hp_change"] = "hp_change"
    ghost_id: str
    delta: int
    reason: str = ""


class RegionTransitionPayload(BaseModel):
    event_type: Literal["region_transition"] = "region_transition"
    target_region_id: str | None = None
    target_region_name: str | None = None

    @model_validator(mode="after")
    def check_region_provided(self) -> "RegionTransitionPayload":
        if not self.target_region_id and not self.target_region_name:
            raise ValueError("Must provide target_region_id or target_region_name")
        return self


class LocationTransitionPayload(BaseModel):
    event_type: Literal["location_transition"] = "location_transition"
    target_location_id: str | None = None
    target_location_name: str | None = None

    @model_validator(mode="after")
    def check_location_provided(self) -> "LocationTransitionPayload":
        if not self.target_location_id and not self.target_location_name:
            raise ValueError("Must provide target_location_id or target_location_name")
        return self


# --- DM management payloads ---


class BuffAddPayload(BaseModel):
    event_type: Literal["buff_add"] = "buff_add"
    ghost_id: str
    name: str
    expression: str
    remaining_rounds: int = 1


class BuffRemovePayload(BaseModel):
    event_type: Literal["buff_remove"] = "buff_remove"
    buff_id: str


class ItemGrantPayload(BaseModel):
    event_type: Literal["item_grant"] = "item_grant"
    patient_id: str
    item_def_id: str
    count: int = 1


class EventDefinePayload(BaseModel):
    event_type: Literal["event_define"] = "event_define"
    name: str
    expression: str
    color_restriction: str | None = None


class EventDeactivatePayload(BaseModel):
    event_type: Literal["event_deactivate"] = "event_deactivate"
    event_def_id: str


class AttributeSetPayload(BaseModel):
    event_type: Literal["attribute_set"] = "attribute_set"
    ghost_id: str
    attribute: str  # hp, mp, hp_max, mp_max, cmyk.C/M/Y/K
    value: int


class AbilityAddPayload(BaseModel):
    event_type: Literal["ability_add"] = "ability_add"
    ghost_id: str
    name: str
    description: str = ""
    color: str  # C/M/Y/K
    ability_count: int = 1


EventPayload = Annotated[
    Union[
        GameStartPayload,
        GameEndPayload,
        PlayerJoinPayload,
        PlayerLeavePayload,
        SessionStartPayload,
        SessionEndPayload,
        EventCheckPayload,
        RerollPayload,
        HardRerollPayload,
        AttackPayload,
        DefendPayload,
        CommRequestPayload,
        CommAcceptPayload,
        CommRejectPayload,
        CommCancelPayload,
        ItemUsePayload,
        ApplyFragmentPayload,
        HPChangePayload,
        RegionTransitionPayload,
        LocationTransitionPayload,
        BuffAddPayload,
        BuffRemovePayload,
        ItemGrantPayload,
        EventDefinePayload,
        EventDeactivatePayload,
        AttributeSetPayload,
        AbilityAddPayload,
    ],
    Field(discriminator="event_type"),
]


class GameEvent(BaseModel):
    """Top-level event submitted by a client to the engine."""

    game_id: str
    session_id: str | None = None
    user_id: str
    payload: EventPayload
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
