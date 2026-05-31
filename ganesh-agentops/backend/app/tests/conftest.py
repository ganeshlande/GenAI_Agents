"""
Shared test fixtures for the app/tests suite.

Uses a dedicated SQLite file (data/app_tests.db) that is completely separate
from the main tests/ suite so the two suites can run together without state
collisions.

Fixtures:
  client      – TestClient with DB dependency overridden
  db_session  – raw SQLAlchemy session pointing at the test DB
  seeded      – ensures agents + workflows are seeded once per test session
  pfi_run     – triggers a full PFI run and returns the queued + completed data
"""

import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.database import Base, get_db

# ── Isolated test database ────────────────────────────────────────────────────

_TEST_DB_PATH = "./data/app_tests.db"
_TEST_DB_URL  = f"sqlite:///{_TEST_DB_PATH}"

os.makedirs("data", exist_ok=True)

_engine       = create_engine(_TEST_DB_URL, connect_args={"check_same_thread": False})
_SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


# ── Session-scoped DB lifecycle ───────────────────────────────────────────────

@pytest.fixture(scope="session", autouse=True)
def _init_test_db():
    """Create all tables once for this test session, drop them on exit."""
    Base.metadata.create_all(bind=_engine)
    yield
    Base.metadata.drop_all(bind=_engine)
    _engine.dispose()
    if os.path.exists(_TEST_DB_PATH):
        os.remove(_TEST_DB_PATH)


@pytest.fixture(autouse=True)
def _redirect_bg_sessions():
    """
    Redirect BackgroundTask DB sessions to the test DB so the workflow
    background execution writes to the same database the test client reads.
    """
    import app.api.workflows as wf_mod
    wf_mod._bg_session_factory = _SessionLocal
    yield
    wf_mod._bg_session_factory = None


# ── Per-test fixtures ─────────────────────────────────────────────────────────

def _override_get_db():
    db = _SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def db_session():
    """Raw SQLAlchemy session pointed at the isolated test DB."""
    db = _SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def client():
    """TestClient with the DB dependency overridden to use the test DB."""
    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def seeded(client, db_session):
    """Seed agents + workflows into the test DB and return them."""
    from app.seed.seed_data import seed_agents, seed_workflows
    seed_agents(db=db_session)
    seed_workflows(db=db_session)
    agents   = client.get("/api/agents").json()
    workflows = client.get("/api/workflows").json()
    return {"agents": agents, "workflows": workflows}


@pytest.fixture
def pfi_run(client, seeded):
    """
    Trigger a Payment Failure Investigation run and return a dict with both
    the queued response and the completed run detail.

    BackgroundTasks run synchronously inside TestClient, so the run is
    complete by the time the POST response is received.
    """
    wfs = seeded["workflows"]
    pfi_wf = next(w for w in wfs if w["template_type"] == "payment_failure_investigation")

    queued = client.post(
        f"/api/workflows/{pfi_wf['id']}/run",
        json={"message": "Payment PAY-10291 failed. Card declined. Please investigate."},
    ).json()

    detail = client.get(f"/api/runs/{queued['run_id']}").json()

    return {
        "queued":    queued,
        "detail":    detail,
        "run_id":    queued["run_id"],
        "workflow":  pfi_wf,
    }
