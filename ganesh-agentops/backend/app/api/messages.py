"""
Cross-run message query endpoint.

  GET /api/messages  – query messages with optional filters

Per-run messages are also available at GET /api/runs/{run_id}/messages.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.message import Message

router = APIRouter(prefix="/api/messages", tags=["messages"])


@router.get("", summary="Query persisted agent messages")
def list_messages(
    run_id: int | None = Query(default=None, description="Filter by run"),
    agent: str | None = Query(default=None, description="Filter by sender or receiver agent name"),
    channel: str | None = Query(default=None, description="Filter by channel (internal/telegram/…)"),
    message_type: str | None = Query(default=None, description="Filter by type (text/tool_call/…)"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    q = db.query(Message)
    if run_id is not None:
        q = q.filter(Message.run_id == run_id)
    if agent:
        q = q.filter(
            (Message.sender_agent == agent) | (Message.receiver_agent == agent)
        )
    if channel:
        q = q.filter(Message.channel == channel)
    if message_type:
        q = q.filter(Message.message_type == message_type)

    msgs = q.order_by(Message.id.desc()).offset(skip).limit(limit).all()
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
