from sqlalchemy import Boolean, Column, DateTime, Integer, JSON, String, Text

from app.database import Base
from app.utils import utcnow


class Agent(Base):
    """
    Represents a configurable AI agent.

    JSON columns (tools, channels, guardrails, limits) are stored as TEXT in
    SQLite and automatically serialized/deserialized by SQLAlchemy's JSON type.
    """

    __tablename__ = "agents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False, unique=True, index=True)
    role = Column(String(255), nullable=False)
    system_prompt = Column(Text, nullable=False, default="")
    model = Column(String(100), nullable=False, default="claude-sonnet-4-6")

    # List of tool identifiers, e.g. ["web_search", "calculator"]
    tools = Column(JSON, nullable=False, default=list)

    # List of channel identifiers, e.g. ["internal", "telegram"]
    channels = Column(JSON, nullable=False, default=list)

    memory_enabled = Column(Boolean, nullable=False, default=False)

    # Flexible dict for guardrail config, e.g. {"block_topics": ["violence"]}
    guardrails = Column(JSON, nullable=False, default=dict)

    # Flexible dict for operational limits, e.g. {"max_iterations": 10, "max_tokens": 4096}
    limits = Column(JSON, nullable=False, default=dict)

    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)
