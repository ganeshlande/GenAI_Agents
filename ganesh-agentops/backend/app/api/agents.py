"""
Agent management endpoints.

  GET    /api/agents           – list agents (newest first, paginated)
  POST   /api/agents           – create an agent
  GET    /api/agents/{id}      – get a single agent
  PUT    /api/agents/{id}      – partial update
  DELETE /api/agents/{id}      – delete
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.agent import Agent
from app.schemas.agent import AgentCreate, AgentRead, AgentUpdate

router = APIRouter(prefix="/api/agents", tags=["agents"])


# ── helpers ──────────────────────────────────────────────────────────────────

def _get_or_404(agent_id: int, db: Session) -> Agent:
    agent = db.get(Agent, agent_id)
    if agent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent with id={agent_id} not found.",
        )
    return agent


def _handle_name_conflict(name: str) -> None:
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=f"An agent named '{name}' already exists. Names must be unique.",
    )


# ── endpoints ─────────────────────────────────────────────────────────────────

@router.get(
    "",
    response_model=list[AgentRead],
    summary="List agents",
    description="Return all agents ordered by creation date (newest first). Supports pagination via `skip` / `limit`.",
)
def list_agents(
    skip: int = Query(default=0, ge=0, description="Records to skip"),
    limit: int = Query(default=100, ge=1, le=500, description="Max records to return"),
    db: Session = Depends(get_db),
):
    return (
        db.query(Agent)
        .order_by(Agent.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


@router.post(
    "",
    response_model=AgentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create an agent",
)
def create_agent(payload: AgentCreate, db: Session = Depends(get_db)):
    agent = Agent(**payload.model_dump())
    db.add(agent)
    try:
        db.commit()
        db.refresh(agent)
    except IntegrityError:
        db.rollback()
        _handle_name_conflict(payload.name)
    return agent


@router.get(
    "/{agent_id}",
    response_model=AgentRead,
    summary="Get a single agent",
)
def get_agent(agent_id: int, db: Session = Depends(get_db)):
    return _get_or_404(agent_id, db)


@router.put(
    "/{agent_id}",
    response_model=AgentRead,
    summary="Update an agent",
    description="Partial update — only fields present in the request body are changed.",
)
def update_agent(
    agent_id: int,
    payload: AgentUpdate,
    db: Session = Depends(get_db),
):
    agent = _get_or_404(agent_id, db)

    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(
            status_code=422,
            detail="Request body must contain at least one field to update.",
        )

    for field, value in updates.items():
        setattr(agent, field, value)

    try:
        db.commit()
        db.refresh(agent)
    except IntegrityError:
        db.rollback()
        _handle_name_conflict(updates.get("name", ""))
    return agent


@router.delete(
    "/{agent_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an agent",
)
def delete_agent(agent_id: int, db: Session = Depends(get_db)):
    agent = _get_or_404(agent_id, db)
    db.delete(agent)
    db.commit()
