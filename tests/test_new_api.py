"""Tests for new resource-based API endpoints (Phase 4 dual routing)."""

from tests.conftest import register_user


# --- Games ---

async def test_new_create_game(client):
    user = await register_user(client)
    resp = await client.post("/api/games", json={"name": "NewGame"}, headers=user["headers"])
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "NewGame"
    assert "game_id" in data


async def test_new_get_game(client):
    user = await register_user(client)
    create = await client.post("/api/games", json={"name": "G1"}, headers=user["headers"])
    gid = create.json()["game_id"]

    resp = await client.get(f"/api/games/{gid}", headers=user["headers"])
    assert resp.status_code == 200
    assert resp.json()["name"] == "G1"


# --- Events ---

async def test_new_events_endpoint(client):
    user = await register_user(client)
    create = await client.post("/api/games", json={"name": "EvtGame"}, headers=user["headers"])
    gid = create.json()["game_id"]

    resp = await client.post("/api/events", json={
        "game_id": gid,
        "user_id": user["user_id"],
        "payload": {"event_type": "game_start"},
    }, headers=user["headers"])
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["event_type"] == "game_start"


# --- Sessions ---

async def test_new_session_info(client):
    user = await register_user(client)
    create = await client.post("/api/games", json={"name": "SG"}, headers=user["headers"])
    gid = create.json()["game_id"]

    # Start game + session via new events endpoint
    await client.post("/api/events", json={
        "game_id": gid, "user_id": user["user_id"],
        "payload": {"event_type": "game_start"},
    }, headers=user["headers"])

    sess_resp = await client.post("/api/events", json={
        "game_id": gid, "user_id": user["user_id"],
        "payload": {"event_type": "session_start"},
    }, headers=user["headers"])
    sid = sess_resp.json()["data"]["session_id"]

    resp = await client.get(f"/api/sessions/{sid}", headers=user["headers"])
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"


# --- Dice ---

async def test_new_dice_roll(client):
    user = await register_user(client)
    resp = await client.post("/api/dice/roll", json={
        "expression": "2d6",
    }, headers=user["headers"])
    assert resp.status_code == 200
    data = resp.json()
    assert "total" in data
    assert len(data["individual_rolls"]) == 2  # 2d6 = 2 dice


# --- DM management via events ---

async def test_dm_buff_add_via_new_events(client):
    user = await register_user(client)
    create = await client.post("/api/games", json={"name": "BG"}, headers=user["headers"])
    gid = create.json()["game_id"]

    # Create patient + ghost via resource-based endpoints
    patient_resp = await client.post(f"/api/games/{gid}/characters/patients", json={
        "user_id": user["user_id"],
        "name": "TestP",
        "soul_color": "C",
    }, headers=user["headers"])
    pid = patient_resp.json()["patient_id"]

    ghost_resp = await client.post(f"/api/games/{gid}/characters/ghosts", json={
        "origin_patient_id": pid,
        "creator_user_id": user["user_id"],
        "name": "TestG",
        "soul_color": "C",
    }, headers=user["headers"])
    ghost_id = ghost_resp.json()["ghost_id"]

    # Add buff via new events endpoint
    resp = await client.post("/api/events", json={
        "game_id": gid,
        "user_id": user["user_id"],
        "payload": {
            "event_type": "buff_add",
            "ghost_id": ghost_id,
            "name": "Shield",
            "expression": "+2",
        },
    }, headers=user["headers"])
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["event_type"] == "buff_add"
    assert data["data"]["name"] == "Shield"
