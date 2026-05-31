from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.workflow import Workflow
from app.schemas.workflow import (
    CreateWorkflowFromTemplateRequest,
    WorkflowRead,
    WorkflowTemplateRead,
)
from app.seed.workflow_templates import WORKFLOW_TEMPLATES

router = APIRouter(prefix="/api/templates", tags=["templates"])


# ── endpoints ─────────────────────────────────────────────────────────────────

@router.get(
    "",
    response_model=list[WorkflowTemplateRead],
    summary="List available workflow templates",
)
def list_templates():
    return list(WORKFLOW_TEMPLATES.values())


@router.get(
    "/{template_type}",
    response_model=WorkflowTemplateRead,
    summary="Get a single template definition",
)
def get_template(template_type: str):
    template = WORKFLOW_TEMPLATES.get(template_type)
    if template is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template '{template_type}' not found. "
                   f"Available: {list(WORKFLOW_TEMPLATES.keys())}",
        )
    return template


@router.post(
    "/{template_type}/create-workflow",
    response_model=WorkflowRead,
    status_code=status.HTTP_201_CREATED,
    summary="Instantiate a new Workflow from a template",
    description=(
        "Creates a persisted Workflow record pre-populated with the template's "
        "nodes and edges. The optional request body lets you override the name "
        "or description; omit it (or send {}) to use the template defaults."
    ),
)
def create_workflow_from_template(
    template_type: str,
    payload: CreateWorkflowFromTemplateRequest = Body(
        default=CreateWorkflowFromTemplateRequest()
    ),
    db: Session = Depends(get_db),
):
    template = WORKFLOW_TEMPLATES.get(template_type)
    if template is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template '{template_type}' not found. "
                   f"Available: {list(WORKFLOW_TEMPLATES.keys())}",
        )

    wf = Workflow(
        name=payload.name or template["name"],
        description=payload.description or template["description"],
        nodes=template["nodes"],
        edges=template["edges"],
        template_type=template_type,
    )
    db.add(wf)
    db.commit()
    db.refresh(wf)
    return wf
