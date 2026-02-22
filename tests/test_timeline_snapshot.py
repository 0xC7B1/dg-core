"""Tests for timeline player snapshot system and text export."""

import json

from sqlalchemy import select

from app.domain.session import timeline
from app.domain.session.export import (
    _extract_content,
    _format_timeline,
    export_session_timeline,
)
from app.domain.session.timeline import create_player_snapshot
from app.models.db_models import (
    Game,
    GamePlayer,
    Ghost,
    Patient,
    User,
)
from app.models.responses import _snapshot_display_name


async def _setup_game_with_player(db, *, role="PL"):
    """Create user, game, GamePlayer, patient, ghost."""
    user = User(username=f"snap_user_{id(db)}")
    db.add(user)
    await db.flush()

    game = Game(name="SnapGame", created_by=user.id, status="active")
    db.add(game)
    await db.flush()

    gp = GamePlayer(game_id=game.id, user_id=user.id, role=role)
    db.add(gp)
    await db.flush()

    patient = Patient(
        user_id=user.id, game_id=game.id, name="TestPatient", soul_color="C",
        gender="M", age=25, identity="Test Identity",
    )
    db.add(patient)
    await db.flush()

    gp.active_patient_id = patient.id

    ghost = Ghost(
        game_id=game.id, name="TestGhost",
        current_patient_id=patient.id,
        cmyk_json='{"C":3,"M":2,"Y":1,"K":0}',
        hp=10, hp_max=10, mp=5, mp_max=5,
    )
    db.add(ghost)
    await db.flush()

    return user, game, gp, patient, ghost


# --- Snapshot creation tests ---


async def test_snapshot_creation(db_session):
    """Snapshot captures all player state fields correctly."""
    db = db_session
    user, game, gp, patient, ghost = await _setup_game_with_player(db)

    snap = await create_player_snapshot(
        db, game.id, user.id, patient=patient, ghost=ghost,
    )

    assert snap.game_id == game.id
    assert snap.user_id == user.id
    assert snap.username == user.username
    assert snap.role == "PL"
    assert snap.patient_id == patient.id
    assert snap.patient_name == "TestPatient"
    assert snap.soul_color == "C"
    assert snap.ghost_id == ghost.id
    assert snap.ghost_name == "TestGhost"
    assert snap.hp == 10
    assert snap.hp_max == 10
    assert snap.mp == 5
    assert snap.mp_max == 5
    assert snap.cmyk_json is not None
    cmyk = json.loads(snap.cmyk_json)
    assert cmyk["C"] == 3
    assert snap.created_at is not None


async def test_snapshot_updates_gameplayer(db_session):
    """create_player_snapshot sets GamePlayer.current_snapshot_id."""
    db = db_session
    user, game, gp, patient, ghost = await _setup_game_with_player(db)

    assert gp.current_snapshot_id is None

    snap = await create_player_snapshot(
        db, game.id, user.id, patient=patient, ghost=ghost,
    )

    # Re-fetch GamePlayer to confirm
    result = await db.execute(
        select(GamePlayer).where(
            GamePlayer.game_id == game.id,
            GamePlayer.user_id == user.id,
        )
    )
    gp_fresh = result.scalar_one()
    assert gp_fresh.current_snapshot_id == snap.id


async def test_append_event_uses_current_snapshot(db_session):
    """append_event attaches the GamePlayer's current snapshot."""
    db = db_session
    user, game, gp, patient, ghost = await _setup_game_with_player(db)

    from app.domain.session.service import start_session

    session = await start_session(db, game.id, user.id)

    # Create a snapshot first
    snap = await create_player_snapshot(
        db, game.id, user.id, patient=patient, ghost=ghost,
    )

    # Append event — should use the current snapshot
    event = await timeline.append_event(
        db, session_id=session.id, game_id=game.id,
        event_type="test_event", user_id=user.id,
    )

    assert event.player_snapshot_id == snap.id


async def test_append_event_lazy_init(db_session):
    """First event from a player auto-creates an initial snapshot."""
    db = db_session
    user, game, gp, patient, ghost = await _setup_game_with_player(db)

    from app.domain.session.service import start_session

    session = await start_session(db, game.id, user.id)

    assert gp.current_snapshot_id is None

    event = await timeline.append_event(
        db, session_id=session.id, game_id=game.id,
        event_type="test_event", user_id=user.id,
    )

    # Should have auto-created a snapshot
    assert event.player_snapshot_id is not None

    # GamePlayer should now have current_snapshot_id set
    result = await db.execute(
        select(GamePlayer).where(
            GamePlayer.game_id == game.id,
            GamePlayer.user_id == user.id,
        )
    )
    gp_fresh = result.scalar_one()
    assert gp_fresh.current_snapshot_id == event.player_snapshot_id


async def test_no_snapshot_without_user(db_session):
    """System events (no user_id) have null snapshot."""
    db = db_session
    user, game, gp, patient, ghost = await _setup_game_with_player(db)

    from app.domain.session.service import start_session

    session = await start_session(db, game.id, user.id)

    event = await timeline.append_event(
        db, session_id=session.id, game_id=game.id,
        event_type="system_event",
    )

    assert event.player_snapshot_id is None


async def test_multiple_events_same_snapshot(db_session):
    """Consecutive non-state-changing events share the same snapshot ID."""
    db = db_session
    user, game, gp, patient, ghost = await _setup_game_with_player(db)

    from app.domain.session.service import start_session

    session = await start_session(db, game.id, user.id)

    # Create initial snapshot
    snap = await create_player_snapshot(
        db, game.id, user.id, patient=patient, ghost=ghost,
    )

    # Append two events without creating a new snapshot
    e1 = await timeline.append_event(
        db, session_id=session.id, game_id=game.id,
        event_type="event_a", user_id=user.id,
    )
    e2 = await timeline.append_event(
        db, session_id=session.id, game_id=game.id,
        event_type="event_b", user_id=user.id,
    )

    assert e1.player_snapshot_id == snap.id
    assert e2.player_snapshot_id == snap.id


async def test_state_change_creates_new_snapshot(db_session):
    """After create_player_snapshot, new events use the new snapshot."""
    db = db_session
    user, game, gp, patient, ghost = await _setup_game_with_player(db)

    from app.domain.session.service import start_session

    session = await start_session(db, game.id, user.id)

    snap1 = await create_player_snapshot(
        db, game.id, user.id, patient=patient, ghost=ghost,
    )
    e1 = await timeline.append_event(
        db, session_id=session.id, game_id=game.id,
        event_type="before_change", user_id=user.id,
    )

    # Simulate state change + new snapshot
    ghost.hp = 7
    snap2 = await create_player_snapshot(
        db, game.id, user.id, patient=patient, ghost=ghost,
    )
    e2 = await timeline.append_event(
        db, session_id=session.id, game_id=game.id,
        event_type="after_change", user_id=user.id,
    )

    assert snap1.id != snap2.id
    assert e1.player_snapshot_id == snap1.id
    assert e2.player_snapshot_id == snap2.id
    assert snap2.hp == 7


async def test_dm_snapshot_with_character(db_session):
    """DM with active patient captures full state."""
    db = db_session
    user, game, gp, patient, ghost = await _setup_game_with_player(db, role="DM")

    snap = await create_player_snapshot(
        db, game.id, user.id, patient=patient, ghost=ghost,
    )

    assert snap.role == "DM"
    assert snap.patient_name == "TestPatient"
    assert snap.ghost_name == "TestGhost"
    assert snap.hp == 10


async def test_dm_snapshot_without_character(db_session):
    """DM without patient has null patient/ghost fields."""
    db = db_session
    user = User(username="dm_no_char")
    db.add(user)
    await db.flush()

    game = Game(name="DMGame", created_by=user.id, status="active")
    db.add(game)
    await db.flush()

    gp = GamePlayer(game_id=game.id, user_id=user.id, role="DM")
    db.add(gp)
    await db.flush()

    snap = await create_player_snapshot(db, game.id, user.id)

    assert snap.role == "DM"
    assert snap.patient_id is None
    assert snap.ghost_id is None
    assert snap.hp is None


# --- Display name tests ---


def test_display_name_pl():
    """PL with patient+ghost shows [患者]name/[幽灵]name."""
    name = _snapshot_display_name("user1", "PL", "卡尔森", "异端")
    assert name == "[患者]卡尔森/[幽灵]异端"


def test_display_name_dm():
    """DM always shows username."""
    name = _snapshot_display_name("Olivia", "DM", "SomePatient", "SomeGhost")
    assert name == "Olivia"


def test_display_name_pl_no_ghost():
    """PL with only patient shows [患者]name."""
    name = _snapshot_display_name("user1", "PL", "卡尔森", None)
    assert name == "[患者]卡尔森"


def test_display_name_pl_no_character():
    """PL without patient/ghost falls back to username."""
    name = _snapshot_display_name("user1", "PL", None, None)
    assert name == "user1"


# --- Export tests ---


async def test_export_no_events(db_session):
    """Export with no events returns placeholder text."""
    db = db_session
    user, game, gp, patient, ghost = await _setup_game_with_player(db)

    from app.domain.session.service import start_session

    session = await start_session(db, game.id, user.id)
    text = await export_session_timeline(db, session.id)

    assert "灰山城系统自动生成" in text
    assert "无事件记录" in text


async def test_export_header(db_session):
    """Export header contains time range and participants."""
    db = db_session
    user, game, gp, patient, ghost = await _setup_game_with_player(db)

    from app.domain.session.service import start_session

    session = await start_session(db, game.id, user.id)

    await create_player_snapshot(
        db, game.id, user.id, patient=patient, ghost=ghost,
    )
    await timeline.append_event(
        db, session_id=session.id, game_id=game.id,
        event_type="event_check", user_id=user.id,
        data={"event_name": "test"},
        result_data={"player_total": 15, "target_total": 12, "success": True},
    )

    text = await export_session_timeline(db, session.id)

    assert "灰山城系统自动生成" in text
    assert "记录时段" in text
    assert "参与信号" in text
    assert "总消息数：1" in text


async def test_export_event_content(db_session):
    """Export formats event content based on event type."""
    db = db_session
    user, game, gp, patient, ghost = await _setup_game_with_player(db)

    from app.domain.session.service import start_session

    session = await start_session(db, game.id, user.id)

    await create_player_snapshot(
        db, game.id, user.id, patient=patient, ghost=ghost,
    )
    await timeline.append_event(
        db, session_id=session.id, game_id=game.id,
        event_type="event_check", user_id=user.id,
        data={"event_name": "trap"},
        result_data={"player_total": 15, "target_total": 12, "success": True},
    )

    text = await export_session_timeline(db, session.id)

    assert "[事件判定]" in text
    assert "判定成功" in text
    assert "15" in text
    assert "12" in text


def test_extract_content_event_check():
    """_extract_content formats event_check correctly."""
    from types import SimpleNamespace

    event = SimpleNamespace(
        event_type="event_check",
        data_json=json.dumps({"event_name": "trap"}),
        result_json=json.dumps({"player_total": 15, "target_total": 12, "success": True}),
        narrative=None,
    )
    content = _extract_content(event)
    assert "判定成功" in content
    assert "15" in content


def test_extract_content_attack_hit():
    """_extract_content formats attack hit correctly."""
    from types import SimpleNamespace

    event = SimpleNamespace(
        event_type="attack",
        data_json=json.dumps({}),
        result_json=json.dumps({"success": True, "damage": 3}),
        narrative=None,
    )
    content = _extract_content(event)
    assert "命中" in content
    assert "3" in content


def test_extract_content_with_narrative():
    """_extract_content prefers narrative when available."""
    from types import SimpleNamespace

    event = SimpleNamespace(
        event_type="event_check",
        data_json=json.dumps({}),
        result_json=json.dumps({}),
        narrative="A dramatic roll!",
    )
    content = _extract_content(event)
    assert content == "A dramatic roll!"


def test_format_timeline_empty():
    """_format_timeline with empty list shows placeholder."""
    text = _format_timeline([])
    assert "无事件记录" in text


# --- API endpoint tests ---


async def test_export_api_endpoint(client):
    """GET /api/sessions/{id}/timeline/export returns PlainTextResponse."""
    from tests.conftest import register_user

    user = await register_user(client, username="export_user", platform_uid="exp001")
    h = user["headers"]

    # Create game
    resp = await client.post("/api/games", json={"name": "ExportGame"}, headers=h)
    game_id = resp.json()["game_id"]

    # Start session via events API
    resp = await client.post("/api/events", json={
        "game_id": game_id,
        "user_id": user["user_id"],
        "event_type": "session_start",
        "payload": {"event_type": "session_start", "region_id": None, "location_id": None},
    }, headers=h)
    assert resp.status_code == 200
    session_id = resp.json()["data"]["session_id"]

    # Export timeline
    resp = await client.get(
        f"/api/sessions/{session_id}/timeline/export", headers=h,
    )
    assert resp.status_code == 200
    assert "text/plain" in resp.headers["content-type"]
    assert "灰山城系统自动生成" in resp.text


async def test_game_export_api_endpoint(client):
    """GET /api/games/{id}/timeline/export returns PlainTextResponse."""
    from tests.conftest import register_user

    user = await register_user(client, username="gexport_user", platform_uid="gexp001")
    h = user["headers"]

    resp = await client.post("/api/games", json={"name": "GExportGame"}, headers=h)
    game_id = resp.json()["game_id"]

    resp = await client.get(
        f"/api/games/{game_id}/timeline/export", headers=h,
    )
    assert resp.status_code == 200
    assert "text/plain" in resp.headers["content-type"]
