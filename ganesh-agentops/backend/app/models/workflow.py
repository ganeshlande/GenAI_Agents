from sqlalchemy import Column, DateTime, Integer, JSON, String, Text

from app.database import Base
from app.utils import utcnow


class Workflow(Base):
    """
    A named multi-agent workflow graph.

    `nodes` and `edges` follow the React Flow schema so the frontend canvas
    can render them directly without transformation.
    """

    __tablename__ = "workflows"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=False, default="")

    # React Flow node list: [{"id": "1", "type": "agentNode", "data": {...}, "position": {...}}]
    nodes = Column(JSON, nullable=False, default=list)

    # React Flow edge list: [{"id": "e1-2", "source": "1", "target": "2"}]
    edges = Column(JSON, nullable=False, default=list)

    # Pre-built template identifier, e.g. "research_pipeline", "code_review"
    template_type = Column(String(100), nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)
