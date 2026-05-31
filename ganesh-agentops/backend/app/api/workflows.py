from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.workflow import Workflow
from app.models.workflow_run import WorkflowRun
from app.schemas.workflow import WorkflowCreate, WorkflowRead, WorkflowUpdate
from app.schemas.workflow_run import RunWorkflowRequest, WorkflowRunQueued

router = APIRouter(prefix="/api/workflows", tags=["workflows"])


# ── helpers ───────────────────────────────────────────────────────────────────

def _get_or_404(workflow_id: int, db: Session) -> Workflow:
    wf = db.get(Workflow, workflow_id)
    if wf is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow with id={workflow_id} not found.",
        )
    return wf


# Overridable in tests so the background task uses the same DB as the test client.
# Set to a sessionmaker factory; None means "use the default SessionLocal".
_bg_session_factory = None


def _run_in_background(run_id: int, input_data: dict) -> None:
    """
    Execute a workflow in a background thread with its own DB session.
    Called via FastAPI BackgroundTasks — runs after the HTTP response is sent.
    """
    from app.database import SessionLocal
    from app.runtime.agent_runtime import AgentRuntime
    from app.runtime.event_bus import bus

    factory = _bg_session_factory or SessionLocal
    db = factory()
    try:
        run = db.get(WorkflowRun, run_id)
        if run is None:
            bus.publish(run_id, "workflow_error", f"Run {run_id} not found in DB")
            return
        AgentRuntime(db).execute(run, input_data)
    except Exception as exc:
        import traceback
        try:
            bus.publish(run_id, "workflow_error",
                        f"Unexpected error: {exc}",
                        metadata={"traceback": traceback.format_exc()[:800]})
        except Exception:
            pass
    finally:
        db.close()


# ── CRUD ──────────────────────────────────────────────────────────────────────

@router.get("", response_model=list[WorkflowRead], summary="List workflows")
def list_workflows(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    return (
        db.query(Workflow)
        .order_by(Workflow.created_at.desc())
        .offset(skip).limit(limit).all()
    )


@router.post("", response_model=WorkflowRead, status_code=201, summary="Create a workflow")
def create_workflow(payload: WorkflowCreate, db: Session = Depends(get_db)):
    wf = Workflow(**payload.model_dump())
    db.add(wf)
    db.commit()
    db.refresh(wf)
    return wf


@router.get("/{workflow_id}", response_model=WorkflowRead, summary="Get a workflow")
def get_workflow(workflow_id: int, db: Session = Depends(get_db)):
    return _get_or_404(workflow_id, db)


@router.put("/{workflow_id}", response_model=WorkflowRead, summary="Update a workflow")
def update_workflow(workflow_id: int, payload: WorkflowUpdate, db: Session = Depends(get_db)):
    wf = _get_or_404(workflow_id, db)
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=422, detail="Request body must contain at least one field.")
    for k, v in updates.items():
        setattr(wf, k, v)
    db.commit()
    db.refresh(wf)
    return wf


@router.delete("/{workflow_id}", status_code=204, summary="Delete a workflow")
def delete_workflow(workflow_id: int, db: Session = Depends(get_db)):
    wf = _get_or_404(workflow_id, db)
    db.delete(wf)
    db.commit()


# ── Run (non-blocking) ────────────────────────────────────────────────────────

@router.post(
    "/{workflow_id}/run",
    response_model=WorkflowRunQueued,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger a workflow run",
    description=(
        "Creates a WorkflowRun record (status=pending) and starts execution in a "
        "background task. Returns immediately with the run_id and SSE URL. "
        "Connect to `events_url` for real-time progress, or poll `poll_url` for status."
    ),
)
def run_workflow(
    workflow_id: int,
    payload: RunWorkflowRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    wf = _get_or_404(workflow_id, db)

    run = WorkflowRun(
        workflow_id=wf.id,
        status="pending",
        input_payload=payload.model_dump(exclude_none=True),
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    # Schedule workflow execution AFTER the response is sent
    background_tasks.add_task(
        _run_in_background,
        run.id,
        payload.model_dump(exclude_none=True),
    )

    return WorkflowRunQueued(
        run_id=run.id,
        workflow_id=wf.id,
        workflow_name=wf.name,
        status="pending",
        events_url=f"/api/runs/{run.id}/events",
        poll_url=f"/api/runs/{run.id}",
        message=(
            f"Run #{run.id} queued for workflow '{wf.name}'. "
            f"Stream live events at /api/runs/{run.id}/events "
            f"or poll status at /api/runs/{run.id}."
        ),
    )
