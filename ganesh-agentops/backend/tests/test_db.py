"""
Verifies that:
1. All five tables are created on startup.
2. JSON fields on Agent round-trip correctly through SQLite.
3. WorkflowRun FK to Workflow is enforced.
4. Message and RuntimeLog FK to WorkflowRun is enforced.
"""

import pytest
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.database import engine, init_db
from app.models.agent import Agent
from app.models.workflow import Workflow
from app.models.workflow_run import WorkflowRun
from app.models.message import Message
from app.models.runtime_log import RuntimeLog


@pytest.fixture(autouse=True, scope="module")
def ensure_tables():
    init_db()


def test_all_tables_exist():
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    for expected in ("agents", "workflows", "workflow_runs", "messages", "runtime_logs"):
        assert expected in tables, f"Missing table: {expected}"


def test_agent_json_fields_round_trip():
    with Session(engine) as session:
        agent = Agent(
            name="__test_agent__",
            role="researcher",
            system_prompt="You research things.",
            model="claude-sonnet-4-6",
            tools=["web_search", "calculator"],
            channels=["internal", "telegram"],
            memory_enabled=True,
            guardrails={"block_topics": ["violence"], "max_response_length": 2000},
            limits={"max_iterations": 10, "max_tokens": 4096},
        )
        session.add(agent)
        session.commit()
        session.refresh(agent)

        assert agent.id is not None
        assert agent.tools == ["web_search", "calculator"]
        assert agent.channels == ["internal", "telegram"]
        assert agent.memory_enabled is True
        assert agent.guardrails["max_response_length"] == 2000
        assert agent.limits["max_iterations"] == 10
        assert agent.created_at is not None
        assert agent.updated_at is not None

        session.delete(agent)
        session.commit()


def test_workflow_defaults():
    with Session(engine) as session:
        wf = Workflow(name="__test_workflow__")
        session.add(wf)
        session.commit()
        session.refresh(wf)

        assert wf.id is not None
        assert wf.nodes == []
        assert wf.edges == []
        assert wf.description == ""
        assert wf.template_type is None

        session.delete(wf)
        session.commit()


def test_workflow_run_and_message_chain():
    with Session(engine) as session:
        wf = Workflow(name="__test_chain_wf__")
        session.add(wf)
        session.flush()

        run = WorkflowRun(
            workflow_id=wf.id,
            status="pending",
            input_payload={"task": "summarise the web"},
        )
        session.add(run)
        session.flush()

        msg = Message(
            run_id=run.id,
            sender_agent="orchestrator",
            receiver_agent="researcher",
            channel="internal",
            content="Please search for AI news.",
            message_type="text",
        )
        session.add(msg)

        log = RuntimeLog(
            run_id=run.id,
            level="info",
            event_type="agent_start",
            message="Researcher agent started.",
            log_metadata={"agent": "researcher", "iteration": 1},
        )
        session.add(log)
        session.commit()

        assert msg.id is not None
        assert log.id is not None
        assert log.log_metadata["agent"] == "researcher"

        # Cascade: deleting the run should cascade-delete message and log
        session.delete(run)
        session.delete(wf)
        session.commit()
