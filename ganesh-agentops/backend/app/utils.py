from datetime import datetime, timezone


def utcnow() -> datetime:
    """Return current UTC time. Used as SQLAlchemy column default."""
    return datetime.now(timezone.utc)
