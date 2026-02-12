"""Integration tests for the admin and bot API endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health(client: AsyncClient):
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["engine"] == "dg-core"


@pytest.mark.asyncio
async def test_create_player(client: AsyncClient):
    resp = await client.post("/api/admin/players", json={
        "platform": "discord",
        "platform_uid": "user123",
        "display_name": "TestPlayer",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "player_id" in data
    assert "api_key" in data
    assert len(data["api_key"]) == 64


@pytest.mark.asyncio
async def test_create_game(client: AsyncClient):
    # Create a player first
    player_resp = await client.post("/api/admin/players", json={
        "platform": "discord",
        "platform_uid": "kp001",
        "display_name": "KP",
    })
    player_id = player_resp.json()["player_id"]

    # Create game
    resp = await client.post("/api/admin/games", json={
        "name": "Test Game",
        "created_by": player_id,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Test Game"
    assert data["status"] == "preparing"


@pytest.mark.asyncio
async def test_create_patient_and_ghost(client: AsyncClient):
    # Setup: player + game
    player_resp = await client.post("/api/admin/players", json={
        "platform": "discord", "platform_uid": "pl001", "display_name": "Player1",
    })
    player_id = player_resp.json()["player_id"]

    creator_resp = await client.post("/api/admin/players", json={
        "platform": "discord", "platform_uid": "pl002", "display_name": "Player2",
    })
    creator_id = creator_resp.json()["player_id"]

    game_resp = await client.post("/api/admin/games", json={
        "name": "CharTest", "created_by": player_id,
    })
    game_id = game_resp.json()["game_id"]

    # Create patient
    patient_resp = await client.post("/api/admin/characters/patient", json={
        "player_id": player_id,
        "game_id": game_id,
        "name": "测试患者",
        "soul_color": "C",
        "gender": "男",
        "age": 25,
        "personality_archives": {
            "C": "一个关于忧郁的故事",
            "M": "一个关于愤怒的故事",
        },
        "ideal_projection": "我想成为一个自由的旅人",
    })
    assert patient_resp.status_code == 200
    patient_data = patient_resp.json()
    assert patient_data["name"] == "测试患者"
    assert patient_data["swap_file"]["soul_color"] == "C"
    assert "C" in patient_data["swap_file"]["revealed_archive"]
    # SWAP should NOT reveal M archive
    assert "M" not in patient_data["swap_file"]["revealed_archive"]

    # Create ghost
    ghost_resp = await client.post("/api/admin/characters/ghost", json={
        "patient_id": patient_data["patient_id"],
        "creator_player_id": creator_id,
        "game_id": game_id,
        "name": "测试幽灵",
        "soul_color": "C",
        "appearance": "数字蓝色光影形态",
        "personality": "冷静分析型",
        "print_abilities": [
            {"name": "逆流之雨", "color": "C", "description": "创造倒流的数据雨", "ability_count": 2},
        ],
    })
    assert ghost_resp.status_code == 200
    ghost_data = ghost_resp.json()
    assert ghost_data["cmyk"]["C"] == 1
    assert ghost_data["cmyk"]["M"] == 0
    assert ghost_data["hp"] == 10
    assert len(ghost_data["print_abilities"]) == 1
    assert ghost_data["print_abilities"][0]["name"] == "逆流之雨"


@pytest.mark.asyncio
async def test_get_character(client: AsyncClient):
    # Create player + game + patient
    p = await client.post("/api/admin/players", json={
        "platform": "web", "platform_uid": "u1", "display_name": "P1"
    })
    pid = p.json()["player_id"]
    g = await client.post("/api/admin/games", json={"name": "G1", "created_by": pid})
    gid = g.json()["game_id"]
    pat = await client.post("/api/admin/characters/patient", json={
        "player_id": pid, "game_id": gid, "name": "患者A", "soul_color": "M",
    })
    patient_id = pat.json()["patient_id"]

    # Lookup patient
    resp = await client.get(f"/api/admin/characters/{patient_id}")
    assert resp.status_code == 200
    assert resp.json()["type"] == "patient"
    assert resp.json()["name"] == "患者A"


@pytest.mark.asyncio
async def test_game_not_found(client: AsyncClient):
    resp = await client.get("/api/bot/games/nonexistent")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_region_crud(client: AsyncClient):
    # Setup: player + game
    p = await client.post("/api/admin/players", json={
        "platform": "qq", "platform_uid": "r1", "display_name": "RegionKP",
    })
    pid = p.json()["player_id"]
    g = await client.post("/api/admin/games", json={"name": "RegionTest", "created_by": pid})
    game_id = g.json()["game_id"]

    # Create regions
    r1 = await client.post(f"/api/admin/games/{game_id}/regions", json={
        "code": "A", "name": "数据荒原",
    })
    assert r1.status_code == 200
    assert r1.json()["code"] == "A"

    r2 = await client.post(f"/api/admin/games/{game_id}/regions", json={
        "code": "B", "name": "信号塔区",
    })
    assert r2.status_code == 200

    # List regions
    regions = await client.get(f"/api/admin/games/{game_id}/regions")
    assert regions.status_code == 200
    assert len(regions.json()["regions"]) == 2

    # Create location under region A
    region_a_id = r1.json()["region_id"]
    loc = await client.post(f"/api/admin/regions/{region_a_id}/locations", json={
        "name": "数据废墟",
        "description": "一片荒废的数据存储设施",
        "content": "这里曾经是灰山城最大的数据中心...",
    })
    assert loc.status_code == 200
    assert loc.json()["name"] == "数据废墟"

    # List locations
    locs = await client.get(f"/api/admin/regions/{region_a_id}/locations")
    assert locs.status_code == 200
    assert len(locs.json()["locations"]) == 1
