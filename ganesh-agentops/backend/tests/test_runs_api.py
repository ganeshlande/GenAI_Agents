"""
Tests for:
  GET  /api/runs
  GET  /api/runs/{run_id}
  GET  /api/runs/{run_id}/messages
  GET  /api/runs/{run_id}/logs
  GET  /api/runs/{run_id}/events   (SSE — verified for correct headers / content-type)
  GET  /api/messages
"""

import pytest


# ── helpers ───────────────────────────────────────────────────────────────────

def _seed_and_run(client, db_session) -> dict:
    """Seed data, trigger a PFI run, return the queued response."""
    from app.seed.seed_data import seed_agents, seed_workflows

    seed_agents(db=db_session)
    seed_workflows(db=db_session)

    wfs = client.get("/api/workflows").json()
    pfi = next(w for w in wfs if w["template_type"] == "payment_failure_investigation")

    r = client.post(
        f"/api/workflows/{pfi['id']}/run",
        json={"message": "PAY-10291 failed. Investigate."},
    )
    assert r.status_code == 202
    return r.json()


# ── /api/runs ─────────────────────────────────────────────────────────────────

def test_list_runs_empty(client):
    r = client.get("/api/runs")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_list_runs_after_execution(client, db_session):
    queued = _seed_and_run(client, db_session)
    runs = client.get("/api/runs").json()
    run_ids = [r["run_id"] for r in runs]
    assert queued["run_id"] in run_ids


def test_list_runs_filter_by_status(client, db_session):
    _seed_and_run(client, db_session)
    completed = client.get("/api/runs?status=completed").json()
    assert all(r["status"] == "completed" for r in completed)


def test_list_runs_pagination(client, db_session):
    _seed_and_run(client, db_session)
    r = client.get("/api/runs?skip=0&limit=1")
    assert r.status_code == 200
    assert len(r.json()) <= 1


# ── /api/runs/{run_id} ────────────────────────────────────────────────────────

def test_get_run_not_found(client):
    r = client.get("/api/runs/99999")
    assert r.status_code == 404


def test_get_run_detail_structure(client, db_session):
    queued = _seed_and_run(client, db_session)
    run_id = queued["run_id"]

    r = client.get(f"/api/runs/{run_id}")
    assert r.status_code == 200
    body = r.json()

    for field in ("run_id", "status", "total_tokens", "message_count",
                  "log_count", "event_count", "output"):
        assert field in body, f"Missing field: {field}"

    assert body["status"] == "completed"
    assert body["total_tokens"] > 0
    assert body["message_count"] >= 2
    assert body["log_count"] >= 3
    assert body["event_count"] >= 4


def test_get_run_output_contains_payment_id(client, db_session):
    queued = _seed_and_run(client, db_session)
    run = client.get(f"/api/runs/{queued['run_id']}").json()
    final = run["output"]["final_output"]
    assert "PAY-10291" in final


# ── /api/runs/{run_id}/messages ───────────────────────────────────────────────

def test_run_messages_not_found(client):
    r = client.get("/api/runs/99999/messages")
    assert r.status_code == 404


def test_run_messages_structure(client, db_session):
    queued = _seed_and_run(client, db_session)
    msgs = client.get(f"/api/runs/{queued['run_id']}/messages").json()
    assert len(msgs) >= 2
    for m in msgs:
        assert "sender_agent" in m
        assert "content" in m
        assert "created_at" in m


def test_run_messages_agents_participated(client, db_session):
    queued = _seed_and_run(client, db_session)
    msgs = client.get(f"/api/runs/{queued['run_id']}/messages").json()
    agents = {m["sender_agent"] for m in msgs}
    # PFI without fraud: Intake, Investigator, Resolution should appear
    assert "Support Intake Agent" in agents
    assert "Resolution Agent" in agents


# ── /api/runs/{run_id}/logs ───────────────────────────────────────────────────

def test_run_logs_not_found(client):
    r = client.get("/api/runs/99999/logs")
    assert r.status_code == 404


def test_run_logs_contain_lifecycle_events(client, db_session):
    queued = _seed_and_run(client, db_session)
    logs = client.get(f"/api/runs/{queued['run_id']}/logs").json()
    event_types = {l["event_type"] for l in logs}
    assert "workflow_start" in event_types
    assert "workflow_end" in event_types
    assert "agent_start" in event_types
    assert "agent_end" in event_types
    assert "tool_call" in event_types


def test_run_logs_filter_by_level(client, db_session):
    queued = _seed_and_run(client, db_session)
    info_logs = client.get(f"/api/runs/{queued['run_id']}/logs?level=info").json()
    assert all(l["level"] == "info" for l in info_logs)


def test_run_logs_filter_by_event_type(client, db_session):
    queued = _seed_and_run(client, db_session)
    agent_starts = client.get(
        f"/api/runs/{queued['run_id']}/logs?event_type=agent_start"
    ).json()
    assert len(agent_starts) >= 2
    assert all(l["event_type"] == "agent_start" for l in agent_starts)


# ── /api/runs/{run_id}/events (SSE) ──────────────────────────────────────────

def test_sse_endpoint_not_found(client):
    r = client.get("/api/runs/99999/events")
    assert r.status_code == 404


def test_sse_endpoint_returns_event_stream(client, db_session):
    queued = _seed_and_run(client, db_session)
    run_id = queued["run_id"]

    # Read the full SSE response synchronously (run is already complete)
    with client.stream("GET", f"/api/runs/{run_id}/events") as r:
        assert r.status_code == 200
        assert "text/event-stream" in r.headers["content-type"]

        raw = b""
        for chunk in r.iter_bytes():
            raw += chunk
            if b"stream_complete" in raw:
                break

    text = raw.decode("utf-8", errors="replace")
    assert "data:" in text
    assert "workflow_start" in text or "agent_start" in text


def test_sse_events_contain_required_fields(client, db_session):
    """Parse SSE frames and verify every event has the required fields."""
    import json as _json

    queued = _seed_and_run(client, db_session)
    run_id = queued["run_id"]

    with client.stream("GET", f"/api/runs/{run_id}/events") as r:
        raw = b""
        for chunk in r.iter_bytes():
            raw += chunk
            if b"stream_complete" in raw:
                break

    parsed = []
    for line in raw.decode("utf-8", errors="replace").splitlines():
        line = line.strip()
        if line.startswith("data:"):
            payload = line[len("data:"):].strip()
            try:
                parsed.append(_json.loads(payload))
            except _json.JSONDecodeError:
                pass

    # Filter actual run events (not stream_complete meta-event)
    run_events = [e for e in parsed if "event_id" in e]
    assert len(run_events) >= 3

    for evt in run_events:
        assert "run_id" in evt
        assert "event_id" in evt
        assert "timestamp" in evt
        assert "event_type" in evt
        assert "content" in evt


def test_event_bus_populated_after_run(client, db_session):
    from app.runtime.event_bus import bus

    queued = _seed_and_run(client, db_session)
    run_id = queued["run_id"]

    events = bus.get_events(run_id)
    assert len(events) >= 5
    types = {e.event_type for e in events}
    assert "workflow_start" in types
    assert "agent_start" in types
    assert "agent_message" in types
    assert "tool_call" in types
    assert "tool_result" in types
    assert "workflow_end" in types
    assert bus.is_terminal(run_id)


# ── /api/messages ─────────────────────────────────────────────────────────────

def test_list_messages_no_filter(client, db_session):
    _seed_and_run(client, db_session)
    r = client.get("/api/messages")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_list_messages_filter_by_run(client, db_session):
    queued = _seed_and_run(client, db_session)
    run_id = queued["run_id"]
    msgs = client.get(f"/api/messages?run_id={run_id}").json()
    assert len(msgs) >= 2
    assert all(m["run_id"] == run_id for m in msgs)


def test_list_messages_filter_by_agent(client, db_session):
    queued = _seed_and_run(client, db_session)
    run_id = queued["run_id"]
    msgs = client.get(
        f"/api/messages?run_id={run_id}&agent=Support Intake Agent"
    ).json()
    assert len(msgs) >= 1
    for m in msgs:
        assert (
            m["sender_agent"] == "Support Intake Agent"
            or m["receiver_agent"] == "Support Intake Agent"
        )


def test_list_messages_filter_by_channel(client, db_session):
    _seed_and_run(client, db_session)
    msgs = client.get("/api/messages?channel=internal").json()
    assert all(m["channel"] == "internal" for m in msgs)
