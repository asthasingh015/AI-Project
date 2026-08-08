"""Statistics API: published / pending / failed counts for the queue."""

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from publisher.database import get_db
from publisher.models import Post, PostStatus
from publisher.schemas import StatsResponse

router = APIRouter(prefix="/api", tags=["stats"])


@router.get("/stats", response_model=StatsResponse)
async def get_stats(db: AsyncSession = Depends(get_db)) -> StatsResponse:
    """Return counts of posts by lifecycle status."""
    counts: dict[str, int] = {
        status.value: 0 for status in PostStatus
    }

    rows = await db.execute(
        select(Post.status, func.count()).group_by(Post.status)
    )
    for status_value, count in rows.all():
        counts[status_value] = count

    return StatsResponse(
        published=counts[PostStatus.PUBLISHED.value],
        pending=counts[PostStatus.PENDING.value],
        failed=counts[PostStatus.FAILED.value],
        total=sum(counts.values()),
    )
