"""Tests for characters API — covers all endpoints in characters.py and communications.py."""

import pytest
from httpx import AsyncClient

from tests.conftest import register_user


# --- Helpers ---

async def _setup_game_with_player(client: AsyncClient):
    """Create KP (DM), PL, and a game with PL joined."""
    kp = await register_user(client, "KP", "test", "kp_char")
    pl = await register_user(client, "PL", "test", "pl_char")

    game_resp = await client.post("/api/games", json={
        "name": "CharTestGame",
    }, headers=kp["headers"])
    game_id = game_resp.json()["game_id"]

    await client.post(f"/api/games/{game_id}/players", json={
        "user_id": pl["user_id"], "role": "PL",
    }, headers=kp["headers"])

    return kp, pl, game_id


async def _create_patient(client: AsyncClient, headers: dict, user_id: str, game_id: str, name: str = "测试患者"):
    """Create a patient and return patient_id."""
    resp = await client.post(f"/api/games/{game_id}/characters/patients", json={
        "user_id": user_id, "name": name, "soul_color": "C",
    }, headers=headers)
    assert resp.status_code == 200
    return resp.json()["patient_id"]


async def _create_ghost(client: AsyncClient, headers: dict, game_id: str, patient_id: str, creator_user_id: str, name: str = "测试幽灵"):
    """Create a ghost for a patient and return ghost_id."""
    resp = await client.post(f"/api/games/{game_id}/characters/ghosts", json={
        "origin_patient_id": patient_id,
        "creator_user_id": creator_user_id,
        "name": name,
        "soul_color": "C",
        "print_abilities": [
            {"name": "数据逆流", "color": "C", "ability_count": 2},
        ],
    }, headers=headers)
    assert resp.status_code == 200
    return resp.json()["ghost_id"]


async def _assign_companion(client: AsyncClient, headers: dict, game_id: str, ghost_id: str, patient_id: str):
    """Assign a ghost as companion to a patient."""
    resp = await client.put(
        f"/api/games/{game_id}/ghosts/{ghost_id}/companion",
        json={"patient_id": patient_id},
        headers=headers,
    )
    assert resp.status_code == 200


async def _setup_full_character(client: AsyncClient):
    """Create game + player + patient + ghost + companion assignment."""
    kp, pl, game_id = await _setup_game_with_player(client)
    patient_id = await _create_patient(client, pl["headers"], pl["user_id"], game_id)
    ghost_id = await _create_ghost(client, kp["headers"], game_id, patient_id, kp["user_id"])
    await _assign_companion(client, kp["headers"], game_id, ghost_id, patient_id)
    return kp, pl, game_id, patient_id, ghost_id


# --- GET /characters/active ---

@pytest.mark.asyncio
async def test_get_active_character_success(client: AsyncClient):
    """Returns active patient + companion ghost with abilities and buffs."""
    kp, pl, game_id, patient_id, ghost_id = await _setup_full_character(client)

    resp = await client.get(
        f"/api/games/{game_id}/characters/active",
        headers=pl["headers"],
    )
    assert resp.status_code == 200
    data = resp.json()

    assert "patient" in data
    assert data["patient"]["id"] == patient_id
    assert data["patient"]["name"] == "测试患者"
    assert data["patient"]["soul_color"] == "C"

    assert "ghost" in data
    assert data["ghost"]["id"] == ghost_id
    assert data["ghost"]["name"] == "测试幽灵"
    assert "cmyk" in data["ghost"]
    assert "print_abilities" in data["ghost"]
    assert len(data["ghost"]["print_abilities"]) == 1
    assert "buffs" in data["ghost"]
    assert "origin_data" in data["ghost"]


@pytest.mark.asyncio
async def test_get_active_character_no_active(client: AsyncClient):
    """Player in game but no active_patient_id returns 400."""
    kp, pl, game_id = await _setup_game_with_player(client)

    resp = await client.get(
        f"/api/games/{game_id}/characters/active",
        headers=pl["headers"],
    )
    assert resp.status_code == 400
    assert "No active character" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_get_active_character_no_ghost(client: AsyncClient):
    """Active patient without companion ghost — response has patient only."""
    kp, pl, game_id = await _setup_game_with_player(client)
    await _create_patient(client, pl["headers"], pl["user_id"], game_id)

    resp = await client.get(
        f"/api/games/{game_id}/characters/active",
        headers=pl["headers"],
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "patient" in data
    assert "ghost" not in data


@pytest.mark.asyncio
async def test_get_active_character_proxy(client: AsyncClient):
    """Bot proxy mode: ?user_id= returns that player's active character."""
    kp, pl, game_id, patient_id, ghost_id = await _setup_full_character(client)

    # KP queries PL's active character via proxy
    resp = await client.get(
        f"/api/games/{game_id}/characters/active?user_id={pl['user_id']}",
        headers=kp["headers"],
    )
    assert resp.status_code == 200
    assert resp.json()["patient"]["id"] == patient_id


# --- PUT /characters/active ---

@pytest.mark.asyncio
async def test_switch_active_character_new_path(client: AsyncClient):
    """PUT /characters/active (renamed from /active-character) works."""
    kp, pl, game_id = await _setup_game_with_player(client)
    await _create_patient(client, pl["headers"], pl["user_id"], game_id, "患者一号")
    second_id = await _create_patient(client, pl["headers"], pl["user_id"], game_id, "患者二号")

    resp = await client.put(
        f"/api/games/{game_id}/characters/active",
        json={"patient_id": second_id},
        headers=pl["headers"],
    )
    assert resp.status_code == 200
    assert resp.json()["active_patient_id"] == second_id


# --- GET /characters ---

@pytest.mark.asyncio
async def test_list_characters_success(client: AsyncClient):
    """List characters returns all patients for the user."""
    kp, pl, game_id = await _setup_game_with_player(client)
    id1 = await _create_patient(client, pl["headers"], pl["user_id"], game_id, "患者一号")
    id2 = await _create_patient(client, pl["headers"], pl["user_id"], game_id, "患者二号")

    resp = await client.get(
        f"/api/games/{game_id}/characters",
        headers=pl["headers"],
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["game_id"] == game_id
    ids = [c["patient_id"] for c in data["characters"]]
    assert id1 in ids
    assert id2 in ids


@pytest.mark.asyncio
async def test_list_characters_empty(client: AsyncClient):
    """Player in game with no patients returns empty list."""
    kp, pl, game_id = await _setup_game_with_player(client)

    resp = await client.get(
        f"/api/games/{game_id}/characters",
        headers=pl["headers"],
    )
    assert resp.status_code == 200
    assert resp.json()["characters"] == []


# --- DELETE /characters/{character_id} ---

@pytest.mark.asyncio
async def test_delete_character_owner(client: AsyncClient):
    """Patient owner can delete their own character."""
    kp, pl, game_id = await _setup_game_with_player(client)
    patient_id = await _create_patient(client, pl["headers"], pl["user_id"], game_id)

    resp = await client.delete(
        f"/api/games/{game_id}/characters/{patient_id}",
        headers=pl["headers"],
    )
    assert resp.status_code == 200
    assert resp.json()["deleted"] == patient_id


@pytest.mark.asyncio
async def test_delete_character_dm(client: AsyncClient):
    """DM can delete any player's character."""
    kp, pl, game_id = await _setup_game_with_player(client)
    patient_id = await _create_patient(client, pl["headers"], pl["user_id"], game_id)

    resp = await client.delete(
        f"/api/games/{game_id}/characters/{patient_id}",
        headers=kp["headers"],
    )
    assert resp.status_code == 200
    assert resp.json()["deleted"] == patient_id


@pytest.mark.asyncio
async def test_delete_character_forbidden(client: AsyncClient):
    """Other player cannot delete someone else's character."""
    kp, pl, game_id = await _setup_game_with_player(client)
    patient_id = await _create_patient(client, pl["headers"], pl["user_id"], game_id)

    other = await register_user(client, "Other", "test", "other_del")
    await client.post(f"/api/games/{game_id}/players", json={
        "user_id": other["user_id"], "role": "PL",
    }, headers=kp["headers"])

    resp = await client.delete(
        f"/api/games/{game_id}/characters/{patient_id}",
        headers=other["headers"],
    )
    assert resp.status_code == 403


# --- GET /ghosts/{ghost_id}/abilities ---

@pytest.mark.asyncio
async def test_list_abilities_success(client: AsyncClient):
    """List abilities returns ghost's print abilities."""
    kp, pl, game_id, patient_id, ghost_id = await _setup_full_character(client)

    resp = await client.get(
        f"/api/games/{game_id}/ghosts/{ghost_id}/abilities",
        headers=pl["headers"],
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ghost_id"] == ghost_id
    assert len(data["abilities"]) == 1
    assert data["abilities"][0]["name"] == "数据逆流"


@pytest.mark.asyncio
async def test_list_abilities_not_found(client: AsyncClient):
    """Invalid ghost_id returns 404."""
    kp, pl, game_id = await _setup_game_with_player(client)

    resp = await client.get(
        f"/api/games/{game_id}/ghosts/nonexistent/abilities",
        headers=pl["headers"],
    )
    assert resp.status_code == 404


# --- GET /ghosts/{ghost_id}/buffs ---

@pytest.mark.asyncio
async def test_list_buffs_success(client: AsyncClient):
    """List buffs for a ghost (empty by default)."""
    kp, pl, game_id, patient_id, ghost_id = await _setup_full_character(client)

    resp = await client.get(
        f"/api/games/{game_id}/ghosts/{ghost_id}/buffs",
        headers=pl["headers"],
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ghost_id"] == ghost_id
    assert data["buffs"] == []


@pytest.mark.asyncio
async def test_list_buffs_not_found(client: AsyncClient):
    """Invalid ghost_id returns 404 after fix."""
    kp, pl, game_id = await _setup_game_with_player(client)

    resp = await client.get(
        f"/api/games/{game_id}/ghosts/nonexistent/buffs",
        headers=pl["headers"],
    )
    assert resp.status_code == 404


# --- POST /characters/unlock-archive ---

@pytest.mark.asyncio
async def test_unlock_archive_no_active_character(client: AsyncClient):
    """Unlock archive without active character returns 400."""
    kp, pl, game_id = await _setup_game_with_player(client)

    resp = await client.post(
        f"/api/games/{game_id}/characters/unlock-archive",
        json={"fragment_id": "fake"},
        headers=pl["headers"],
    )
    assert resp.status_code == 400
    assert "No active character" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_unlock_archive_no_companion(client: AsyncClient):
    """Unlock archive without companion ghost returns 400."""
    kp, pl, game_id = await _setup_game_with_player(client)
    await _create_patient(client, pl["headers"], pl["user_id"], game_id)

    resp = await client.post(
        f"/api/games/{game_id}/characters/unlock-archive",
        json={"fragment_id": "fake"},
        headers=pl["headers"],
    )
    assert resp.status_code == 400
    assert "No companion ghost" in resp.json()["detail"]


# --- GET /communications/pending ---

@pytest.mark.asyncio
async def test_list_pending_communications_empty(client: AsyncClient):
    """No pending communications returns empty list."""
    kp, pl, game_id, patient_id, ghost_id = await _setup_full_character(client)

    resp = await client.get(
        f"/api/games/{game_id}/communications/pending",
        headers=pl["headers"],
    )
    assert resp.status_code == 200
    assert resp.json()["pending_requests"] == []


@pytest.mark.asyncio
async def test_list_pending_communications_no_active(client: AsyncClient):
    """Communications endpoint without active character returns 400."""
    kp, pl, game_id = await _setup_game_with_player(client)

    resp = await client.get(
        f"/api/games/{game_id}/communications/pending",
        headers=pl["headers"],
    )
    assert resp.status_code == 400
    assert "No active character" in resp.json()["detail"]
