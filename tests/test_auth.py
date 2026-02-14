"""Tests for the authentication system."""

import pytest
from httpx import AsyncClient

from tests.conftest import register_user


@pytest.mark.asyncio
async def test_register_user(client: AsyncClient):
    resp = await client.post("/api/auth/register", json={
        "username": "NewUser",
        "platform": "qq",
        "platform_uid": "qq_12345",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "user_id" in data
    assert "api_key" in data
    assert "access_token" in data
    assert "expires_at" in data


@pytest.mark.asyncio
async def test_register_duplicate_platform(client: AsyncClient):
    await register_user(client, "First", "qq", "dup_001")
    resp = await client.post("/api/auth/register", json={
        "username": "Second",
        "platform": "qq",
        "platform_uid": "dup_001",
    })
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_login_by_platform(client: AsyncClient):
    user = await register_user(client, "PlatformUser", "qq", "login_001")
    # Platform login requires auth (simulates a trusted bot service calling)
    resp = await client.post("/api/auth/login/platform", json={
        "platform": "qq",
        "platform_uid": "login_001",
    }, headers=user["headers"])
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "user_id" in data


@pytest.mark.asyncio
async def test_login_by_api_key(client: AsyncClient):
    user = await register_user(client, "ApiKeyUser", "web", "ak_001")
    resp = await client.post("/api/auth/login/api-key", json={
        "api_key": user["api_key"],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["user_id"] == user["user_id"]
    assert "access_token" in data


@pytest.mark.asyncio
async def test_login_invalid_platform(client: AsyncClient):
    user = await register_user(client, "InvalidPlat", "test", "ip_001")
    resp = await client.post("/api/auth/login/platform", json={
        "platform": "qq",
        "platform_uid": "nonexistent",
    }, headers=user["headers"])
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_login_invalid_api_key(client: AsyncClient):
    resp = await client.post("/api/auth/login/api-key", json={
        "api_key": "0" * 64,
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_bind_platform(client: AsyncClient):
    user = await register_user(client, "BindUser", "qq", "bind_001")
    resp = await client.post("/api/auth/bind-platform", json={
        "platform": "discord",
        "platform_uid": "disc_001",
    }, headers=user["headers"])
    assert resp.status_code == 200
    assert resp.json()["platform"] == "discord"
    assert resp.json()["status"] == "bound"


@pytest.mark.asyncio
async def test_bind_duplicate_platform(client: AsyncClient):
    user = await register_user(client, "BindDup", "qq", "bindd_001")
    await client.post("/api/auth/bind-platform", json={
        "platform": "discord", "platform_uid": "disc_dup",
    }, headers=user["headers"])

    resp = await client.post("/api/auth/bind-platform", json={
        "platform": "discord", "platform_uid": "disc_dup",
    }, headers=user["headers"])
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_get_me(client: AsyncClient):
    user = await register_user(client, "MeUser", "qq", "me_001")
    resp = await client.get("/api/auth/me", headers=user["headers"])
    assert resp.status_code == 200
    data = resp.json()
    assert data["user_id"] == user["user_id"]
    assert data["username"] == "MeUser"
    assert len(data["platform_bindings"]) == 1
    assert data["platform_bindings"][0]["platform"] == "qq"


@pytest.mark.asyncio
async def test_multi_platform_same_user(client: AsyncClient):
    user = await register_user(client, "MultiPlat", "qq", "multi_001")
    await client.post("/api/auth/bind-platform", json={
        "platform": "discord", "platform_uid": "multi_disc",
    }, headers=user["headers"])

    # Login via discord should return the same user (auth as bot service)
    resp = await client.post("/api/auth/login/platform", json={
        "platform": "discord", "platform_uid": "multi_disc",
    }, headers=user["headers"])
    assert resp.status_code == 200
    assert resp.json()["user_id"] == user["user_id"]


@pytest.mark.asyncio
async def test_protected_endpoint_no_auth(client: AsyncClient):
    resp = await client.post("/api/admin/games", json={"name": "NoAuth"})
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_api_key_header_auth(client: AsyncClient):
    user = await register_user(client, "ApiKeyH", "test", "akh_001")
    # Use X-API-Key header instead of Bearer token
    resp = await client.post("/api/admin/games", json={
        "name": "ViaApiKey",
    }, headers={"X-API-Key": user["api_key"]})
    assert resp.status_code == 200
    assert resp.json()["name"] == "ViaApiKey"


# --- Password auth tests ---


@pytest.mark.asyncio
async def test_register_with_password(client: AsyncClient):
    """Register with password instead of platform binding."""
    resp = await client.post("/api/auth/register", json={
        "username": "PasswordUser",
        "password": "securepass123",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "user_id" in data
    assert "api_key" in data
    assert "access_token" in data


@pytest.mark.asyncio
async def test_register_with_password_and_platform(client: AsyncClient):
    """Register with both password and platform binding."""
    resp = await client.post("/api/auth/register", json={
        "username": "BothAuth",
        "platform": "discord",
        "platform_uid": "both_001",
        "password": "securepass123",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "user_id" in data


@pytest.mark.asyncio
async def test_register_requires_some_auth(client: AsyncClient):
    """Register without password or platform should fail."""
    resp = await client.post("/api/auth/register", json={
        "username": "NoAuth",
    })
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_login_by_password(client: AsyncClient):
    """Login with username + password."""
    await client.post("/api/auth/register", json={
        "username": "PwdLogin",
        "password": "mypassword",
    })
    resp = await client.post("/api/auth/login/password", json={
        "username": "PwdLogin",
        "password": "mypassword",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "user_id" in data


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient):
    """Login with wrong password should fail."""
    await client.post("/api/auth/register", json={
        "username": "WrongPwd",
        "password": "correctpass",
    })
    resp = await client.post("/api/auth/login/password", json={
        "username": "WrongPwd",
        "password": "wrongpass",
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_nonexistent_user(client: AsyncClient):
    """Login with non-existent username should fail."""
    resp = await client.post("/api/auth/login/password", json={
        "username": "Ghost",
        "password": "anything",
    })
    assert resp.status_code == 401


# --- Resolve platform tests ---


@pytest.mark.asyncio
async def test_resolve_platform_success(client: AsyncClient):
    """Bot resolves a known platform identity to user_id."""
    bot = await register_user(client, "BotService", "test", "bot_001")
    player = await register_user(client, "Player1", "qq", "resolve_001")
    resp = await client.post("/api/auth/resolve-platform", json={
        "platform": "qq",
        "platform_uid": "resolve_001",
    }, headers={"X-API-Key": bot["api_key"]})
    assert resp.status_code == 200
    data = resp.json()
    assert data["user_id"] == player["user_id"]
    assert data["username"] == "Player1"


@pytest.mark.asyncio
async def test_resolve_platform_not_found(client: AsyncClient):
    """Resolve unknown platform identity returns 404."""
    bot = await register_user(client, "BotResolve", "test", "botres_001")
    resp = await client.post("/api/auth/resolve-platform", json={
        "platform": "qq",
        "platform_uid": "nonexistent",
    }, headers=bot["headers"])
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_resolve_platform_no_auth(client: AsyncClient):
    """Resolve platform without auth returns 401."""
    resp = await client.post("/api/auth/resolve-platform", json={
        "platform": "qq",
        "platform_uid": "any",
    })
    assert resp.status_code == 401


# --- API key regeneration tests ---


@pytest.mark.asyncio
async def test_regenerate_api_key_via_jwt(client: AsyncClient):
    """Regenerate API key via JWT auth. Old key invalidated, new key works."""
    user = await register_user(client, "RegenJwt", "test", "regen_001")
    old_key = user["api_key"]

    # Regenerate via JWT
    resp = await client.post("/api/auth/regenerate-api-key",
                             headers=user["headers"])
    assert resp.status_code == 200
    new_key = resp.json()["api_key"]
    assert new_key != old_key

    # Old key should fail
    resp = await client.post("/api/admin/games", json={"name": "OldKey"},
                             headers={"X-API-Key": old_key})
    assert resp.status_code == 401

    # New key should work
    resp = await client.post("/api/admin/games", json={"name": "NewKey"},
                             headers={"X-API-Key": new_key})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_regenerate_api_key_via_api_key(client: AsyncClient):
    """Regenerate API key via current API key auth."""
    user = await register_user(client, "RegenKey", "test", "regen_002")
    old_key = user["api_key"]

    resp = await client.post("/api/auth/regenerate-api-key",
                             headers={"X-API-Key": old_key})
    assert resp.status_code == 200
    new_key = resp.json()["api_key"]
    assert new_key != old_key

    # Old key invalidated
    resp = await client.post("/api/auth/regenerate-api-key",
                             headers={"X-API-Key": old_key})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_regenerate_api_key_no_auth(client: AsyncClient):
    """Regenerate without auth returns 401."""
    resp = await client.post("/api/auth/regenerate-api-key")
    assert resp.status_code == 401


# --- Bot proxy pattern tests ---


@pytest.mark.asyncio
async def test_bot_proxy_submit_event(client: AsyncClient):
    """Bot authenticates with its own key, submits event on behalf of player."""
    bot = await register_user(client, "ProxyBot", "test", "proxy_001")
    player = await register_user(client, "ProxyPlayer", "qq", "proxy_002")

    # Bot creates a game
    game_resp = await client.post("/api/admin/games", json={"name": "ProxyGame"},
                                  headers={"X-API-Key": bot["api_key"]})
    game_id = game_resp.json()["game_id"]

    # Bot submits player_join on behalf of player (bot's API key, player's user_id)
    resp = await client.post("/api/bot/events", json={
        "game_id": game_id,
        "user_id": player["user_id"],
        "payload": {"event_type": "player_join", "role": "PL"},
    }, headers={"X-API-Key": bot["api_key"]})
    assert resp.status_code == 200
    assert resp.json()["success"] is True
