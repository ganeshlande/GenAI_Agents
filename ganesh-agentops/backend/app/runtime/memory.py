"""Thin helpers for persisting agent messages and runtime logs to SQLite."""

from sqlalchemy.orm import Session

from app.models.message import Message
from app.models.runtime_log import RuntimeLog


def persist_message(
    db: Session,
    run_id: int,
    sender_agent: str | None,
    receiver_agent: str | None,
    content: str,
    message_type: str = "text",
    channel: str = "internal",
) -> Message:
    msg = Message(
        run_id=run_id,
        sender_agent=sender_agent,
        receiver_agent=receiver_agent,
        channel=channel,
        content=content,
        message_type=message_type,
    )
    db.add(msg)
    db.commit()
    return msg


def persist_log(
    db: Session,
    run_id: int,
    level: str,
    event_type: str,
    message: str,
    metadata: dict | None = None,
) -> RuntimeLog:
    log = RuntimeLog(
        run_id=run_id,
        level=level,
        event_type=event_type,
        message=message,
        log_metadata=metadata or {},
    )
    db.add(log)
    db.commit()
    return log
