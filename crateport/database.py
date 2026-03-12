"""Database engine, session management, and cache helpers."""

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .config import config
from .models import Base

# ---------------------------------------------------------------------------
# Engine & session factory
# ---------------------------------------------------------------------------

engine = create_engine(
    config.db_url,
    echo=False,
    # SQLite-specific: allow usage across threads (needed for the OAuth callback server)
    connect_args=(
        {"check_same_thread": False} if config.db_url.startswith("sqlite") else {}
    ),
)
SessionLocal = sessionmaker(  # pylint: disable=invalid-name
    bind=engine, autoflush=True, autocommit=False, expire_on_commit=False
)


def init_db() -> None:
    """Create all tables (no-op if they already exist)."""
    Base.metadata.create_all(engine)


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """Provide a transactional database session as a context manager."""
    session: Session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------


def is_fresh(cached_at: datetime | None, ttl_hours: int | None = None) -> bool:
    """Return True if *cached_at* is within the configured TTL."""
    if cached_at is None:
        return False
    ttl = timedelta(
        hours=ttl_hours if ttl_hours is not None else config.cache_ttl_hours
    )
    now = datetime.now(timezone.utc)
    ts = (
        cached_at.replace(tzinfo=timezone.utc)
        if cached_at.tzinfo is None
        else cached_at
    )
    return (now - ts) < ttl
