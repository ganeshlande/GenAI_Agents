from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

RunStatus = Literal["pending", "running", "completed", "failed", "cancelled"]


# ── Existing CRUD schemas ────────────────────────────────────────────────────

class WorkflowRunCreate(BaseModel):
    workflow_id: int | None = None
    input_payload: dict[str, Any] | None = None


class WorkflowRunUpdate(BaseModel):
    """Partial update used by the runtime to progress a run through its lifecycle."""

    status: RunStatus | None = None
    output_payload: dict[str, Any] | None = None
    total_tokens: int | None = None
    estimated_cost: float | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


class WorkflowRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    workflow_id: int | None
    status: str
    input_payload: dict[str, Any] | None
    output_payload: dict[str, Any] | None
    total_tokens: int | None
    estimated_cost: float | None
    started_at: datetime | None
    completed_at: datetime | None


# ── Run-trigger schemas ───────────────────────────────────────────────────────

class RunWorkflowRequest(BaseModel):
    """
    Body for POST /api/workflows/{workflow_id}/run.
    workflow_id comes from the URL path, not the body.
    """

    message: str | None = None             # natural-language prompt
    input_payload: dict[str, Any] | None = None  # structured input (also accepted)


class WorkflowRunResult(BaseModel):
    """Full response returned after synchronous execution."""

    run_id: int
    workflow_id: int
    workflow_name: str
    status: str
    output: dict[str, Any] | None
    total_tokens: int | None
    estimated_cost_usd: float | None
    duration_seconds: float | None
    message_count: int
    log_count: int


class WorkflowRunQueued(BaseModel):
    """
    Response from non-blocking POST /api/workflows/{id}/run.
    The workflow executes in a background task; connect to events_url for live updates.
    """

    run_id: int
    workflow_id: int
    workflow_name: str
    status: str           # always "pending" at response time
    events_url: str       # SSE endpoint for live monitoring
    poll_url: str         # polling endpoint for run status
    message: str


