import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.config import settings


# Ensure the parent directory for the SQLite file exists.
# Parses DATABASE_URL so the directory is correct regardless of cwd.
_db_url = settings.DATABASE_URL
if _db_url.startswith("sqlite:///"):
    _db_file = _db_url[len("sqlite:///"):]          # strip the scheme prefix
    _data_dir = os.path.dirname(_db_file)            # e.g. "./data" or "/app/data"
    if _data_dir:
        os.makedirs(_data_dir, exist_ok=True)

engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False},  # required for SQLite
    echo=settings.DEBUG,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """
    Import all ORM models (registering them with Base.metadata), then create
    any tables that do not yet exist.  Safe to call on every startup — existing
    tables and data are untouched.
    """
    import app.models  # noqa: F401 — side-effect import registers models
    Base.metadata.create_all(bind=engine)
