import pytest
import os
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.database import Base, get_db

TEST_DB_PATH = "./data/test_agentops.db"
TEST_DATABASE_URL = f"sqlite:///{TEST_DB_PATH}"

os.makedirs("data", exist_ok=True)

_test_engine = create_engine(
    TEST_DATABASE_URL, connect_args={"check_same_thread": False}
)
_TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=_test_engine)


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    Base.metadata.create_all(bind=_test_engine)
    yield
    Base.metadata.drop_all(bind=_test_engine)
    _test_engine.dispose()  # release all connections before deleting (required on Windows)
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)


def _override_get_db():
    db = _TestingSession()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def db_session():
    """Yields a raw SQLAlchemy session bound to the test database."""
    db = _TestingSession()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def _patch_bg_session_factory():
    """
    Redirect background-task DB sessions to the test database so that
    POST /run background execution writes to the same DB the test client reads.
    """
    import app.api.workflows as wf_module
    wf_module._bg_session_factory = _TestingSession
    yield
    wf_module._bg_session_factory = None


@pytest.fixture
def client():
    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
