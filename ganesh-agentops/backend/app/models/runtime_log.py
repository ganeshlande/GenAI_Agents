from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, Text

from app.database import Base
from app.utils import utcnow


# level values:      "debug" | "info" | "warning" | "error"
# event_type values: "agent_start" | "agent_end" | "tool_call" | "tool_result" |
#                    "message_sent" | "workflow_start" | "workflow_end" | "error"


class RuntimeLog(Base):
    """
    Structured log entry emitted by the agent runtime during a workflow run.

    The DB column is named "metadata"; the Python attribute is `log_metadata`
    to avoid shadowing SQLAlchemy's DeclarativeBase.metadata class attribute.
    """

    __tablename__ = "runtime_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(
        Integer,
        ForeignKey("workflow_runs.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    level = Column(String(20), nullable=False, default="info")
    event_type = Column(String(100), nullable=True)
    message = Column(Text, nullable=False)

    # Mapped to DB column "metadata"; Python attribute avoids shadowing Base.metadata
    log_metadata = Column("metadata", JSON, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
