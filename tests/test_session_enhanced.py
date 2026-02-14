"""Tests for enhanced session management (pause/resume, player management)."""

import pytest

from app.domain import session as session_mod
from app.models.db_models import Game, GamePlayer, Location, Patient, Region, User


async def _setup_game(db):
    """Helper: create a user and game for session tests."""
    user = User(username=f"ses_user_{id(db)}")
    db.add(user)
    await db.flush()

    game = Game(name="SesGame", created_by=user.id, status="active")
    db.add(game)
    await db.flush()

    gp = GamePlayer(game_id=game.id, user_id=user.id, role="DM")
    db.add(gp)
    await db.flush()

    return user, game


@pytest.mark.asyncio
async def test_pause_and_resume_session(db_session):
    db = db_session
    user, game = await _setup_game(db)

    session = await session_mod.start_session(db, game.id, user.id)
    assert session.status == "active"

    paused = await session_mod.pause_session(db, session.id)
    assert paused.status == "paused"

    resumed = await session_mod.resume_session(db, session.id)
    assert resumed.status == "active"


@pytest.mark.asyncio
async def test_pause_non_active_session_fails(db_session):
    db = db_session
    user, game = await _setup_game(db)

    session = await session_mod.start_session(db, game.id, user.id)
    await session_mod.end_session(db, session.id)

    with pytest.raises(ValueError, match="Cannot pause"):
        await session_mod.pause_session(db, session.id)


@pytest.mark.asyncio
async def test_resume_non_paused_session_fails(db_session):
    db = db_session
    user, game = await _setup_game(db)

    session = await session_mod.start_session(db, game.id, user.id)

    with pytest.raises(ValueError, match="Cannot resume"):
        await session_mod.resume_session(db, session.id)


@pytest.mark.asyncio
async def test_add_and_remove_player_from_session(db_session):
    db = db_session
    user, game = await _setup_game(db)

    patient = Patient(
        user_id=user.id, game_id=game.id, name="SesPatient", soul_color="C"
    )
    db.add(patient)
    await db.flush()

    session = await session_mod.start_session(db, game.id, user.id)

    sp = await session_mod.add_player_to_session(db, session.id, patient.id)
    assert sp.patient_id == patient.id

    players = await session_mod.get_session_players(db, session.id)
    assert len(players) == 1

    await session_mod.remove_player_from_session(db, session.id, patient.id)

    players = await session_mod.get_session_players(db, session.id)
    assert len(players) == 0


@pytest.mark.asyncio
async def test_add_duplicate_player_fails(db_session):
    db = db_session
    user, game = await _setup_game(db)

    patient = Patient(
        user_id=user.id, game_id=game.id, name="DupP", soul_color="M"
    )
    db.add(patient)
    await db.flush()

    session = await session_mod.start_session(db, game.id, user.id)
    await session_mod.add_player_to_session(db, session.id, patient.id)

    with pytest.raises(ValueError, match="already in this session"):
        await session_mod.add_player_to_session(db, session.id, patient.id)


@pytest.mark.asyncio
async def test_auto_join_location_players(db_session):
    db = db_session
    user, game = await _setup_game(db)

    region = Region(game_id=game.id, code="A", name="TestRegion")
    db.add(region)
    await db.flush()

    # Create a patient at this region
    patient = Patient(
        user_id=user.id, game_id=game.id, name="AutoJoinP", soul_color="Y",
        current_region_id=region.id,
    )
    db.add(patient)
    await db.flush()

    # Start session at the same region — should auto-join
    session = await session_mod.start_session(
        db, game.id, user.id, region_id=region.id
    )

    players = await session_mod.get_session_players(db, session.id)
    assert len(players) == 1
    assert players[0].patient_id == patient.id


@pytest.mark.asyncio
async def test_get_session_info(db_session):
    db = db_session
    user, game = await _setup_game(db)

    session = await session_mod.start_session(db, game.id, user.id)
    info = await session_mod.get_session_info(db, session.id)

    assert info["session_id"] == session.id
    assert info["status"] == "active"
    assert isinstance(info["players"], list)
    assert isinstance(info["active_events"], list)


# --- Duplicate session prevention tests ---


async def _setup_game_with_location(db):
    """Helper: create user, game, region, and location."""
    user, game = await _setup_game(db)

    region = Region(game_id=game.id, code="A", name="RegionA")
    db.add(region)
    await db.flush()

    location = Location(region_id=region.id, name="LocationA1")
    db.add(location)
    await db.flush()

    return user, game, region, location


@pytest.mark.asyncio
async def test_duplicate_session_at_same_location_fails(db_session):
    """Starting two sessions at the same location should raise."""
    db = db_session
    user, game, region, location = await _setup_game_with_location(db)

    await session_mod.start_session(
        db, game.id, user.id, region_id=region.id, location_id=location.id
    )

    with pytest.raises(ValueError, match="active session already exists at location"):
        await session_mod.start_session(
            db, game.id, user.id, region_id=region.id, location_id=location.id
        )


@pytest.mark.asyncio
async def test_duplicate_session_at_same_region_fails(db_session):
    """Starting two region-level sessions at the same region should raise."""
    db = db_session
    user, game, region, _location = await _setup_game_with_location(db)

    await session_mod.start_session(db, game.id, user.id, region_id=region.id)

    with pytest.raises(ValueError, match="active session already exists at region"):
        await session_mod.start_session(db, game.id, user.id, region_id=region.id)


@pytest.mark.asyncio
async def test_sessions_at_different_locations_allowed(db_session):
    """Sessions at different locations should not conflict."""
    db = db_session
    user, game, region, loc1 = await _setup_game_with_location(db)

    loc2 = Location(region_id=region.id, name="LocationA2")
    db.add(loc2)
    await db.flush()

    s1 = await session_mod.start_session(
        db, game.id, user.id, region_id=region.id, location_id=loc1.id
    )
    s2 = await session_mod.start_session(
        db, game.id, user.id, region_id=region.id, location_id=loc2.id
    )
    assert s1.status == "active"
    assert s2.status == "active"
    assert s1.id != s2.id


@pytest.mark.asyncio
async def test_session_at_location_after_previous_ended(db_session):
    """Starting a new session after the previous one ended should succeed."""
    db = db_session
    user, game, region, location = await _setup_game_with_location(db)

    s1 = await session_mod.start_session(
        db, game.id, user.id, region_id=region.id, location_id=location.id
    )
    await session_mod.end_session(db, s1.id)

    s2 = await session_mod.start_session(
        db, game.id, user.id, region_id=region.id, location_id=location.id
    )
    assert s2.status == "active"


@pytest.mark.asyncio
async def test_resume_blocked_when_another_active_at_same_location(db_session):
    """Resuming a paused session should fail if another became active at the same location."""
    db = db_session
    user, game, region, location = await _setup_game_with_location(db)

    s1 = await session_mod.start_session(
        db, game.id, user.id, region_id=region.id, location_id=location.id
    )
    await session_mod.pause_session(db, s1.id)

    # Start a new session at the same location while s1 is paused
    _s2 = await session_mod.start_session(
        db, game.id, user.id, region_id=region.id, location_id=location.id
    )

    with pytest.raises(ValueError, match="active session already exists"):
        await session_mod.resume_session(db, s1.id)


@pytest.mark.asyncio
async def test_resume_allowed_when_no_conflict(db_session):
    """Resuming a paused session should succeed when no conflict exists."""
    db = db_session
    user, game, region, location = await _setup_game_with_location(db)

    s1 = await session_mod.start_session(
        db, game.id, user.id, region_id=region.id, location_id=location.id
    )
    await session_mod.pause_session(db, s1.id)

    resumed = await session_mod.resume_session(db, s1.id)
    assert resumed.status == "active"
