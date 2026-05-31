"""
Main workflow executor.
Loads the workflow, builds the graph, runs it, and persists every artefact.
"""

import traceback

from sqlalchemy.orm import Session

from app.models.workflow import Workflow
from app.models.workflow_run import WorkflowRun
from app.runtime.cost_tracker import CostTracker
from app.runtime.event_bus import bus
from app.runtime.graph_builder import build_graph
from app.runtime.memory import persist_log
from app.utils import utcnow


class AgentRuntime:
    def __init__(self, db: Session):
        self.db = db

    # ── Public API ────────────────────────────────────────────────────────────

    def execute(self, run: WorkflowRun, input_payload: dict) -> dict:
        """
        Synchronously execute a workflow run.

        Updates ``run`` (status, timestamps, output, token counts) and returns
        the final output dict.  The caller is responsible for the surrounding
        HTTP response.
        """
        workflow = self.db.get(Workflow, run.workflow_id)
        if not workflow:
            return self._fail(run, f"Workflow id={run.workflow_id} not found")

        run.status = "running"
        run.started_at = utcnow()
        self.db.commit()

        bus.publish(run.id, "workflow_start",
                    f"Workflow '{workflow.name}' started",
                    metadata={"workflow_id": workflow.id,
                              "node_count": len(workflow.nodes or [])})
        persist_log(self.db, run.id, "info", "workflow_start",
                    f"Workflow '{workflow.name}' started",
                    {"workflow_id": workflow.id,
                     "node_count": len(workflow.nodes or []),
                     "input_keys": list(input_payload.keys())})

        try:
            cost_tracker = CostTracker()
            graph = build_graph(workflow, run, self.db, cost_tracker)

            input_message = (
                input_payload.get("message")
                or input_payload.get("input")
                or str(input_payload)
            )

            initial_state: dict = {
                "run_id": run.id,
                "workflow_id": workflow.id,
                "input_message": input_message,
                "messages": [],
                "tool_results": [],
                "agent_outputs": {},
                "extracted_data": {},
                "fraud_detected": False,
                "risk_score": 0,
                "final_output": "",
                "error": None,
                "total_input_tokens": 0,
                "total_output_tokens": 0,
                # Per-agent step counters used by the step-limit guardrail
                "agent_steps": {},
            }

            final_state = graph.invoke(initial_state)

            # Persist results
            total_tokens = (
                final_state.get("total_input_tokens", 0)
                + final_state.get("total_output_tokens", 0)
            )
            run.status = "completed"
            run.completed_at = utcnow()
            run.total_tokens = total_tokens
            run.estimated_cost = cost_tracker.total_cost()
            run.output_payload = {
                "final_output": final_state.get("final_output", ""),
                "agent_outputs": final_state.get("agent_outputs", {}),
                "extracted_data": final_state.get("extracted_data", {}),
                "cost_summary": cost_tracker.summary(),
            }
            self.db.commit()

            persist_log(self.db, run.id, "info", "workflow_end",
                        f"Workflow completed — {total_tokens} tokens, "
                        f"${cost_tracker.total_cost():.6f}",
                        cost_tracker.summary())
            bus.publish(run.id, "workflow_end",
                        f"Workflow completed — {total_tokens} tokens",
                        metadata=cost_tracker.summary())

            return run.output_payload

        except Exception as exc:
            return self._fail(run, str(exc), traceback.format_exc())

    # ── Internal ──────────────────────────────────────────────────────────────

    def _fail(self, run: WorkflowRun, error: str, detail: str = "") -> dict:
        run.status = "failed"
        run.completed_at = utcnow()
        run.output_payload = {"error": error}
        self.db.commit()
        persist_log(self.db, run.id, "error", "workflow_error",
                    f"Workflow failed: {error}",
                    {"error": error, "traceback": detail[:1000]})
        bus.publish(run.id, "workflow_error", f"Workflow failed: {error}",
                    metadata={"error": error})
        return {"error": error}
