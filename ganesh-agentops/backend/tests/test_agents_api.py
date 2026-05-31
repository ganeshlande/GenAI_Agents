"""
Agent CRUD API tests.
Uses the shared TestClient fixture from conftest.py (isolated SQLite test DB).
"""

import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────

MINIMAL_AGENT = {
    "name": "Test Agent Alpha",
    "role": "tester",
}

FULL_AGENT = {
    "name": "Test Agent Beta",
    "role": "researcher",
    "system_prompt": "You research things.",
    "model": "claude-sonnet-4-6",
    "tools": ["web_search", "calculator"],
    "channels": ["internal"],
    "memory_enabled": True,
    "guardrails": {"block_topics": ["violence"]},
    "limits": {"max_iterations": 10},
}


def _create(client, payload: dict) -> dict:
    r = client.post("/api/agents", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


# ── Seed ──────────────────────────────────────────────────────────────────────

def test_seed_agents_present(client, db_session):
    """
    The 4 default agents must be visible via the API after seeding.
    seed_agents() is called with the test session so it writes to the same
    database the TestClient reads from.
    """
    from app.seed.seed_data import seed_agents, DEFAULT_AGENTS

    seed_agents(db=db_session)

    r = client.get("/api/agents")
    assert r.status_code == 200
    names = [a["name"] for a in r.json()]
    for expected in [d["name"] for d in DEFAULT_AGENTS]:
        assert expected in names, f"Seeded agent '{expected}' not found in {names}"


# ── LIST ──────────────────────────────────────────────────────────────────────

def test_list_agents_returns_list(client):
    r = client.get("/api/agents")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_list_agents_pagination(client):
    r = client.get("/api/agents?skip=0&limit=2")
    assert r.status_code == 200
    assert len(r.json()) <= 2


def test_list_agents_invalid_limit(client):
    r = client.get("/api/agents?limit=0")
    assert r.status_code == 422


# ── CREATE ────────────────────────────────────────────────────────────────────

def test_create_agent_minimal(client):
    agent = _create(client, MINIMAL_AGENT)
    assert agent["name"] == MINIMAL_AGENT["name"]
    assert agent["role"] == MINIMAL_AGENT["role"]
    assert agent["id"] is not None
    assert agent["tools"] == []
    assert agent["memory_enabled"] is False
    assert "created_at" in agent
    assert "updated_at" in agent


def test_create_agent_full(client):
    agent = _create(client, FULL_AGENT)
    assert agent["tools"] == ["web_search", "calculator"]
    assert agent["memory_enabled"] is True
    assert agent["guardrails"] == {"block_topics": ["violence"]}
    assert agent["limits"] == {"max_iterations": 10}


def test_create_agent_duplicate_name(client):
    _create(client, {"name": "Unique Agent X", "role": "r"})
    r = client.post("/api/agents", json={"name": "Unique Agent X", "role": "r2"})
    assert r.status_code == 409
    assert "already exists" in r.json()["detail"]


def test_create_agent_missing_required_fields(client):
    r = client.post("/api/agents", json={"role": "r"})   # missing name
    assert r.status_code == 422


# ── GET ───────────────────────────────────────────────────────────────────────

def test_get_agent_by_id(client):
    created = _create(client, {"name": "GetMe Agent", "role": "r"})
    r = client.get(f"/api/agents/{created['id']}")
    assert r.status_code == 200
    assert r.json()["name"] == "GetMe Agent"


def test_get_agent_not_found(client):
    r = client.get("/api/agents/99999")
    assert r.status_code == 404
    assert "not found" in r.json()["detail"]


# ── UPDATE ────────────────────────────────────────────────────────────────────

def test_update_agent_partial(client):
    created = _create(client, {"name": "UpdateMe Agent", "role": "original_role"})
    r = client.put(f"/api/agents/{created['id']}", json={"role": "updated_role"})
    assert r.status_code == 200
    body = r.json()
    assert body["role"] == "updated_role"
    assert body["name"] == "UpdateMe Agent"           # unchanged
    assert body["updated_at"] >= body["created_at"]  # timestamp advanced


def test_update_agent_json_fields(client):
    created = _create(client, {"name": "JSON Update Agent", "role": "r"})
    r = client.put(
        f"/api/agents/{created['id']}",
        json={"tools": ["new_tool"], "memory_enabled": True},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["tools"] == ["new_tool"]
    assert body["memory_enabled"] is True


def test_update_agent_empty_body(client):
    created = _create(client, {"name": "EmptyUpdate Agent", "role": "r"})
    r = client.put(f"/api/agents/{created['id']}", json={})
    assert r.status_code == 422


def test_update_agent_not_found(client):
    r = client.put("/api/agents/99999", json={"role": "x"})
    assert r.status_code == 404


def test_update_agent_duplicate_name(client):
    _create(client, {"name": "Name Conflict A", "role": "r"})
    b = _create(client, {"name": "Name Conflict B", "role": "r"})
    r = client.put(f"/api/agents/{b['id']}", json={"name": "Name Conflict A"})
    assert r.status_code == 409


# ── DELETE ────────────────────────────────────────────────────────────────────

def test_delete_agent(client):
    created = _create(client, {"name": "DeleteMe Agent", "role": "r"})
    r = client.delete(f"/api/agents/{created['id']}")
    assert r.status_code == 204

    # Confirm gone
    r2 = client.get(f"/api/agents/{created['id']}")
    assert r2.status_code == 404


def test_delete_agent_not_found(client):
    r = client.delete("/api/agents/99999")
    assert r.status_code == 404
