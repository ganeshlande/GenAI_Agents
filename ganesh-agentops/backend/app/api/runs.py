"""
Run inspection and live-monitoring endpoints.

  GET  /api/runs                         – list all runs (newest first)
  GET  /api/runs/{run_id}                – run detail with counts
  GET  /api/runs/{run_id}/messages       – persisted agent messages
  GET  /api/runs/{run_id}/logs           – persisted runtime logs
  GET  /api/runs/{run_id}/events         – Server-Sent Events stream
"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.message import Message
from app.models.runtime_log import RuntimeLog
from app.models.workflow import Workflow
from app.models.workflow_run import WorkflowRun
from app.runtime.event_bus import bus

router = APIRouter(prefix="/api/runs", tags=["runs"])


# ── helpers ───────────────────────────────────────────────────────────────────

def _run_or_404(run_id: int, db: Session) -> WorkflowRun:
    run = db.get(WorkflowRun, run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run {run_id} not found.",
        )
    return run


def _run_summary(run: WorkflowRun, db: Session) -> dict:
    wf = db.get(Workflow, run.workflow_id) if run.workflow_id else None
    msg_count = db.query(Message).filter(Message.run_id == run.id).count()
    log_count = db.query(RuntimeLog).filter(RuntimeLog.run_id == run.id).count()
    duration = None
    if run.started_at and run.completed_at:
        duration = round((run.completed_at - run.started_at).total_seconds(), 3)
    return {
        "run_id": run.id,
        "workflow_id": run.workflow_id,
        "workflow_name": wf.name if wf else None,
        "status": run.status,
        "total_tokens": run.total_tokens,
        "estimated_cost_usd": run.estimated_cost,
        "duration_seconds": duration,
        "message_count": msg_count,
        "log_count": log_count,
        "event_count": bus.event_count(run.id),
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "output": run.output_payload,
    }


# ── List / Get ────────────────────────────────────────────────────────────────

@router.get("", summary="List all runs (newest first)")
def list_runs(
    workflow_id: int | None = Query(default=None, description="Filter by workflow"),
    status_filter: str | None = Query(default=None, alias="status"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    q = db.query(WorkflowRun)
    if workflow_id is not None:
        q = q.filter(WorkflowRun.workflow_id == workflow_id)
    if status_filter:
        q = q.filter(WorkflowRun.status == status_filter)
    runs = q.order_by(WorkflowRun.id.desc()).offset(skip).limit(limit).all()
    return [_run_summary(r, db) for r in runs]


@router.get("/{run_id}", summary="Get run details")
def get_run(run_id: int, db: Session = Depends(get_db)):
    return _run_summary(_run_or_404(run_id, db), db)


# ── Messages & Logs ───────────────────────────────────────────────────────────

@router.get("/{run_id}/messages", summary="Persisted agent messages for a run")
def get_messages(run_id: int, db: Session = Depends(get_db)):
    _run_or_404(run_id, db)
    msgs = (
        db.query(Message)
        .filter(Message.run_id == run_id)
        .order_by(Message.id)
        .all()
    )
    return [
        {
            "id": m.id,
            "run_id": m.run_id,
            "sender_agent": m.sender_agent,
            "receiver_agent": m.receiver_agent,
            "channel": m.channel,
            "message_type": m.message_type,
            "content": m.content,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in msgs
    ]


@router.get("/{run_id}/logs", summary="Runtime logs for a run")
def get_logs(
    run_id: int,
    level: str | None = Query(default=None, description="Filter by level (info/warning/error)"),
    event_type: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    _run_or_404(run_id, db)
    q = db.query(RuntimeLog).filter(RuntimeLog.run_id == run_id)
    if level:
        q = q.filter(RuntimeLog.level == level)
    if event_type:
        q = q.filter(RuntimeLog.event_type == event_type)
    logs = q.order_by(RuntimeLog.id).all()
    return [
        {
            "id": log.id,
            "run_id": log.run_id,
            "level": log.level,
            "event_type": log.event_type,
            "message": log.message,
            "metadata": log.log_metadata,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }
        for log in logs
    ]


# ── SSE stream ────────────────────────────────────────────────────────────────

@router.get(
    "/{run_id}/events",
    summary="Server-Sent Events stream for a run",
    description=(
        "Streams all events for a run as SSE. "
        "If the run is already complete, replays stored events and closes the stream. "
        "If the run is still executing, streams live events as they arrive. "
        "Each data frame is a JSON-encoded RunEvent object."
    ),
)
async def stream_events(
    run_id: int,
    after: int = Query(default=0, ge=0, description="Skip events with event_id < after"),
    db: Session = Depends(get_db),
):
    # Verify run exists (use the DB session before entering the generator)
    run = db.get(WorkflowRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found.")

    async def generate():
        cursor = after
        max_wait = 180.0  # seconds before timeout
        elapsed = 0.0
        poll_interval = 0.15  # 150 ms
        heartbeat_ticks = 0

        # Initial ping so the client knows the connection is live
        yield f": ping run_id={run_id}\n\n"

        try:
            while elapsed < max_wait:
                new_events = bus.get_events(run_id, after=cursor)

                for evt in new_events:
                    yield evt.to_sse()
                    cursor += 1
                    if evt.event_type in ("workflow_end", "workflow_error"):
                        # Signal stream completion and exit
                        done = {"type": "stream_complete",
                                "run_id": run_id,
                                "total_events": cursor}
                        yield f"data: {json.dumps(done)}\n\n"
                        return

                # Heartbeat comment every ~5 s so proxies don't time out
                heartbeat_ticks += 1
                if heartbeat_ticks % 33 == 0:
                    yield f": heartbeat {int(elapsed)}s\n\n"

                await asyncio.sleep(poll_interval)
                elapsed += poll_interval

            # Timed out — send a timeout event and close
            timeout_evt = {"type": "timeout", "run_id": run_id,
                           "message": "SSE stream timed out after 180s"}
            yield f"data: {json.dumps(timeout_evt)}\n\n"

        except asyncio.CancelledError:
            pass  # client disconnected

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",   # prevent nginx from buffering the stream
        },
    )
