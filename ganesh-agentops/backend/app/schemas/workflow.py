from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ── Workflow CRUD ─────────────────────────────────────────────────────────────

class WorkflowBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str = ""
    # React Flow node/edge shapes — kept as opaque dicts for flexibility
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    template_type: str | None = None


class WorkflowCreate(WorkflowBase):
    pass


class WorkflowUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    nodes: list[dict[str, Any]] | None = None
    edges: list[dict[str, Any]] | None = None
    template_type: str | None = None


class WorkflowRead(WorkflowBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


# ── Templates ─────────────────────────────────────────────────────────────────

class WorkflowTemplateRead(BaseModel):
    """Static template definition returned by GET /api/templates."""

    template_type: str
    name: str
    description: str
    agents: list[str]
    tools: list[str]
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]


class CreateWorkflowFromTemplateRequest(BaseModel):
    """
    Optional body for POST /api/templates/{template_type}/create-workflow.
    When omitted or empty, the template's default name/description are used.
    """

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
