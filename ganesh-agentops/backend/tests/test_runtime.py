"""
Runtime tests — all run in pure mock mode (no API key required).
"""

import pytest
from sqlalchemy.orm import Session

from app.database import engine, init_db
from app.models.agent import Agent
from app.models.workflow import Workflow
from app.models.workflow_run import WorkflowRun
from app.models.message import Message
from app.models.runtime_log import RuntimeLog
from app.seed.workflow_templates import WORKFLOW_TEMPLATES


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module", autouse=True)
def ensure_schema():
    init_db()


@pytest.fixture
def db():
    from app.database import SessionLocal
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def pfi_workflow(db: Session) -> Workflow:
    """Create (or reuse) the Payment Failure Investigation workflow."""
    tmpl = WORKFLOW_TEMPLATES["payment_failure_investigation"]
    wf = Workflow(
        name="__test_PFI__",
        description=tmpl["description"],
        nodes=tmpl["nodes"],
        edges=tmpl["edges"],
        template_type="payment_failure_investigation",
    )
    db.add(wf)
    db.commit()
    db.refresh(wf)
    yield wf
    db.delete(wf)
    db.commit()


@pytest.fixture
def seeded_agents(db: Session):
    """Ensure the 4 default agents exist for the test run."""
    from app.seed.seed_data import seed_agents
    seed_agents(db=db)
    yield
    # Leave agents — cleaned up by the test-db teardown in conftest


# ── Unit tests: individual runtime components ─────────────────────────────────

class TestMockLLM:
    def test_intake_extracts_payment_id(self):
        from app.runtime.graph_builder import MockLLM
        llm = MockLLM()
        r = llm.complete("You are a Support Intake Specialist.",
                         [{"role": "user", "content": "payment PAY-10291 failed"}],
                         ["ticket_creator"], {})
        assert "PAY-10291" in r["content"]
        assert r["extracted_data_updates"]["payment_id"] == "PAY-10291"
        assert r["input_tokens"] > 0

    def test_investigator_sets_fraud_false(self):
        from app.runtime.graph_builder import MockLLM
        llm = MockLLM()
        r = llm.complete("You are a Payment Investigation Specialist.",
                         [{"role": "user", "content": "investigate PAY-10291"}],
                         ["payment_lookup"],
                         {"extracted_data": {"payment_id": "PAY-10291"}})
        assert r["fraud_detected"] is False
        assert r["extracted_data_updates"]["confidence_score"] == 0.95

    def test_risk_returns_score(self):
        from app.runtime.graph_builder import MockLLM
        llm = MockLLM()
        r = llm.complete("You are a Risk and Compliance Analyst.",
                         [{"role": "user", "content": "check risk"}],
                         ["risk_check"],
                         {"extracted_data": {"payment_id": "PAY-10291"}})
        assert r["risk_score"] == 28

    def test_resolution_marks_final(self):
        from app.runtime.graph_builder import MockLLM
        llm = MockLLM()
        r = llm.complete("You are a Customer Resolution Specialist.",
                         [{"role": "user", "content": "resolve"}],
                         ["ticket_creator"],
                         {"extracted_data": {"payment_id": "PAY-10291", "root_cause": "CARD_DECLINED"}})
        assert r.get("is_final") is True
        assert "Resolution Summary" in r["content"]


class TestCostTracker:
    def test_mock_model_zero_cost(self):
        from app.runtime.cost_tracker import CostTracker
        ct = CostTracker()
        cost = ct.track("agent", "mock", 1000, 500)
        assert cost == 0.0
        assert ct.total_cost() == 0.0

    def test_sonnet_pricing(self):
        from app.runtime.cost_tracker import CostTracker
        ct = CostTracker()
        ct.track("agent", "claude-sonnet-4-6", 1_000_000, 1_000_000)
        assert ct.total_cost() == pytest.approx(3.0 + 15.0, rel=1e-4)

    def test_summary_structure(self):
        from app.runtime.cost_tracker import CostTracker
        ct = CostTracker()
        ct.track("a1", "mock", 100, 50)
        ct.track("a2", "mock", 200, 75)
        s = ct.summary()
        assert s["total_tokens"] == 425
        assert len(s["per_agent"]) == 2


class TestGuardrails:
    def test_blocked_topic(self):
        from app.runtime.guardrails import check_guardrails
        r = check_guardrails({"block_topics": ["competitor_pricing"]},
                             "Their competitor pricing is lower")
        assert not r.allowed
        assert "competitor_pricing" in r.reason

    def test_passes_clean_content(self):
        from app.runtime.guardrails import check_guardrails
        r = check_guardrails({"block_topics": ["violence"]}, "Payment processed successfully.")
        assert r.allowed

    def test_truncates_long_response(self):
        from app.runtime.guardrails import check_guardrails
        r = check_guardrails({"max_response_length_chars": 20}, "A" * 100)
        assert r.allowed
        assert len(r.final_content) <= 60  # includes truncation marker


class TestToolRegistry:
    def test_payment_lookup_deterministic(self):
        from app.tools.registry import execute_tool
        r = execute_tool("payment_lookup", payment_id="PAY-10291")
        assert r["payment_id"] == "PAY-10291"
        assert r["error_code"] == "CARD_DECLINED"

    def test_risk_check_low_score(self):
        from app.tools.registry import execute_tool
        r = execute_tool("risk_check", payment_id="PAY-10291")
        assert r["risk_score"] == 28
        assert r["risk_level"] == "low"

    def test_ticket_creator_returns_id(self):
        from app.tools.registry import execute_tool
        r = execute_tool("ticket_creator", payment_id="PAY-10291", issue_type="test")
        assert r["ticket_id"].startswith("TKT-")

    def test_unknown_tool_returns_error(self):
        from app.tools.registry import execute_tool
        r = execute_tool("nonexistent_tool")
        assert "error" in r


class TestFallbackGraph:
    def test_sequential_execution(self):
        from app.runtime.fallback_graph import StateGraph, END
        g = StateGraph()

        # Nodes return DELTAS only — the fallback (and LangGraph) appends them.
        def node_a(state):
            return {"visited": ["A"], "value": 1}

        def node_b(state):
            return {"visited": ["B"], "value": 2}

        g.add_node("a", node_a)
        g.add_node("b", node_b)
        g.set_entry_point("a")
        g.add_edge("a", "b")
        g.add_edge("b", END)

        result = g.compile().invoke({"visited": [], "value": 0})
        assert result["visited"] == ["A", "B"]
        assert result["value"] == 2

    def test_conditional_routing_true(self):
        from app.runtime.fallback_graph import StateGraph, END
        g = StateGraph()

        g.add_node("start", lambda s: {"flag": True})
        g.add_node("branch_yes", lambda s: {"result": "yes"})
        g.add_node("branch_no", lambda s: {"result": "no"})
        g.set_entry_point("start")
        g.add_conditional_edges("start",
                                lambda s: "yes" if s.get("flag") else "no",
                                {"yes": "branch_yes", "no": "branch_no"})
        g.add_edge("branch_yes", END)
        g.add_edge("branch_no", END)

        result = g.compile().invoke({"flag": False, "result": ""})
        assert result["result"] == "yes"

    def test_list_appended_not_replaced(self):
        from app.runtime.fallback_graph import StateGraph, END
        g = StateGraph()
        g.add_node("n", lambda s: {"items": ["b"]})
        g.set_entry_point("n")
        g.add_edge("n", END)
        result = g.compile().invoke({"items": ["a"]})
        assert result["items"] == ["a", "b"]


# ── Integration test: full pipeline via HTTP ──────────────────────────────────

def test_full_pfi_pipeline_via_api(client, db_session):
    """
    End-to-end: seed agents + workflow → POST /run (non-blocking) → poll for
    completion → verify messages, logs, and event bus artefacts.
    """
    from app.seed.seed_data import seed_agents, seed_workflows

    seed_agents(db=db_session)
    seed_workflows(db=db_session)

    wfs = client.get("/api/workflows").json()
    pfi = next((w for w in wfs if w["template_type"] == "payment_failure_investigation"), None)
    assert pfi is not None, "PFI workflow not seeded"

    # ── Trigger (non-blocking, returns 202 immediately) ───────────────────────
    r = client.post(
        f"/api/workflows/{pfi['id']}/run",
        json={"message": "Payment PAY-10291 failed for a customer in Brazil. Please investigate."},
    )
    assert r.status_code == 202, r.text
    queued = r.json()
    assert queued["status"] == "pending"
    run_id = queued["run_id"]

    # BackgroundTasks run synchronously inside TestClient before this line
    run_detail = client.get(f"/api/runs/{run_id}").json()
    assert run_detail["status"] == "completed", f"Expected completed, got: {run_detail}"

    # ── Output ────────────────────────────────────────────────────────────────
    output = run_detail["output"]
    assert output is not None
    assert "final_output" in output
    assert "PAY-10291" in output["final_output"]
    assert output["cost_summary"]["total_tokens"] > 0

    # ── Messages (via /api/runs/{run_id}/messages) ────────────────────────────
    msgs = client.get(f"/api/runs/{run_id}/messages").json()
    assert len(msgs) >= 2
    agents_seen = {m["sender_agent"] for m in msgs}
    assert len(agents_seen) >= 2

    # ── Logs (via /api/runs/{run_id}/logs) ───────────────────────────────────
    logs = client.get(f"/api/runs/{run_id}/logs").json()
    event_types = {l["event_type"] for l in logs}
    assert "workflow_start" in event_types
    assert "workflow_end" in event_types
    assert "agent_start" in event_types

    # ── Event bus ────────────────────────────────────────────────────────────
    from app.runtime.event_bus import bus
    events = bus.get_events(run_id)
    assert len(events) >= 5, "At minimum: wf_start, agent_start×2, agent_end×2, wf_end"
    bus_types = {e.event_type for e in events}
    assert "workflow_start" in bus_types
    assert "workflow_end" in bus_types
    assert "agent_message" in bus_types
    assert bus.is_terminal(run_id)


def test_run_without_api_key_uses_mock(client, db_session):
    """Confirm mock mode is used when no API keys are set."""
    from app.runtime.graph_builder import _get_llm, MockLLM
    llm = _get_llm("claude-sonnet-4-6")
    assert isinstance(llm, MockLLM), "Expected MockLLM when no API keys configured"


def test_run_workflow_not_found(client):
    r = client.post("/api/workflows/99999/run", json={"message": "test"})
    assert r.status_code == 404
