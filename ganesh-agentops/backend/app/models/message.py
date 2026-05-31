from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text

from app.database import Base
from app.utils import utcnow


# channel values:      "internal" | "telegram" | "slack" | "whatsapp"
# message_type values: "text" | "tool_call" | "tool_result" | "system" | "error"


class Message(Base):
    """
    A single message exchanged between agents or between an agent and an
    external channel during a workflow run.
    """

    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(
        Integer,
        ForeignKey("workflow_runs.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # None means the message originated from outside the system (e.g. a human)
    sender_agent = Column(String(255), nullable=True)
    receiver_agent = Column(String(255), nullable=True)

    channel = Column(String(100), nullable=False, default="internal")
    content = Column(Text, nullable=False)
    message_type = Column(String(50), nullable=False, default="text")

    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
