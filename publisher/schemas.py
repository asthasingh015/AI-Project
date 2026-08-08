"""Pydantic API schemas for the Publisher module.

Response schemas are kept separate from the ORM models in ``models.py`` so
the API contract (``schemas.py``) can evolve independently of persistence.
"""

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict


class PostOut(BaseModel):
    """API representation of a post."""

    id: int
    title: str
    text: str
    rationale: str
    sources: list[str]
    status: str
    attempts: int
    created_at: datetime
    published_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


def _as_utc(dt: datetime | None) -> datetime | None:
    """Normalize a possibly-naive UTC datetime to timezone-aware UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def to_post_out(post) -> PostOut:
    """Convert an ORM ``Post`` row to its API schema."""
    return PostOut(
        id=post.id,
        title=post.title,
        text=post.text,
        rationale=post.rationale,
        sources=post.sources_list,
        status=post.status,
        attempts=post.attempts,
        created_at=_as_utc(post.created_at),
        published_at=_as_utc(post.published_at),
    )


class FeedResponse(BaseModel):
    """List response wrapper for the feed."""

    total: int
    posts: list[PostOut]


class StatsResponse(BaseModel):
    """Publish queue statistics."""

    published: int
    pending: int
    failed: int
    total: int


class DashboardResponse(BaseModel):
    """Single source of truth for the demo dashboard."""

    total_posts: int
    published: int
    pending: int
    failed: int
    posts_today: int
    scheduler_status: str
    next_publish_time: str | None
    last_publish_time: datetime | None
    latest_post: PostOut | None
    last_run_time: datetime | None
    last_run_success: bool | None
    last_run_error: str | None


class PublishResponse(BaseModel):
    """Outcome of a manual publish attempt."""

    enqueued: int
    published: int
    posts: list[PostOut]
