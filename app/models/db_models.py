"""SQLAlchemy ORM models for dg-core."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# Naming convention for constraints — required for Alembic batch mode (SQLite)
convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def _uuid() -> str:
    return uuid.uuid4().hex


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=convention)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    username: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    email: Mapped[str | None] = mapped_column(String(256), nullable=True, unique=True)
    api_key_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    role: Mapped[str] = mapped_column(String(16), default="user")  # "user", "admin"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    platform_bindings: Mapped[list[PlatformBinding]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    game_links: Mapped[list[GamePlayer]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    patients: Mapped[list[Patient]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    def __str__(self) -> str:
        return f"{self.username} ({self.id[:8]})"


class PlatformBinding(Base):
    """Links a User to an external platform identity (QQ, Discord, web, etc.)."""

    __tablename__ = "platform_bindings"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    platform: Mapped[str] = mapped_column(String(32), nullable=False)  # "qq", "discord", "web"
    platform_uid: Mapped[str] = mapped_column(String(128), nullable=False)
    bound_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    user: Mapped[User] = relationship(back_populates="platform_bindings")

    def __str__(self) -> str:
        return f"{self.platform}:{self.platform_uid}"

    __table_args__ = (
        Index("ix_binding_platform", "platform", "platform_uid", unique=True),
        Index("ix_binding_user", "user_id"),
    )


class Game(Base):
    """A complete game instance — top-level container for regions, characters, sessions."""

    __tablename__ = "games"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(
        Enum("preparing", "active", "paused", "ended", name="game_status"),
        default="preparing",
    )
    config_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    flags_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    creator: Mapped[User | None] = relationship(foreign_keys=[created_by])
    user_links: Mapped[list[GamePlayer]] = relationship(
        back_populates="game", cascade="all, delete-orphan"
    )
    regions: Mapped[list[Region]] = relationship(
        back_populates="game", cascade="all, delete-orphan"
    )
    patients: Mapped[list[Patient]] = relationship(
        back_populates="game", cascade="all, delete-orphan"
    )
    ghosts: Mapped[list[Ghost]] = relationship(
        back_populates="game", cascade="all, delete-orphan"
    )
    sessions: Mapped[list[Session]] = relationship(
        back_populates="game", cascade="all, delete-orphan"
    )
    item_definitions: Mapped[list[ItemDefinition]] = relationship(
        back_populates="game", cascade="all, delete-orphan"
    )
    communication_requests: Mapped[list[CommunicationRequest]] = relationship(
        back_populates="game", cascade="all, delete-orphan"
    )

    def __str__(self) -> str:
        return self.name


class GamePlayer(Base):
    """Player participation in a game — role and active character tracking."""

    __tablename__ = "game_players"

    game_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("games.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str] = mapped_column(
        Enum("DM", "PL", name="player_role"), nullable=False
    )
    active_patient_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("patients.id", ondelete="SET NULL"), nullable=True
    )
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    game: Mapped[Game] = relationship(back_populates="user_links")
    user: Mapped[User] = relationship(back_populates="game_links")
    active_patient: Mapped[Patient | None] = relationship(foreign_keys=[active_patient_id])

    def __str__(self) -> str:
        return f"{self.role} ({self.user_id[:8]} in {self.game_id[:8]})"


class Region(Base):
    """A geographical area within a game (e.g., A/B/C/D districts)."""

    __tablename__ = "regions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    game_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("games.id", ondelete="CASCADE")
    )
    code: Mapped[str] = mapped_column(String(8), nullable=False)  # "A", "B", "C", "D"
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    game: Mapped[Game] = relationship(back_populates="regions")
    locations: Mapped[list[Location]] = relationship(
        back_populates="region", cascade="all, delete-orphan"
    )

    def __str__(self) -> str:
        return f"{self.code} - {self.name}"

    __table_args__ = (
        Index("ix_region_game", "game_id"),
        Index("ix_region_game_code", "game_id", "code", unique=True),
    )


class Location(Base):
    """A specific place within a region (e.g., data ruins, signal tower)."""

    __tablename__ = "locations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    region_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("regions.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)  # Rich text for RAG indexing
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    region: Mapped[Region] = relationship(back_populates="locations")

    def __str__(self) -> str:
        return self.name

    __table_args__ = (
        Index("ix_location_region", "region_id"),
    )


class Patient(Base):
    __tablename__ = "patients"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="CASCADE")
    )
    game_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("games.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    gender: Mapped[str | None] = mapped_column(String(16), nullable=True)
    age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    identity: Mapped[str | None] = mapped_column(String(128), nullable=True)
    portrait_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    soul_color: Mapped[str] = mapped_column(String(1), nullable=False)  # C/M/Y/K
    personality_archives_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    ideal_projection: Mapped[str | None] = mapped_column(Text, nullable=True)
    current_region_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("regions.id", ondelete="SET NULL"), nullable=True
    )
    current_location_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("locations.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    user: Mapped[User] = relationship(back_populates="patients")
    game: Mapped[Game] = relationship(back_populates="patients")
    current_region: Mapped[Region | None] = relationship(
        foreign_keys=[current_region_id]
    )
    current_location: Mapped[Location | None] = relationship(
        foreign_keys=[current_location_id]
    )
    ghost: Mapped[Ghost | None] = relationship(
        foreign_keys="[Ghost.current_patient_id]", back_populates="current_patient", uselist=False
    )
    origin_ghost: Mapped[Ghost | None] = relationship(
        foreign_keys="[Ghost.origin_patient_id]", back_populates="origin_patient", uselist=False
    )
    # Cascade-owned children
    player_items: Mapped[list[PlayerItem]] = relationship(
        back_populates="patient", cascade="all, delete-orphan"
    )
    session_links: Mapped[list[SessionPlayer]] = relationship(
        back_populates="patient", cascade="all"
    )
    initiated_comms: Mapped[list[CommunicationRequest]] = relationship(
        foreign_keys="[CommunicationRequest.initiator_patient_id]",
        back_populates="initiator_patient", cascade="all",
    )
    received_comms: Mapped[list[CommunicationRequest]] = relationship(
        foreign_keys="[CommunicationRequest.target_patient_id]",
        back_populates="target_patient", cascade="all",
    )

    def __str__(self) -> str:
        return f"{self.name} ({self.soul_color})"

    __table_args__ = (
        Index("ix_patient_game", "game_id"),
    )


class Ghost(Base):
    __tablename__ = "ghosts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    current_patient_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("patients.id", ondelete="SET NULL"),
        unique=True, nullable=True,
    )
    origin_patient_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("patients.id", ondelete="SET NULL"),
        unique=True, nullable=True,
    )
    creator_user_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    game_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("games.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    appearance: Mapped[str | None] = mapped_column(Text, nullable=True)
    personality: Mapped[str | None] = mapped_column(Text, nullable=True)
    cmyk_json: Mapped[str] = mapped_column(Text, nullable=False)  # {"C":1,"M":0,"Y":0,"K":0}
    hp: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    hp_max: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    mp: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    mp_max: Mapped[int] = mapped_column(Integer, nullable=False, default=5)

    # --- Origin patient data snapshot (immutable after creation) ---
    origin_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    origin_identity: Mapped[str | None] = mapped_column(String(128), nullable=True)
    origin_soul_color: Mapped[str | None] = mapped_column(String(1), nullable=True)
    origin_ideal_projection: Mapped[str | None] = mapped_column(Text, nullable=True)
    origin_archives_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Unlock state ---
    archive_unlock_json: Mapped[str] = mapped_column(
        Text, nullable=False, default='{"C":false,"M":false,"Y":false,"K":false}'
    )
    origin_name_unlocked: Mapped[bool] = mapped_column(Boolean, default=False)
    origin_identity_unlocked: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    current_patient: Mapped[Patient | None] = relationship(
        foreign_keys=[current_patient_id], back_populates="ghost"
    )
    origin_patient: Mapped[Patient | None] = relationship(
        foreign_keys=[origin_patient_id], back_populates="origin_ghost"
    )
    creator_user: Mapped[User | None] = relationship(foreign_keys=[creator_user_id])
    game: Mapped[Game] = relationship(back_populates="ghosts")
    print_abilities: Mapped[list[PrintAbility]] = relationship(
        back_populates="ghost", cascade="all, delete-orphan"
    )
    color_fragments: Mapped[list[ColorFragment]] = relationship(
        back_populates="holder_ghost", cascade="all, delete-orphan"
    )
    buffs: Mapped[list[Buff]] = relationship(
        back_populates="ghost", cascade="all, delete-orphan"
    )
    event_ability_usages: Mapped[list[EventAbilityUsage]] = relationship(
        back_populates="ghost", cascade="all",
    )

    def __str__(self) -> str:
        return self.name

    __table_args__ = (
        Index("ix_ghost_game", "game_id"),
    )


class PrintAbility(Base):
    __tablename__ = "print_abilities"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    ghost_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("ghosts.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    color: Mapped[str] = mapped_column(String(1), nullable=False)  # C/M/Y/K
    ability_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    ghost: Mapped[Ghost] = relationship(back_populates="print_abilities")
    ability_usages: Mapped[list[EventAbilityUsage]] = relationship(
        back_populates="ability", cascade="all",
    )

    def __str__(self) -> str:
        return f"{self.name} ({self.color})"


class Session(Base):
    """A single play session — from /session start to /session end."""

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    game_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("games.id", ondelete="CASCADE")
    )
    region_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("regions.id", ondelete="SET NULL"), nullable=True
    )
    location_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("locations.id", ondelete="SET NULL"), nullable=True
    )
    started_by: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        Enum("active", "paused", "ended", name="session_status"),
        default="active",
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    game: Mapped[Game] = relationship(back_populates="sessions")
    region: Mapped[Region | None] = relationship(foreign_keys=[region_id])
    location: Mapped[Location | None] = relationship(foreign_keys=[location_id])
    started_by_user: Mapped[User | None] = relationship(foreign_keys=[started_by])
    timeline_events: Mapped[list[TimelineEvent]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    session_players: Mapped[list[SessionPlayer]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    event_definitions: Mapped[list[EventDefinition]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )

    def __str__(self) -> str:
        return f"Session {self.id[:8]} ({self.status})"

    __table_args__ = (
        Index("ix_session_game", "game_id"),
    )


class TimelineEvent(Base):
    __tablename__ = "timeline_events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("sessions.id", ondelete="CASCADE")
    )
    game_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("games.id", ondelete="CASCADE")
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    data_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    narrative: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    session: Mapped[Session] = relationship(back_populates="timeline_events")
    game: Mapped[Game] = relationship()

    def __str__(self) -> str:
        return f"#{self.seq} {self.event_type}"

    __table_args__ = (
        Index("ix_timeline_session_seq", "session_id", "seq"),
        Index("ix_timeline_game", "game_id"),
    )


class ColorFragment(Base):
    __tablename__ = "color_fragments"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    game_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("games.id", ondelete="CASCADE")
    )
    holder_ghost_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("ghosts.id", ondelete="CASCADE")
    )
    color: Mapped[str] = mapped_column(String(1), nullable=False)  # C/M/Y/K
    value: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    redeemed: Mapped[bool] = mapped_column(Boolean, default=False)
    redeemed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    holder_ghost: Mapped[Ghost] = relationship(back_populates="color_fragments")
    game: Mapped[Game] = relationship()

    def __str__(self) -> str:
        return f"{self.color} ({self.value})"

    __table_args__ = (
        Index("ix_fragment_game", "game_id"),
    )


# --- New models for refactored game features ---


class SessionPlayer(Base):
    """Tracks which patients are participating in a session."""

    __tablename__ = "session_players"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("sessions.id", ondelete="CASCADE")
    )
    patient_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("patients.id", ondelete="CASCADE")
    )
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    session: Mapped[Session] = relationship(back_populates="session_players")
    patient: Mapped[Patient] = relationship(back_populates="session_links")

    def __str__(self) -> str:
        return f"SessionPlayer({self.patient_id[:8]} in {self.session_id[:8]})"

    __table_args__ = (
        Index("ix_session_player_session", "session_id"),
        Index("ix_session_player_patient", "patient_id"),
        Index("ix_session_player_unique", "session_id", "patient_id", unique=True),
    )


class Buff(Base):
    """Active buff/debuff on a ghost character."""

    __tablename__ = "buffs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    ghost_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("ghosts.id", ondelete="CASCADE")
    )
    game_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("games.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    expression: Mapped[str] = mapped_column(String(128), nullable=False)
    buff_type: Mapped[str] = mapped_column(
        Enum("numeric", "dice", "attribute", "text", name="buff_type"),
        nullable=False,
    )
    remaining_rounds: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    ghost: Mapped[Ghost] = relationship(back_populates="buffs")
    game: Mapped[Game] = relationship()

    def __str__(self) -> str:
        return f"{self.name} ({self.expression})"

    __table_args__ = (
        Index("ix_buff_ghost", "ghost_id"),
        Index("ix_buff_game", "game_id"),
    )


class EventDefinition(Base):
    """A DM-defined event check target, scoped to a session."""

    __tablename__ = "event_definitions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("sessions.id", ondelete="CASCADE")
    )
    game_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("games.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    expression: Mapped[str] = mapped_column(String(128), nullable=False)
    color_restriction: Mapped[str | None] = mapped_column(String(1), nullable=True)
    target_roll_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_roll_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    session: Mapped[Session] = relationship(back_populates="event_definitions")
    game: Mapped[Game] = relationship()
    ability_usages: Mapped[list[EventAbilityUsage]] = relationship(
        back_populates="event_definition", cascade="all, delete-orphan"
    )

    def __str__(self) -> str:
        return f"Event: {self.name} ({self.expression})"

    __table_args__ = (
        Index("ix_event_def_session", "session_id"),
        Index("ix_event_def_name", "session_id", "name"),
    )


class EventAbilityUsage(Base):
    """Tracks which abilities have been used in a specific event check."""

    __tablename__ = "event_ability_usages"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    event_def_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("event_definitions.id", ondelete="CASCADE")
    )
    ghost_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("ghosts.id", ondelete="CASCADE")
    )
    ability_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("print_abilities.id", ondelete="CASCADE")
    )
    used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    event_definition: Mapped[EventDefinition] = relationship(back_populates="ability_usages")
    ghost: Mapped[Ghost] = relationship(back_populates="event_ability_usages")
    ability: Mapped[PrintAbility] = relationship(back_populates="ability_usages")

    def __str__(self) -> str:
        return f"Usage({self.ability_id[:8]} in event {self.event_def_id[:8]})"

    __table_args__ = (
        Index("ix_event_usage_event_ghost", "event_def_id", "ghost_id"),
        Index(
            "ix_event_usage_unique",
            "event_def_id",
            "ghost_id",
            "ability_id",
            unique=True,
        ),
    )


class CommunicationRequest(Base):
    """A pending/completed communication request between two players."""

    __tablename__ = "communication_requests"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    game_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("games.id", ondelete="CASCADE")
    )
    initiator_patient_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("patients.id", ondelete="CASCADE")
    )
    target_patient_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("patients.id", ondelete="CASCADE")
    )
    status: Mapped[str] = mapped_column(
        Enum("pending", "accepted", "rejected", "cancelled", name="comm_status"),
        default="pending",
    )
    transferred_ability_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("print_abilities.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    game: Mapped[Game] = relationship(back_populates="communication_requests")
    initiator_patient: Mapped[Patient] = relationship(
        foreign_keys=[initiator_patient_id], back_populates="initiated_comms"
    )
    target_patient: Mapped[Patient] = relationship(
        foreign_keys=[target_patient_id], back_populates="received_comms"
    )

    def __str__(self) -> str:
        return f"Comm({self.status})"

    __table_args__ = (
        Index("ix_comm_game", "game_id"),
        Index("ix_comm_initiator", "initiator_patient_id"),
        Index("ix_comm_target", "target_patient_id"),
        Index("ix_comm_status", "game_id", "status"),
    )


class ItemDefinition(Base):
    """Game-scoped item template."""

    __tablename__ = "item_definitions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    game_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("games.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    item_type: Mapped[str] = mapped_column(String(32), nullable=False, default="generic")
    effect_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    stackable: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    game: Mapped[Game] = relationship(back_populates="item_definitions")
    player_items: Mapped[list[PlayerItem]] = relationship(
        back_populates="item_definition", cascade="all, delete-orphan"
    )

    def __str__(self) -> str:
        return self.name

    __table_args__ = (
        Index("ix_item_def_game", "game_id"),
        Index("ix_item_def_name", "game_id", "name"),
    )


class PlayerItem(Base):
    """An item in a patient's inventory."""

    __tablename__ = "player_items"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    patient_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("patients.id", ondelete="CASCADE")
    )
    item_def_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("item_definitions.id", ondelete="CASCADE")
    )
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    patient: Mapped[Patient] = relationship(back_populates="player_items")
    item_definition: Mapped[ItemDefinition] = relationship(back_populates="player_items")

    def __str__(self) -> str:
        return f"Item x{self.count}"

    __table_args__ = (
        Index("ix_player_item_patient", "patient_id"),
        Index("ix_player_item_unique", "patient_id", "item_def_id", unique=True),
    )
