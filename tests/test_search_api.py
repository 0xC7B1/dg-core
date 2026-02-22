"""Tests for entity name search, listing, and batch resolve endpoints."""

from tests.conftest import register_user


# --- Helpers ---


async def _setup_game_with_entities(client):
    """Create a game with patients, ghosts, regions, locations, and items."""
    user = await register_user(client)
    h = user["headers"]
    uid = user["user_id"]

    # Create game
    game_resp = await client.post("/api/games", json={"name": "SearchGame"}, headers=h)
    gid = game_resp.json()["game_id"]

    # Create patients
    p1 = await client.post(f"/api/games/{gid}/characters/patients", json={
        "user_id": uid, "name": "Alice", "soul_color": "C",
    }, headers=h)
    pid1 = p1.json()["patient_id"]

    p2 = await client.post(f"/api/games/{gid}/characters/patients", json={
        "user_id": uid, "name": "Bob", "soul_color": "M",
    }, headers=h)
    pid2 = p2.json()["patient_id"]

    # Create ghosts
    g1 = await client.post(f"/api/games/{gid}/characters/ghosts", json={
        "origin_patient_id": pid1, "creator_user_id": uid,
        "name": "ShadowAlice", "soul_color": "C",
    }, headers=h)
    ghost1_id = g1.json()["ghost_id"]

    g2 = await client.post(f"/api/games/{gid}/characters/ghosts", json={
        "origin_patient_id": pid2, "creator_user_id": uid,
        "name": "EchoBob", "soul_color": "M",
    }, headers=h)
    ghost2_id = g2.json()["ghost_id"]

    # Create region + location
    r1 = await client.post(f"/api/games/{gid}/regions", json={
        "code": "A", "name": "District Alpha",
    }, headers=h)
    rid = r1.json()["region_id"]

    l1 = await client.post(f"/api/games/{gid}/regions/{rid}/locations", json={
        "name": "Alpha Station",
    }, headers=h)
    lid = l1.json()["location_id"]

    # Create item definition
    i1 = await client.post(f"/api/games/{gid}/items/definitions", json={
        "name": "Healing Potion",
    }, headers=h)
    item_id = i1.json()["id"]

    return {
        "user": user, "game_id": gid,
        "patient_ids": [pid1, pid2],
        "ghost_ids": [ghost1_id, ghost2_id],
        "region_id": rid, "location_id": lid,
        "item_id": item_id,
    }


# --- Game listing ---


async def test_list_games(client):
    user = await register_user(client)
    await client.post("/api/games", json={"name": "Game1"}, headers=user["headers"])
    await client.post("/api/games", json={"name": "Game2"}, headers=user["headers"])

    resp = await client.get("/api/games", headers=user["headers"])
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["games"]) == 2
    names = {g["name"] for g in data["games"]}
    assert names == {"Game1", "Game2"}


async def test_list_games_empty(client):
    user = await register_user(client)
    resp = await client.get("/api/games", headers=user["headers"])
    assert resp.status_code == 200
    assert len(resp.json()["games"]) == 0


# --- Ghost listing ---


async def test_list_ghosts_in_game(client):
    ctx = await _setup_game_with_entities(client)
    h = ctx["user"]["headers"]
    gid = ctx["game_id"]

    resp = await client.get(f"/api/games/{gid}/characters/ghosts", headers=h)
    assert resp.status_code == 200
    data = resp.json()
    assert data["game_id"] == gid
    assert len(data["ghosts"]) == 2
    names = {g["name"] for g in data["ghosts"]}
    assert names == {"ShadowAlice", "EchoBob"}


async def test_list_ghosts_by_name(client):
    ctx = await _setup_game_with_entities(client)
    h = ctx["user"]["headers"]
    gid = ctx["game_id"]

    resp = await client.get(f"/api/games/{gid}/characters/ghosts?name=Shadow", headers=h)
    assert resp.status_code == 200
    ghosts = resp.json()["ghosts"]
    assert len(ghosts) == 1
    assert ghosts[0]["name"] == "ShadowAlice"


# --- Patient listing ---


async def test_list_all_patients(client):
    ctx = await _setup_game_with_entities(client)
    h = ctx["user"]["headers"]
    gid = ctx["game_id"]

    resp = await client.get(f"/api/games/{gid}/characters?all=true", headers=h)
    assert resp.status_code == 200
    chars = resp.json()["characters"]
    assert len(chars) == 2
    names = {c["name"] for c in chars}
    assert names == {"Alice", "Bob"}


async def test_search_patients_by_name(client):
    ctx = await _setup_game_with_entities(client)
    h = ctx["user"]["headers"]
    gid = ctx["game_id"]

    resp = await client.get(f"/api/games/{gid}/characters?all=true&name=Ali", headers=h)
    assert resp.status_code == 200
    chars = resp.json()["characters"]
    assert len(chars) == 1
    assert chars[0]["name"] == "Alice"


# --- Session listing ---


async def test_list_sessions_for_game(client):
    ctx = await _setup_game_with_entities(client)
    h = ctx["user"]["headers"]
    gid = ctx["game_id"]

    # Start game then session
    await client.post("/api/events", json={
        "game_id": gid, "user_id": ctx["user"]["user_id"],
        "payload": {"event_type": "game_start"},
    }, headers=h)
    await client.post("/api/events", json={
        "game_id": gid, "user_id": ctx["user"]["user_id"],
        "payload": {"event_type": "session_start"},
    }, headers=h)

    resp = await client.get(f"/api/games/{gid}/sessions", headers=h)
    assert resp.status_code == 200
    data = resp.json()
    assert data["game_id"] == gid
    assert len(data["sessions"]) == 1
    assert data["sessions"][0]["status"] == "active"


async def test_list_sessions_with_status_filter(client):
    ctx = await _setup_game_with_entities(client)
    h = ctx["user"]["headers"]
    gid = ctx["game_id"]

    resp = await client.get(f"/api/games/{gid}/sessions?status=active", headers=h)
    assert resp.status_code == 200
    assert len(resp.json()["sessions"]) == 0  # no sessions yet


# --- Batch resolve ---


async def test_resolve_names(client):
    ctx = await _setup_game_with_entities(client)
    h = ctx["user"]["headers"]
    gid = ctx["game_id"]

    resp = await client.post(f"/api/games/{gid}/resolve", json={
        "queries": [
            {"name": "Alice", "entity_type": "patient"},
            {"name": "Shadow", "entity_type": "ghost"},
            {"name": "Alpha", "entity_type": "region"},
        ],
    }, headers=h)
    assert resp.status_code == 200
    results = resp.json()["results"]
    types = {r["entity_type"] for r in results}
    assert "patient" in types
    assert "ghost" in types
    assert "region" in types

    patient_results = [r for r in results if r["entity_type"] == "patient"]
    assert len(patient_results) == 1
    assert patient_results[0]["name"] == "Alice"


async def test_resolve_names_no_match(client):
    ctx = await _setup_game_with_entities(client)
    h = ctx["user"]["headers"]
    gid = ctx["game_id"]

    resp = await client.post(f"/api/games/{gid}/resolve", json={
        "queries": [{"name": "Nonexistent"}],
    }, headers=h)
    assert resp.status_code == 200
    assert len(resp.json()["results"]) == 0


async def test_resolve_names_all_types(client):
    ctx = await _setup_game_with_entities(client)
    h = ctx["user"]["headers"]
    gid = ctx["game_id"]

    # Resolve with no entity_type filter — searches all types
    resp = await client.post(f"/api/games/{gid}/resolve", json={
        "queries": [{"name": "Alpha"}],
    }, headers=h)
    assert resp.status_code == 200
    results = resp.json()["results"]
    # Should find both "District Alpha" region and "Alpha Station" location
    types = {r["entity_type"] for r in results}
    assert "region" in types
    assert "location" in types


# --- Region/Location name filter ---


async def test_region_name_filter(client):
    ctx = await _setup_game_with_entities(client)
    h = ctx["user"]["headers"]
    gid = ctx["game_id"]

    resp = await client.get(f"/api/games/{gid}/regions?name=Alpha", headers=h)
    assert resp.status_code == 200
    regions = resp.json()["regions"]
    assert len(regions) == 1
    assert regions[0]["name"] == "District Alpha"


async def test_location_name_filter(client):
    ctx = await _setup_game_with_entities(client)
    h = ctx["user"]["headers"]
    gid = ctx["game_id"]
    rid = ctx["region_id"]

    resp = await client.get(
        f"/api/games/{gid}/regions/{rid}/locations?name=Station", headers=h,
    )
    assert resp.status_code == 200
    locations = resp.json()["locations"]
    assert len(locations) == 1
    assert locations[0]["name"] == "Alpha Station"


# --- Item name filter ---


async def test_item_definition_name_filter(client):
    ctx = await _setup_game_with_entities(client)
    h = ctx["user"]["headers"]
    gid = ctx["game_id"]

    resp = await client.get(f"/api/games/{gid}/items/definitions?name=Healing", headers=h)
    assert resp.status_code == 200
    defs = resp.json()["definitions"]
    assert len(defs) == 1
    assert defs[0]["name"] == "Healing Potion"

    # No match
    resp2 = await client.get(f"/api/games/{gid}/items/definitions?name=Sword", headers=h)
    assert resp2.status_code == 200
    assert len(resp2.json()["definitions"]) == 0
