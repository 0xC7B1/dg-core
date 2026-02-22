"""Typed response models for OpenAPI schema generation."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


# ── Shared sub-models ──────────────────────────────────────────────


class PlatformBindingInfo(BaseModel):
    platform: str
    platform_uid: str
    bound_at: str


class GamePlayerInfo(BaseModel):
    user_id: str
    role: str
    active_patient_id: str | None


class TimelineEventInfo(BaseModel):
    id: str
    session_id: str | None = None
    event_type: str
    actor_id: str | None
    data: str | None
    result_data: str | None
    created_at: str | None


class PatientSummary(BaseModel):
    patient_id: str
    name: str
    soul_color: str


class PrintAbilityInfo(BaseModel):
    id: str
    name: str
    color: str
    description: str | None = None
    ability_count: int


class BuffInfo(BaseModel):
    id: str
    name: str
    expression: str
    buff_type: str | None = None
    remaining_rounds: int


# ── Auth responses ─────────────────────────────────────────────────


class RegisterResponse(BaseModel):
    user_id: str
    api_key: str
    access_token: str
    expires_at: str


class TokenResponse(BaseModel):
    user_id: str
    access_token: str
    expires_at: str


class ResolvePlatformResponse(BaseModel):
    user_id: str
    username: str


class PlatformBindResponse(BaseModel):
    user_id: str
    platform: str
    platform_uid: str
    status: str


class UserProfileResponse(BaseModel):
    user_id: str
    username: str
    role: str
    is_active: bool
    created_at: str
    platform_bindings: list[PlatformBindingInfo]


class RegenerateApiKeyResponse(BaseModel):
    user_id: str
    api_key: str


# ── Games responses ────────────────────────────────────────────────


class CreateGameResponse(BaseModel):
    game_id: str
    name: str
    status: str


class GameDetailResponse(BaseModel):
    game_id: str
    name: str
    status: str
    config: dict[str, Any] | None
    players: list[GamePlayerInfo]


class AddPlayerResponse(BaseModel):
    game_id: str
    user_id: str
    role: str


class GameTimelineResponse(BaseModel):
    game_id: str
    events: list[TimelineEventInfo]


# ── Characters responses ──────────────────────────────────────────


class CreatePatientResponse(BaseModel):
    patient_id: str
    name: str
    swap_file: dict[str, Any]


class ListCharactersResponse(BaseModel):
    game_id: str
    characters: list[PatientSummary]


class PrintAbilityCreated(BaseModel):
    id: str
    name: str
    color: str


class OriginSnapshot(BaseModel):
    origin_name: str | None
    origin_soul_color: str | None
    origin_identity: str | None
    origin_ideal_projection: str | None
    archive_unlock_state: dict[str, bool]


class CreateGhostResponse(BaseModel):
    ghost_id: str
    name: str
    cmyk: dict[str, int]
    hp: int
    hp_max: int
    print_abilities: list[PrintAbilityCreated]
    origin_snapshot: OriginSnapshot


class PatientBrief(BaseModel):
    id: str
    name: str
    soul_color: str
    gender: str | None = None
    age: int | None = None
    identity: str | None = None
    region_id: str | None = None
    location_id: str | None = None


class PatientFull(BaseModel):
    id: str
    name: str
    soul_color: str
    gender: str | None = None
    age: int | None = None
    identity: str | None = None
    current_region_id: str | None = None
    current_location_id: str | None = None


class GhostDetail(BaseModel):
    id: str
    name: str
    cmyk: dict[str, int]
    hp: int
    hp_max: int
    mp: int
    mp_max: int
    appearance: str | None = None
    personality: str | None = None
    print_abilities: list[PrintAbilityInfo]
    buffs: list[BuffInfo]
    origin_data: dict[str, Any]


class ActiveCharacterResponse(BaseModel):
    patient: PatientBrief
    ghost: GhostDetail | None = None


class PatientDetailResponse(BaseModel):
    patient: PatientFull
    ghost: GhostDetail | None = None


class SwitchCharacterResponse(BaseModel):
    active_patient_id: str


class UnlockArchiveResponse(BaseModel):
    color: str
    archive_content: str | None
    archive_unlock_state: dict[str, bool]


class DeletePatientResponse(BaseModel):
    deleted: str


class AssignCompanionResponse(BaseModel):
    ghost_id: str
    current_patient_id: str


class ListAbilitiesResponse(BaseModel):
    ghost_id: str
    abilities: list[PrintAbilityInfo]


class ListBuffsResponse(BaseModel):
    ghost_id: str
    buffs: list[BuffInfo]


# ── Sessions responses ────────────────────────────────────────────


class SessionPlayerInfo(BaseModel):
    patient_id: str
    joined_at: str


class ActiveEventInfo(BaseModel):
    id: str
    name: str
    expression: str
    color_restriction: str | None


class SessionInfoResponse(BaseModel):
    session_id: str
    game_id: str
    status: str
    region_id: str | None
    location_id: str | None
    started_at: str | None
    ended_at: str | None
    players: list[SessionPlayerInfo]
    active_events: list[ActiveEventInfo]


class SessionStatusResponse(BaseModel):
    session_id: str
    status: str


class AddSessionPlayerResponse(BaseModel):
    session_id: str
    patient_id: str


class RemoveSessionPlayerResponse(BaseModel):
    removed: str


class EventDefinitionInfo(BaseModel):
    id: str
    name: str
    expression: str
    color_restriction: str | None
    target_roll_total: int | None


class ListEventDefinitionsResponse(BaseModel):
    session_id: str
    events: list[EventDefinitionInfo]


class SessionTimelineResponse(BaseModel):
    session_id: str
    events: list[TimelineEventInfo]


# ── Regions responses ─────────────────────────────────────────────


class CreateRegionResponse(BaseModel):
    region_id: str
    game_id: str
    code: str
    name: str


class RegionInfo(BaseModel):
    id: str
    code: str
    name: str
    description: str | None


class ListRegionsResponse(BaseModel):
    game_id: str
    regions: list[RegionInfo]


class CreateLocationResponse(BaseModel):
    location_id: str
    region_id: str
    name: str


class LocationInfo(BaseModel):
    id: str
    name: str
    description: str | None


class ListLocationsResponse(BaseModel):
    region_id: str
    locations: list[LocationInfo]


class LocationPlayersResponse(BaseModel):
    location_id: str
    players: list[PatientSummary]


# ── Items responses ───────────────────────────────────────────────


class CreateItemDefinitionResponse(BaseModel):
    id: str
    name: str
    item_type: str


class ItemDefinitionInfo(BaseModel):
    id: str
    name: str
    item_type: str
    description: str | None


class ListItemDefinitionsResponse(BaseModel):
    game_id: str
    definitions: list[ItemDefinitionInfo]


class InventoryItemInfo(BaseModel):
    item_def_id: str
    count: int


class ListInventoryResponse(BaseModel):
    patient_id: str
    items: list[InventoryItemInfo]


# ── Communications responses ──────────────────────────────────────


class PendingCommInfo(BaseModel):
    id: str
    initiator_patient_id: str
    target_patient_id: str
    status: str


class ListPendingCommunicationsResponse(BaseModel):
    pending_requests: list[PendingCommInfo]


# ── Misc responses ────────────────────────────────────────────────


class DiceRollResponse(BaseModel):
    expression: str
    individual_rolls: list[int]
    total: int


class RagUploadResponse(BaseModel):
    chunks_indexed: int
    category: str


class HealthResponse(BaseModel):
    status: str
    engine: str
    version: str
