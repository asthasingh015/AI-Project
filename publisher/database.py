"""Async SQLAlchemy engine, session factory, and FastAPI dependency.

The SQLite file location is derived from ``DATABASE_URL`` so no manual
directory setup is required on first boot.
"""

from collections.abc import AsyncIterator
from pathlib import Path

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from publisher.config import settings
from publisher.utils.logger import get_logger

logger = get_logger("publisher.database")


class Base(DeclarativeBase):
    """Declarative base shared by every ORM model."""


def _ensure_database_directory(database_url: str) -> None:
    """Create the parent folder of a file-backed SQLite database."""
    if database_url.startswith("sqlite"):
        path = database_url.split("///", 1)[-1]
        if path and path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)


_ensure_database_directory(settings.database_url)

engine = create_async_engine(
    settings.database_url,
    echo=False,
    future=True,
)

SessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db() -> None:
    """Create tables if they do not exist yet."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database initialized (url=%s)", settings.database_url)


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency that yields a scoped async session."""
    async with SessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
