"""
Agent CRUD tests — focused on field structure and persistence.

Covers:
  • Creating an agent with the full set of configurable fields
  • Retrieving an agent by ID and verifying all fields survive the round-trip
  • tools / channels — correct types and values
  • guardrails / limits — persisted as dicts, contents preserved
  • memory_enabled toggle
  • Partial updates preserve untouched fields
  • Delete removes the record
"""

import pytest


# ── Fixtures / helpers ────────────────────────────────────────────────────────

import uuid


def _unique_name(base: str = "CRUD Agent") -> str:
    """Return a unique agent name to avoid 409 name-collision errors."""
    return f"{base} {uuid.uuid4().hex[:8]}"


def _create(client, payload: dict) -> dict:
    r = client.post("/api/agents", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _make_payment_agent() -> dict:
    """Build a full agent payload with a guaranteed-unique name."""
    return {
        "name": _unique_name("Payment Specialist"),
        "role": "Payment Specialist",
        "system_prompt": "You handle payment failures professionally.",
        "model": "claude-sonnet-4-6",
        "tools": ["payment_lookup", "ticket_creator", "customer_lookup"],
        "channels": ["telegram", "internal"],
        "memory_enabled": True,
        "guardrails": {
            "block_topics": ["competitor_pricing", "pii_leakage"],
            "tone": "professional_empathetic",
            "max_response_length_chars": 1200,
        },
        "limits": {
            "max_iterations": 8,
            "max_tokens": 2048,
            "timeout_seconds": 30,
        },
    }


# ── Create ────────────────────────────────────────────────────────────────────

class TestAgentCreate:
    def test_create_returns_201(self, client):
        r = client.post("/api/agents", json={
            "name": "Minimal CRUD Agent", "role": "tester"
        })
        assert r.status_code == 201

    def test_created_agent_has_id(self, client):
        agent = _create(client, {"name": "ID Check Agent", "role": "r"})
        assert isinstance(agent["id"], int)
        assert agent["id"] > 0

    def test_created_agent_has_timestamps(self, client):
        agent = _create(client, {"name": "Timestamp Agent", "role": "r"})
        assert "created_at" in agent
        assert "updated_at" in agent
        assert agent["created_at"] is not None
        assert agent["updated_at"] is not None

    def test_create_with_all_fields_returns_them(self, client):
        payload = _make_payment_agent()
        agent = _create(client, payload)
        assert agent["name"]           == payload["name"]
        assert agent["role"]           == payload["role"]
        assert agent["system_prompt"]  == payload["system_prompt"]
        assert agent["model"]          == payload["model"]
        assert agent["memory_enabled"] is True

    def test_create_default_fields(self, client):
        """Fields not supplied get sensible defaults."""
        agent = _create(client, {"name": "Defaults Agent", "role": "r"})
        assert agent["tools"]           == []
        assert agent["channels"]        == []
        assert agent["memory_enabled"]  is False
        assert agent["guardrails"]      == {}
        assert agent["limits"]          == {}
        assert agent["system_prompt"]   == ""

    def test_create_missing_name_rejected(self, client):
        r = client.post("/api/agents", json={"role": "no-name"})
        assert r.status_code == 422

    def test_create_missing_role_rejected(self, client):
        r = client.post("/api/agents", json={"name": "no-role"})
        assert r.status_code == 422

    def test_create_duplicate_name_rejected(self, client):
        _create(client, {"name": "Unique CRUD Agent", "role": "r"})
        r = client.post("/api/agents", json={"name": "Unique CRUD Agent", "role": "r2"})
        assert r.status_code == 409


# ── Retrieve ──────────────────────────────────────────────────────────────────

class TestAgentRetrieve:
    def test_get_by_id_returns_200(self, client):
        agent = _create(client, {"name": "GetMe CRUD Agent", "role": "r"})
        r = client.get(f"/api/agents/{agent['id']}")
        assert r.status_code == 200

    def test_get_by_id_returns_correct_agent(self, client):
        created = _create(client, {"name": "FetchCheck Agent", "role": "fetcher"})
        fetched = client.get(f"/api/agents/{created['id']}").json()
        assert fetched["id"]   == created["id"]
        assert fetched["name"] == "FetchCheck Agent"
        assert fetched["role"] == "fetcher"

    def test_get_nonexistent_returns_404(self, client):
        r = client.get("/api/agents/9999999")
        assert r.status_code == 404

    def test_list_returns_all_created_agents(self, client):
        before = len(client.get("/api/agents").json())
        _create(client, {"name": "List Test Agent A", "role": "r"})
        _create(client, {"name": "List Test Agent B", "role": "r"})
        after = len(client.get("/api/agents").json())
        assert after == before + 2


# ── Complex field persistence ─────────────────────────────────────────────────

class TestAgentComplexFields:
    """Verify tools, channels, guardrails, and limits survive create → get."""

    def test_tools_is_list(self, client):
        agent = _create(client, _make_payment_agent())
        fetched = client.get(f"/api/agents/{agent['id']}").json()
        assert isinstance(fetched["tools"], list)

    def test_tools_values_preserved(self, client):
        agent = _create(client, _make_payment_agent())
        fetched = client.get(f"/api/agents/{agent['id']}").json()
        assert fetched["tools"] == ["payment_lookup", "ticket_creator", "customer_lookup"]

    def test_tools_count_correct(self, client):
        agent = _create(client, _make_payment_agent())
        fetched = client.get(f"/api/agents/{agent['id']}").json()
        assert len(fetched["tools"]) == 3

    def test_channels_is_list(self, client):
        agent = _create(client, _make_payment_agent())
        fetched = client.get(f"/api/agents/{agent['id']}").json()
        assert isinstance(fetched["channels"], list)

    def test_channels_include_telegram(self, client):
        agent = _create(client, _make_payment_agent())
        fetched = client.get(f"/api/agents/{agent['id']}").json()
        assert "telegram" in fetched["channels"]

    def test_channels_include_internal(self, client):
        agent = _create(client, _make_payment_agent())
        fetched = client.get(f"/api/agents/{agent['id']}").json()
        assert "internal" in fetched["channels"]

    def test_guardrails_is_dict(self, client):
        agent = _create(client, _make_payment_agent())
        fetched = client.get(f"/api/agents/{agent['id']}").json()
        assert isinstance(fetched["guardrails"], dict)

    def test_guardrails_block_topics_preserved(self, client):
        agent = _create(client, _make_payment_agent())
        fetched = client.get(f"/api/agents/{agent['id']}").json()
        assert "block_topics" in fetched["guardrails"]
        assert "competitor_pricing" in fetched["guardrails"]["block_topics"]

    def test_guardrails_tone_preserved(self, client):
        agent = _create(client, _make_payment_agent())
        fetched = client.get(f"/api/agents/{agent['id']}").json()
        assert fetched["guardrails"]["tone"] == "professional_empathetic"

    def test_limits_is_dict(self, client):
        agent = _create(client, _make_payment_agent())
        fetched = client.get(f"/api/agents/{agent['id']}").json()
        assert isinstance(fetched["limits"], dict)

    def test_limits_max_iterations_preserved(self, client):
        agent = _create(client, _make_payment_agent())
        fetched = client.get(f"/api/agents/{agent['id']}").json()
        assert fetched["limits"]["max_iterations"] == 8

    def test_limits_timeout_preserved(self, client):
        agent = _create(client, _make_payment_agent())
        fetched = client.get(f"/api/agents/{agent['id']}").json()
        assert fetched["limits"]["timeout_seconds"] == 30

    def test_memory_enabled_true_persisted(self, client):
        agent = _create(client, _make_payment_agent())
        fetched = client.get(f"/api/agents/{agent['id']}").json()
        assert fetched["memory_enabled"] is True

    def test_memory_enabled_false_persisted(self, client):
        agent = _create(client, {"name": "No Memory Agent", "role": "r",
                                  "memory_enabled": False})
        fetched = client.get(f"/api/agents/{agent['id']}").json()
        assert fetched["memory_enabled"] is False

    # Names defined in DEFAULT_AGENTS seed data
    _DEFAULT_NAMES = {
        "Support Intake Agent",
        "Payment Investigator Agent",
        "Risk & Compliance Agent",
        "Resolution Agent",
    }

    def _ensure_defaults(self, client, db_session):
        """
        Guarantee the 4 default agents exist in the test DB even if
        seed_agents() already ran (its idempotency guard would skip).
        We insert any missing defaults directly.
        """
        from app.seed.seed_data import DEFAULT_AGENTS
        from app.models.agent import Agent as AgentModel

        existing_names = {a.name for a in db_session.query(AgentModel).all()}
        for spec in DEFAULT_AGENTS:
            if spec["name"] not in existing_names:
                db_session.add(AgentModel(**spec))
        db_session.commit()

        all_agents = client.get("/api/agents").json()
        return [a for a in all_agents if a["name"] in self._DEFAULT_NAMES]

    def test_seeded_support_intake_has_telegram_channel(self, client, db_session):
        """The Support Intake Agent must have 'telegram' in its channels."""
        defaults = self._ensure_defaults(client, db_session)
        intake = next((a for a in defaults if a["name"] == "Support Intake Agent"), None)
        assert intake is not None, "Support Intake Agent missing from DB"
        assert "telegram" in intake["channels"]

    def test_seeded_agents_have_tools(self, client, db_session):
        """Every default agent must have at least one tool configured."""
        defaults = self._ensure_defaults(client, db_session)
        assert len(defaults) == 4, f"Expected 4 default agents, found {len(defaults)}"
        for agent in defaults:
            assert len(agent["tools"]) >= 1, \
                f"Default agent '{agent['name']}' has no tools"

    def test_seeded_agents_have_guardrails(self, client, db_session):
        """Every default agent must have a non-empty guardrails dict."""
        defaults = self._ensure_defaults(client, db_session)
        for agent in defaults:
            assert isinstance(agent["guardrails"], dict)
            assert len(agent["guardrails"]) > 0, \
                f"Default agent '{agent['name']}' has empty guardrails"


# ── Update ────────────────────────────────────────────────────────────────────

class TestAgentUpdate:
    def test_update_tools_replaces_list(self, client):
        agent = _create(client, _make_payment_agent())
        r = client.put(f"/api/agents/{agent['id']}", json={"tools": ["new_tool"]})
        assert r.status_code == 200
        assert r.json()["tools"] == ["new_tool"]

    def test_update_channels_replaces_list(self, client):
        agent = _create(client, _make_payment_agent())
        r = client.put(f"/api/agents/{agent['id']}", json={"channels": ["slack"]})
        assert r.status_code == 200
        assert r.json()["channels"] == ["slack"]

    def test_update_preserves_other_fields(self, client):
        payload = _make_payment_agent()
        agent = _create(client, payload)
        r = client.put(f"/api/agents/{agent['id']}", json={"role": "new role"})
        updated = r.json()
        assert updated["tools"]    == payload["tools"]    # unchanged
        assert updated["channels"] == payload["channels"] # unchanged

    def test_update_guardrails_replaces_dict(self, client):
        agent = _create(client, _make_payment_agent())
        new_gr = {"tone": "formal", "block_topics": ["violence"]}
        r = client.put(f"/api/agents/{agent['id']}", json={"guardrails": new_gr})
        assert r.status_code == 200
        assert r.json()["guardrails"] == new_gr

    def test_update_memory_enabled_toggle(self, client):
        agent = _create(client, {"name": "Toggle Memory Agent", "role": "r",
                                  "memory_enabled": False})
        r = client.put(f"/api/agents/{agent['id']}", json={"memory_enabled": True})
        assert r.status_code == 200
        assert r.json()["memory_enabled"] is True


# ── Delete ────────────────────────────────────────────────────────────────────

class TestAgentDelete:
    def test_delete_returns_204(self, client):
        agent = _create(client, {"name": "DeleteMe CRUD Agent", "role": "r"})
        r = client.delete(f"/api/agents/{agent['id']}")
        assert r.status_code == 204

    def test_delete_makes_agent_unretrievable(self, client):
        agent = _create(client, {"name": "Gone Agent", "role": "r"})
        client.delete(f"/api/agents/{agent['id']}")
        r = client.get(f"/api/agents/{agent['id']}")
        assert r.status_code == 404

    def test_delete_removes_from_list(self, client):
        agent = _create(client, {"name": "Remove From List Agent", "role": "r"})
        agent_id = agent["id"]
        client.delete(f"/api/agents/{agent_id}")
        ids = [a["id"] for a in client.get("/api/agents").json()]
        assert agent_id not in ids
