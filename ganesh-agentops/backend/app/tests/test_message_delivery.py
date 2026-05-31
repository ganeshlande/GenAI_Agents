"""
Message delivery tests — verifies agent-to-agent message persistence.

Covers:
  • Messages are stored in the database after a workflow run
  • Each message has a sender_agent, content, channel, and timestamp
  • Messages are linked to the workflow run via run_id
  • Correct agents appear in the message list (Intake, Investigator, Resolution)
  • Internal channel is used for agent-to-agent communication
  • Telegram channel messages can be persisted (channel routing)
  • Messages are retrievable via both /api/runs/{id}/messages and /api/messages
  • Cross-run message isolation (messages don't leak between runs)
"""

import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────

def _senders(messages: list) -> set:
    return {m["sender_agent"] for m in messages if m["sender_agent"]}


# ── Message structure ─────────────────────────────────────────────────────────

class TestMessageStructure:
    """Every persisted message must have the required fields."""

    def test_messages_exist_after_run(self, client, pfi_run):
        msgs = client.get(f"/api/runs/{pfi_run['run_id']}/messages").json()
        assert len(msgs) >= 1, "No messages persisted after workflow run"

    def test_each_message_has_id(self, client, pfi_run):
        msgs = client.get(f"/api/runs/{pfi_run['run_id']}/messages").json()
        for m in msgs:
            assert "id" in m
            assert isinstance(m["id"], int)

    def test_each_message_has_content(self, client, pfi_run):
        msgs = client.get(f"/api/runs/{pfi_run['run_id']}/messages").json()
        for m in msgs:
            assert "content" in m
            assert len(m["content"]) > 0, f"Empty content for message id={m.get('id')}"

    def test_each_message_has_channel(self, client, pfi_run):
        msgs = client.get(f"/api/runs/{pfi_run['run_id']}/messages").json()
        for m in msgs:
            assert "channel" in m
            assert m["channel"] in ("internal", "telegram", "slack", "whatsapp"), \
                f"Unexpected channel: {m['channel']}"

    def test_each_message_has_timestamp(self, client, pfi_run):
        msgs = client.get(f"/api/runs/{pfi_run['run_id']}/messages").json()
        for m in msgs:
            assert "created_at" in m
            assert m["created_at"] is not None

    def test_each_message_has_run_id(self, client, pfi_run):
        msgs = client.get(f"/api/runs/{pfi_run['run_id']}/messages").json()
        for m in msgs:
            assert "run_id" in m

    def test_each_message_has_message_type(self, client, pfi_run):
        msgs = client.get(f"/api/runs/{pfi_run['run_id']}/messages").json()
        for m in msgs:
            assert "message_type" in m
            assert m["message_type"]  # non-empty

    def test_sender_agent_field_present(self, client, pfi_run):
        """sender_agent may be None (human input) but the key must exist."""
        msgs = client.get(f"/api/runs/{pfi_run['run_id']}/messages").json()
        for m in msgs:
            assert "sender_agent" in m

    def test_receiver_agent_field_present(self, client, pfi_run):
        """receiver_agent may be None but the key must exist."""
        msgs = client.get(f"/api/runs/{pfi_run['run_id']}/messages").json()
        for m in msgs:
            assert "receiver_agent" in m


# ── Agent presence ────────────────────────────────────────────────────────────

class TestAgentMessagePresence:
    """The PFI pipeline (non-fraud path) involves Intake → Investigator → Resolution."""

    def test_at_least_two_distinct_senders(self, client, pfi_run):
        msgs = client.get(f"/api/runs/{pfi_run['run_id']}/messages").json()
        senders = _senders(msgs)
        assert len(senders) >= 2, f"Only {len(senders)} distinct sender(s): {senders}"

    def test_support_intake_agent_sends_message(self, client, pfi_run):
        msgs = client.get(f"/api/runs/{pfi_run['run_id']}/messages").json()
        assert "Support Intake Agent" in _senders(msgs)

    def test_resolution_agent_sends_message(self, client, pfi_run):
        """Non-fraud card-declined path always reaches Resolution."""
        msgs = client.get(f"/api/runs/{pfi_run['run_id']}/messages").json()
        assert "Resolution Agent" in _senders(msgs)

    def test_intake_message_references_payment_id(self, client, pfi_run):
        msgs = client.get(f"/api/runs/{pfi_run['run_id']}/messages").json()
        intake_msgs = [m for m in msgs if m["sender_agent"] == "Support Intake Agent"]
        assert len(intake_msgs) >= 1
        assert any("PAY-10291" in m["content"] for m in intake_msgs)

    def test_resolution_message_contains_investigation_result(self, client, pfi_run):
        msgs = client.get(f"/api/runs/{pfi_run['run_id']}/messages").json()
        res_msgs = [m for m in msgs if m["sender_agent"] == "Resolution Agent"]
        assert len(res_msgs) >= 1
        # Resolution message should describe the outcome
        content = " ".join(m["content"] for m in res_msgs).lower()
        assert any(kw in content for kw in
                   ("investigation", "complete", "card", "payment", "resolution", "summary")), \
            f"Resolution message doesn't look like an investigation result: {content[:200]}"


# ── Run linkage ───────────────────────────────────────────────────────────────

class TestMessageRunLinkage:
    """Messages must be tied to their specific run_id."""

    def test_messages_linked_to_correct_run_id(self, client, pfi_run):
        run_id = pfi_run["run_id"]
        msgs = client.get(f"/api/runs/{run_id}/messages").json()
        for m in msgs:
            assert m["run_id"] == run_id, \
                f"Message {m['id']} has run_id={m['run_id']}, expected {run_id}"

    def test_messages_not_returned_for_wrong_run_id(self, client, pfi_run):
        """A fresh run must not return messages from a previous run."""
        run_id = pfi_run["run_id"]
        phantom_id = run_id + 99999
        r = client.get(f"/api/runs/{phantom_id}/messages")
        assert r.status_code == 404

    def test_cross_run_isolation(self, client, seeded):
        """Messages from run A must not appear in run B's message list."""
        wfs = seeded["workflows"]
        pfi = next(w for w in wfs if w["template_type"] == "payment_failure_investigation")

        # Run A
        run_a_id = client.post(
            f"/api/workflows/{pfi['id']}/run",
            json={"message": "Run A — PAY-10291"},
        ).json()["run_id"]

        # Run B
        run_b_id = client.post(
            f"/api/workflows/{pfi['id']}/run",
            json={"message": "Run B — PAY-10291"},
        ).json()["run_id"]

        assert run_a_id != run_b_id

        msgs_a = {m["id"] for m in client.get(f"/api/runs/{run_a_id}/messages").json()}
        msgs_b = {m["id"] for m in client.get(f"/api/runs/{run_b_id}/messages").json()}

        assert msgs_a.isdisjoint(msgs_b), \
            f"Message IDs leaked between runs: {msgs_a & msgs_b}"


# ── Channel routing ───────────────────────────────────────────────────────────

class TestChannelRouting:
    """Verify channel field is set correctly for different message sources."""

    def test_agent_messages_use_internal_channel(self, client, pfi_run):
        msgs = client.get(f"/api/runs/{pfi_run['run_id']}/messages").json()
        # All agent-to-agent messages must be on the 'internal' channel
        agent_msgs = [m for m in msgs if m["sender_agent"] is not None]
        for m in agent_msgs:
            assert m["channel"] == "internal", \
                f"Agent message {m['id']} uses channel '{m['channel']}' instead of 'internal'"

    def test_telegram_channel_message_can_be_persisted(self, db_session):
        """Directly persist a telegram-channel message and confirm it's stored."""
        from app.runtime.memory import persist_message

        # Persist without a run (run_id=None is allowed for inbound Telegram messages)
        msg = persist_message(
            db_session,
            run_id=None,
            sender_agent=None,
            receiver_agent="Support Intake Agent",
            content="[Telegram @testuser] PAY-99999 failed",
            message_type="text",
            channel="telegram",
        )
        db_session.refresh(msg)

        assert msg.id is not None
        assert msg.channel == "telegram"
        assert msg.sender_agent is None
        assert msg.receiver_agent == "Support Intake Agent"
        assert "PAY-99999" in msg.content

    def test_telegram_channel_filter_works(self, client, pfi_run):
        """GET /api/messages?channel=internal should only return internal messages."""
        internal_msgs = client.get("/api/messages?channel=internal").json()
        for m in internal_msgs:
            assert m["channel"] == "internal"


# ── Retrieval APIs ────────────────────────────────────────────────────────────

class TestMessageRetrieval:
    """Messages are accessible via both the run-scoped and global endpoints."""

    def test_run_messages_endpoint_returns_list(self, client, pfi_run):
        r = client.get(f"/api/runs/{pfi_run['run_id']}/messages")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_global_messages_endpoint_returns_run_messages(self, client, pfi_run):
        run_id = pfi_run["run_id"]
        msgs = client.get(f"/api/messages?run_id={run_id}").json()
        assert len(msgs) >= 2
        assert all(m["run_id"] == run_id for m in msgs)

    def test_filter_by_sender_returns_correct_agent(self, client, pfi_run):
        run_id = pfi_run["run_id"]
        msgs = client.get(
            f"/api/messages?run_id={run_id}&agent=Support Intake Agent"
        ).json()
        assert len(msgs) >= 1
        for m in msgs:
            assert (m["sender_agent"] == "Support Intake Agent"
                    or m["receiver_agent"] == "Support Intake Agent")

    def test_messages_returned_in_order(self, client, pfi_run):
        """Messages should be in ascending ID order (chronological)."""
        msgs = client.get(f"/api/runs/{pfi_run['run_id']}/messages").json()
        ids = [m["id"] for m in msgs]
        assert ids == sorted(ids), "Messages are not in ascending ID order"

    def test_message_count_matches_detail_field(self, client, pfi_run):
        """The message_count in run detail must equal the actual messages returned."""
        run_id = pfi_run["run_id"]
        detail   = client.get(f"/api/runs/{run_id}").json()
        messages = client.get(f"/api/runs/{run_id}/messages").json()
        assert detail["message_count"] == len(messages)
