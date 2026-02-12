"""End-to-end scenario test: full game flow via API."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_full_game_flow(client: AsyncClient):
    """
    End-to-end scenario:
    1. Create KP and PL players
    2. Create a game (KP)
    3. PL joins game
    4. Create regions
    5. Create patient + ghost for PL
    6. Start game
    7. Start play session
    8. Submit skill_check event → verify dice result
    9. Submit attack event → verify combat + HP change
    10. Query timeline → verify events recorded
    11. End session → end game
    """

    # 1. Create players
    kp_resp = await client.post("/api/admin/players", json={
        "platform": "discord", "platform_uid": "kp_main", "display_name": "KP小倩",
    })
    kp_id = kp_resp.json()["player_id"]

    pl_resp = await client.post("/api/admin/players", json={
        "platform": "discord", "platform_uid": "pl_main", "display_name": "玩家A",
    })
    pl_id = pl_resp.json()["player_id"]

    pl2_resp = await client.post("/api/admin/players", json={
        "platform": "discord", "platform_uid": "pl_ghost_creator", "display_name": "玩家B",
    })
    pl2_id = pl2_resp.json()["player_id"]

    # 2. Create game
    game_resp = await client.post("/api/admin/games", json={
        "name": "灰山城第一章·信号裂痕",
        "created_by": kp_id,
        "config": {"dice_type": 6, "initial_hp": 10},
    })
    game_id = game_resp.json()["game_id"]

    # 3. PL joins game
    join_resp = await client.post(f"/api/admin/games/{game_id}/players", json={
        "player_id": pl_id, "role": "PL",
    })
    assert join_resp.status_code == 200

    # Also add pl2 to game
    await client.post(f"/api/admin/games/{game_id}/players", json={
        "player_id": pl2_id, "role": "PL",
    })

    # 4. Create regions
    region_resp = await client.post(f"/api/admin/games/{game_id}/regions", json={
        "code": "A", "name": "数据荒原",
    })
    assert region_resp.status_code == 200

    # 5. Create patient → get SWAP → create ghost
    patient_resp = await client.post("/api/admin/characters/patient", json={
        "player_id": pl_id,
        "game_id": game_id,
        "name": "林默",
        "soul_color": "C",
        "gender": "男",
        "age": 28,
        "identity": "前数据分析师",
        "personality_archives": {
            "C": "我总是在深夜思考，那些数据背后是否隐藏着什么",
            "M": "那天我在暴雨中狂奔，仿佛要甩掉所有枷锁",
            "Y": "和朋友们在天台看日落，那一刻什么都不用想",
            "K": "即使全世界都说不可能，我也要找到那个答案",
        },
        "ideal_projection": "我想成为一个能看穿一切谎言的存在，一个数据世界的守望者",
    })
    patient_id = patient_resp.json()["patient_id"]
    swap = patient_resp.json()["swap_file"]
    assert swap["soul_color"] == "C"

    ghost_resp = await client.post("/api/admin/characters/ghost", json={
        "patient_id": patient_id,
        "creator_player_id": pl2_id,
        "game_id": game_id,
        "name": "Echo",
        "soul_color": "C",
        "appearance": "半透明的蓝色人形光影，周身环绕着飘浮的数据碎片",
        "personality": "冷静而好奇，经常用数据逻辑分析一切",
        "print_abilities": [
            {
                "name": "数据逆流",
                "color": "C",
                "description": "创造一道逆流的数据瀑布，暂时扭曲局部的因果逻辑",
                "ability_count": 2,
            },
        ],
    })
    ghost_id = ghost_resp.json()["ghost_id"]
    assert ghost_resp.json()["cmyk"]["C"] == 1

    # Also create a second patient+ghost as target
    p2_patient = await client.post("/api/admin/characters/patient", json={
        "player_id": pl2_id, "game_id": game_id, "name": "敌方实体", "soul_color": "M",
    })
    target_patient_id = p2_patient.json()["patient_id"]

    target_ghost = await client.post("/api/admin/characters/ghost", json={
        "patient_id": target_patient_id,
        "creator_player_id": pl_id,
        "game_id": game_id,
        "name": "Glitch",
        "soul_color": "M",
    })
    target_ghost_id = target_ghost.json()["ghost_id"]

    # 6. Start game
    start_game_resp = await client.post("/api/bot/events", json={
        "game_id": game_id,
        "player_id": kp_id,
        "payload": {"event_type": "game_start"},
    })
    assert start_game_resp.status_code == 200
    assert start_game_resp.json()["success"] is True
    assert start_game_resp.json()["data"]["status"] == "active"

    # Verify game is active
    game_info = await client.get(f"/api/bot/games/{game_id}")
    assert game_info.json()["status"] == "active"

    # 7. Start play session
    session_start_resp = await client.post("/api/bot/events", json={
        "game_id": game_id,
        "player_id": kp_id,
        "payload": {"event_type": "session_start"},
    })
    assert session_start_resp.status_code == 200
    assert session_start_resp.json()["success"] is True
    session_id = session_start_resp.json()["data"]["session_id"]

    # 8. Skill check
    check_resp = await client.post("/api/bot/events", json={
        "game_id": game_id,
        "session_id": session_id,
        "player_id": pl_id,
        "payload": {
            "event_type": "skill_check",
            "color": "C",
            "difficulty": 3,
            "context": "尝试分析扇区的数据流，寻找异常信号",
        },
    })
    assert check_resp.status_code == 200
    check_data = check_resp.json()
    assert check_data["success"] is True
    assert check_data["event_type"] == "skill_check"
    assert "roll_total" in check_data["data"]
    assert "check_success" in check_data["data"]
    assert len(check_data["rolls"]) == 1

    # 9. Attack
    atk_resp = await client.post("/api/bot/events", json={
        "game_id": game_id,
        "session_id": session_id,
        "player_id": pl_id,
        "payload": {
            "event_type": "attack",
            "attacker_ghost_id": ghost_id,
            "target_ghost_id": target_ghost_id,
            "color_used": "C",
        },
    })
    assert atk_resp.status_code == 200
    atk_data = atk_resp.json()
    assert atk_data["success"] is True
    assert atk_data["event_type"] == "attack"
    assert "hit" in atk_data["data"]

    # 10. Query timeline
    tl_resp = await client.get(f"/api/bot/sessions/{session_id}/timeline")
    assert tl_resp.status_code == 200
    events = tl_resp.json()["events"]
    assert len(events) >= 3  # session_start + skill_check + attack
    event_types = [e["event_type"] for e in events]
    assert "session_start" in event_types
    assert "skill_check" in event_types
    assert "attack" in event_types

    # 11. End session and game
    end_session_resp = await client.post("/api/bot/events", json={
        "game_id": game_id,
        "session_id": session_id,
        "player_id": kp_id,
        "payload": {"event_type": "session_end"},
    })
    assert end_session_resp.status_code == 200
    assert end_session_resp.json()["data"]["status"] == "ended"

    end_game_resp = await client.post("/api/bot/events", json={
        "game_id": game_id,
        "player_id": kp_id,
        "payload": {"event_type": "game_end"},
    })
    assert end_game_resp.status_code == 200
    assert end_game_resp.json()["data"]["status"] == "ended"
