"""ORM models for the Publisher module.

The ``Post`` model doubles as the publish queue: approved topics are
inserted as ``pending`` rows and drained by the scheduler or the manual
publish endpoint. A ``failed`` row is eligible for retry until
``attempts`` reaches ``max_attempts``.

``sources`` is persisted as a JSON string (plain SQLite ``Text``) and
exposed as a list through ``sources_list``. API response schemas live in
``schemas.py``.
"""

import json
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from publisher.database import Base


def utcnow() -> datetime:
    """Timezone-aware UTC now (no deprecated ``datetime.utcnow``)."""
    return datetime.now(timezone.utc)


class PostStatus(str, Enum):
    """Lifecycle state of a post in the publish queue."""

    PENDING = "pending"
    PUBLISHED = "published"
    FAILED = "failed"


class Post(Base):
    """A single autonomous publication / queue item."""

    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    rationale: Mapped[str] = mapped_column(Text, nullable=False, default="")
    sources: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=PostStatus.PENDING.value, index=True
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True, nullable=False
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    next_retry_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    @property
    def sources_list(self) -> list[str]:
        """Parse the JSON ``sources`` column into a list of URLs."""
        try:
            value = json.loads(self.sources or "[]")
            return value if isinstance(value, list) else []
        except (TypeError, ValueError):
            return []
