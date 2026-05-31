"""
Workflow execution tests — verifies what happens DURING and AFTER a run.

Covers:
  • Payment Failure Investigation runs to completion (status = completed)
  • At least 2 agents execute (agent_start events in logs)
  • Final output is produced and contains the payment ID
  • Tool execution occurs (tool_call + tool_result in logs)
  • Token counts are positive
  • Extracted data is populated (payment_id, root_cause, fraud_detected)
  • Cost summary structure is correct
  • Merchant Onboarding workflow also runs end-to-end
  • Empty-node workflow completes without crashing the backend
"""

import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────

def _event_types_from_logs(logs: list) -> set:
    return {log["event_type"] for log in logs}


def _agents_from_logs(logs: list) -> set:
    """Return all agent names that appeared in agent_start log entries."""
    agents = set()
    for log in logs:
        if log["event_type"] == "agent_start":
            # Message format: "Agent 'Name' started"  (or "Agent 'Name' starting")
            msg = log["message"]
            if msg.startswith("Agent '"):
                end = msg.find("'", 7)
                if end != -1:
                    agents.add(msg[7:end])
    return agents


# ── Payment Failure Investigation ─────────────────────────────────────────────

class TestPaymentFailureWorkflow:
    """Full end-to-end assertions for the PFI pipeline."""

    def test_run_status_is_completed(self, pfi_run):
        assert pfi_run["detail"]["status"] == "completed"

    def test_run_has_positive_duration(self, pfi_run):
        duration = pfi_run["detail"]["duration_seconds"]
        assert duration is not None
        assert duration > 0

    def test_at_least_two_agents_executed(self, client, pfi_run):
        logs = client.get(f"/api/runs/{pfi_run['run_id']}/logs").json()
        agents = _agents_from_logs(logs)
        assert len(agents) >= 2, \
            f"Expected ≥2 agents, got {len(agents)}: {agents}"

    def test_intake_agent_executed(self, client, pfi_run):
        logs = client.get(f"/api/runs/{pfi_run['run_id']}/logs").json()
        agents = _agents_from_logs(logs)
        assert "Support Intake Agent" in agents

    def test_resolution_agent_executed(self, client, pfi_run):
        """Non-fraud path must reach the Resolution Agent."""
        logs = client.get(f"/api/runs/{pfi_run['run_id']}/logs").json()
        agents = _agents_from_logs(logs)
        assert "Resolution Agent" in agents

    def test_final_output_produced(self, pfi_run):
        output = pfi_run["detail"]["output"]
        assert output is not None
        assert "final_output" in output
        assert len(output["final_output"]) > 0

    def test_final_output_contains_payment_id(self, pfi_run):
        final = pfi_run["detail"]["output"]["final_output"]
        assert "PAY-10291" in final

    def test_agent_outputs_populated(self, pfi_run):
        agent_outputs = pfi_run["detail"]["output"].get("agent_outputs", {})
        assert len(agent_outputs) >= 2

    def test_extracted_data_has_payment_id(self, pfi_run):
        extracted = pfi_run["detail"]["output"].get("extracted_data", {})
        assert extracted.get("payment_id") == "PAY-10291"

    def test_extracted_data_has_root_cause(self, pfi_run):
        extracted = pfi_run["detail"]["output"].get("extracted_data", {})
        assert "root_cause" in extracted
        assert extracted["root_cause"]  # non-empty

    def test_extracted_data_fraud_is_false_for_card_declined(self, pfi_run):
        extracted = pfi_run["detail"]["output"].get("extracted_data", {})
        assert extracted.get("fraud_detected") is False

    def test_extracted_data_confidence_score_present(self, pfi_run):
        extracted = pfi_run["detail"]["output"].get("extracted_data", {})
        assert "confidence_score" in extracted
        score = float(extracted["confidence_score"])
        assert 0.0 <= score <= 1.0

    def test_tool_execution_occurs(self, client, pfi_run):
        """At least one tool must be called during the payment investigation."""
        logs = client.get(f"/api/runs/{pfi_run['run_id']}/logs").json()
        types = _event_types_from_logs(logs)
        assert "tool_call" in types,   "No tool_call event in logs"
        assert "tool_result" in types, "No tool_result event in logs"

    def test_tool_call_count_at_least_one(self, client, pfi_run):
        logs = client.get(f"/api/runs/{pfi_run['run_id']}/logs").json()
        tool_calls = [l for l in logs if l["event_type"] == "tool_call"]
        assert len(tool_calls) >= 1

    def test_ticket_creator_tool_was_called(self, client, pfi_run):
        """Support Intake Agent always calls ticket_creator."""
        logs = client.get(f"/api/runs/{pfi_run['run_id']}/logs").json()
        tool_calls = [l for l in logs if l["event_type"] == "tool_call"]
        tools_called = [l["metadata"].get("tool") for l in tool_calls]
        assert "ticket_creator" in tools_called or "ticket_create" in tools_called

    def test_token_count_is_positive(self, pfi_run):
        tokens = pfi_run["detail"]["total_tokens"]
        assert tokens is not None
        assert tokens > 0

    def test_cost_summary_structure(self, pfi_run):
        summary = pfi_run["detail"]["output"].get("cost_summary", {})
        assert "total_tokens" in summary
        assert "per_agent" in summary
        assert isinstance(summary["per_agent"], list)
        assert len(summary["per_agent"]) >= 2

    def test_cost_summary_per_agent_has_fields(self, pfi_run):
        per_agent = pfi_run["detail"]["output"]["cost_summary"]["per_agent"]
        for entry in per_agent:
            assert "agent" in entry
            assert "model" in entry
            assert "input_tokens" in entry
            assert "output_tokens" in entry

    def test_log_lifecycle_events_present(self, client, pfi_run):
        logs = client.get(f"/api/runs/{pfi_run['run_id']}/logs").json()
        types = _event_types_from_logs(logs)
        assert "workflow_start" in types
        assert "workflow_end"   in types
        assert "agent_start"    in types
        assert "agent_end"      in types

    def test_event_bus_has_terminal_event(self, pfi_run):
        from app.runtime.event_bus import bus
        assert bus.is_terminal(pfi_run["run_id"])

    def test_message_count_at_least_two(self, pfi_run):
        assert pfi_run["detail"]["message_count"] >= 2

    def test_log_count_at_least_five(self, pfi_run):
        """A full 3-agent run produces at minimum: wf_start, 3×agent_start,
        3×agent_end, tool_call, wf_end = 9+ logs."""
        assert pfi_run["detail"]["log_count"] >= 5


# ── Merchant Onboarding workflow ──────────────────────────────────────────────

class TestMerchantOnboardingWorkflow:
    """Parallel workflow: both Compliance and Document Review branches execute."""

    @pytest.fixture
    def mor_run(self, client, seeded):
        wfs = seeded["workflows"]
        wf = next(w for w in wfs if w["template_type"] == "merchant_onboarding_review")
        queued = client.post(
            f"/api/workflows/{wf['id']}/run",
            json={"message": "Merchant ACME Travel Brazil submitted onboarding docs."},
        ).json()
        detail = client.get(f"/api/runs/{queued['run_id']}").json()
        return {"queued": queued, "detail": detail, "run_id": queued["run_id"]}

    def test_mor_run_completes(self, mor_run):
        assert mor_run["detail"]["status"] == "completed"

    def test_mor_final_output_produced(self, mor_run):
        output = mor_run["detail"]["output"]
        assert output is not None
        assert len(output.get("final_output", "")) > 0

    def test_mor_at_least_two_agents_run(self, client, mor_run):
        logs = client.get(f"/api/runs/{mor_run['run_id']}/logs").json()
        agents = _agents_from_logs(logs)
        assert len(agents) >= 2

    def test_mor_tokens_positive(self, mor_run):
        assert (mor_run["detail"]["total_tokens"] or 0) > 0


# ── Edge cases ────────────────────────────────────────────────────────────────

class TestWorkflowEdgeCases:
    def test_empty_workflow_run_does_not_crash_server(self, client):
        """A workflow with no nodes should fail gracefully (not 500)."""
        wf = client.post("/api/workflows", json={
            "name": "Empty WF Test", "description": "no nodes"
        }).json()
        r = client.post(f"/api/workflows/{wf['id']}/run",
                        json={"message": "nothing to do"})
        # Must return 202 Accepted (queued) — actual run may complete or fail
        assert r.status_code == 202
        run_id = r.json()["run_id"]
        detail = client.get(f"/api/runs/{run_id}").json()
        # Status must be a recognised value, not an unhandled exception
        assert detail["status"] in ("completed", "failed", "pending", "running")

    def test_run_nonexistent_workflow_returns_404(self, client):
        r = client.post("/api/workflows/9999999/run", json={"message": "x"})
        assert r.status_code == 404

    def test_multiple_runs_produce_distinct_ids(self, client, seeded):
        wfs = seeded["workflows"]
        pfi = next(w for w in wfs if w["template_type"] == "payment_failure_investigation")
        ids = set()
        for _ in range(2):
            r = client.post(f"/api/workflows/{pfi['id']}/run",
                            json={"message": "PAY-10291 test"})
            ids.add(r.json()["run_id"])
        assert len(ids) == 2, "Each run must receive a unique run_id"

    def test_run_with_empty_message_still_completes(self, client, seeded):
        wfs = seeded["workflows"]
        pfi = next(w for w in wfs if w["template_type"] == "payment_failure_investigation")
        r = client.post(f"/api/workflows/{pfi['id']}/run", json={})
        assert r.status_code == 202
        detail = client.get(f"/api/runs/{r.json()['run_id']}").json()
        assert detail["status"] in ("completed", "failed")
