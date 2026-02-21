"""Tests for DM management events dispatched through the new handler registry."""


from app.domain.dispatcher import dispatch
from app.models.db_models import Game, GamePlayer, Ghost, Patient, User
from app.models.event import GameEvent


# --- Helpers ---

async def _setup_game_with_dm(db):
    """Create a game with a DM user and return (user, game, game_player)."""
    user = User(username="dm_user")
    db.add(user)
    await db.flush()

    game = Game(name="Test Game", created_by=user.id)
    db.add(game)
    await db.flush()

    gp = GamePlayer(game_id=game.id, user_id=user.id, role="DM")
    db.add(gp)
    await db.flush()

    return user, game, gp


async def _setup_patient_and_ghost(db, user, game):
    """Create a patient and ghost for testing."""
    patient = Patient(
        game_id=game.id,
        user_id=user.id,
        name="Test Patient",
        soul_color="C",
        gender="M",
        age=25,
    )
    db.add(patient)
    await db.flush()

    ghost = Ghost(
        origin_patient_id=patient.id,
        creator_user_id=user.id,
        game_id=game.id,
        name="Test Ghost",
        cmyk_json='{"C":1,"M":0,"Y":0,"K":0}',
        hp=10,
        hp_max=10,
        mp=5,
        mp_max=5,
        origin_name=patient.name,
        origin_soul_color="C",
        archive_unlock_json='{"C":true,"M":false,"Y":false,"K":false}',
    )
    db.add(ghost)
    await db.flush()

    return patient, ghost


# --- Tests ---

async def test_buff_add_via_dispatcher(db_session):
    db = db_session
    user, game, _ = await _setup_game_with_dm(db)
    _, ghost = await _setup_patient_and_ghost(db, user, game)

    event = GameEvent(
        game_id=game.id,
        user_id=user.id,
        payload={"event_type": "buff_add", "ghost_id": ghost.id, "name": "Shield", "expression": "+2"},
    )
    result = await dispatch(db, event)

    assert result.success is True
    assert result.event_type == "buff_add"
    assert result.data["name"] == "Shield"
    assert result.data["ghost_id"] == ghost.id
    assert "buff_id" in result.data


async def test_buff_remove_via_dispatcher(db_session):
    db = db_session
    user, game, _ = await _setup_game_with_dm(db)
    _, ghost = await _setup_patient_and_ghost(db, user, game)

    # First add a buff
    from app.domain.character import buff as buff_mod
    buff = await buff_mod.add_buff(
        db, ghost_id=ghost.id, game_id=game.id,
        name="TempBuff", expression="+1", remaining_rounds=3, created_by=user.id,
    )

    event = GameEvent(
        game_id=game.id,
        user_id=user.id,
        payload={"event_type": "buff_remove", "buff_id": buff.id},
    )
    result = await dispatch(db, event)

    assert result.success is True
    assert result.event_type == "buff_remove"
    assert result.data["deleted"] == buff.id


async def test_attribute_set_via_dispatcher(db_session):
    db = db_session
    user, game, _ = await _setup_game_with_dm(db)
    _, ghost = await _setup_patient_and_ghost(db, user, game)

    event = GameEvent(
        game_id=game.id,
        user_id=user.id,
        payload={"event_type": "attribute_set", "ghost_id": ghost.id, "attribute": "hp", "value": 20},
    )
    result = await dispatch(db, event)

    assert result.success is True
    assert result.event_type == "attribute_set"
    assert result.data["value"] == 20
    assert ghost.hp == 20


async def test_ability_add_via_dispatcher(db_session):
    db = db_session
    user, game, _ = await _setup_game_with_dm(db)
    _, ghost = await _setup_patient_and_ghost(db, user, game)

    event = GameEvent(
        game_id=game.id,
        user_id=user.id,
        payload={
            "event_type": "ability_add",
            "ghost_id": ghost.id,
            "name": "Fireball",
            "description": "A ball of fire",
            "color": "C",
            "ability_count": 3,
        },
    )
    result = await dispatch(db, event)

    assert result.success is True
    assert result.event_type == "ability_add"
    assert result.data["name"] == "Fireball"
    assert result.data["ability_count"] == 3


async def test_management_requires_dm(db_session):
    """Non-DM players cannot use management events."""
    db = db_session

    dm_user = User(username="dm")
    pl_user = User(username="player")
    db.add_all([dm_user, pl_user])
    await db.flush()

    game = Game(name="Test", created_by=dm_user.id)
    db.add(game)
    await db.flush()

    dm_gp = GamePlayer(game_id=game.id, user_id=dm_user.id, role="DM")
    pl_gp = GamePlayer(game_id=game.id, user_id=pl_user.id, role="PL")
    db.add_all([dm_gp, pl_gp])
    await db.flush()

    patient = Patient(
        game_id=game.id, user_id=dm_user.id,
        name="P", soul_color="C", gender="M", age=20,
    )
    db.add(patient)
    await db.flush()

    ghost = Ghost(
        origin_patient_id=patient.id, creator_user_id=dm_user.id,
        game_id=game.id, name="G",
        cmyk_json='{"C":1,"M":0,"Y":0,"K":0}',
        hp=10, hp_max=10, mp=5, mp_max=5,
        origin_name="P", origin_soul_color="C",
        archive_unlock_json='{"C":true,"M":false,"Y":false,"K":false}',
    )
    db.add(ghost)
    await db.flush()

    # PL tries to add buff → should fail (ValueError caught by dispatcher)
    event = GameEvent(
        game_id=game.id,
        user_id=pl_user.id,
        payload={"event_type": "buff_add", "ghost_id": ghost.id, "name": "X", "expression": "+1"},
    )
    result = await dispatch(db, event)

    assert result.success is False
    assert "DM" in result.error


async def test_event_define_via_dispatcher(db_session):
    db = db_session
    user, game, _ = await _setup_game_with_dm(db)

    from app.domain import session as session_mod
    session = await session_mod.start_session(db, game_id=game.id, started_by=user.id)

    event = GameEvent(
        game_id=game.id,
        session_id=session.id,
        user_id=user.id,
        payload={
            "event_type": "event_define",
            "name": "trap",
            "expression": "3d6",
        },
    )
    result = await dispatch(db, event)

    assert result.success is True
    assert result.event_type == "event_define"
    assert result.data["name"] == "trap"
    assert result.data["is_active"] is True


async def test_event_deactivate_via_dispatcher(db_session):
    db = db_session
    user, game, _ = await _setup_game_with_dm(db)

    from app.domain import session as session_mod
    from app.domain.session import event_def

    session = await session_mod.start_session(db, game_id=game.id, started_by=user.id)

    ed = await event_def.set_event(
        db, session_id=session.id, game_id=game.id,
        name="challenge", expression="2d6", created_by=user.id,
    )

    event = GameEvent(
        game_id=game.id,
        session_id=session.id,
        user_id=user.id,
        payload={"event_type": "event_deactivate", "event_def_id": ed.id},
    )
    result = await dispatch(db, event)

    assert result.success is True
    assert result.event_type == "event_deactivate"
    assert result.data["deactivated"] == ed.id


async def test_item_grant_via_dispatcher(db_session):
    db = db_session
    user, game, _ = await _setup_game_with_dm(db)
    patient, _ = await _setup_patient_and_ghost(db, user, game)

    from app.domain.character import items as items_mod
    item_def = await items_mod.create_item_definition(
        db, game_id=game.id, name="Potion", item_type="consumable",
    )

    event = GameEvent(
        game_id=game.id,
        user_id=user.id,
        payload={
            "event_type": "item_grant",
            "patient_id": patient.id,
            "item_def_id": item_def.id,
            "count": 2,
        },
    )
    result = await dispatch(db, event)

    assert result.success is True
    assert result.event_type == "item_grant"
    assert result.data["count"] == 2
