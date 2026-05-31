from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, JSON, String

from app.database import Base


# Status literals — validated by Pydantic schema; stored as plain String for SQLite compat.
# Valid values: "pending" | "running" | "completed" | "failed" | "cancelled"


class WorkflowRun(Base):
    """
    A single execution instance of a Workflow.

    `started_at` / `completed_at` are set by the runtime, not at row creation,
    so they are nullable with no Python default.
    """

    __tablename__ = "workflow_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    workflow_id = Column(
        Integer,
        ForeignKey("workflows.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    status = Column(String(50), nullable=False, default="pending")

    # Arbitrary JSON payload sent to start the run
    input_payload = Column(JSON, nullable=True)

    # Final result/output from the run
    output_payload = Column(JSON, nullable=True)

    total_tokens = Column(Integer, nullable=True)
    estimated_cost = Column(Float, nullable=True)

    # Set by runtime when execution begins / ends
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
