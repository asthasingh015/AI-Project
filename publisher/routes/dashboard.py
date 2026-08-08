"""Dashboard API: high-level publishing status for demos and monitoring."""

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from publisher.database import get_db
from publisher.models import Post, PostStatus
from publisher.scheduler import scheduler_manager
from publisher.schemas import DashboardResponse, to_post_out
from publisher.services.publisher import publisher

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/dashboard", response_model=DashboardResponse)
async def get_dashboard(db: AsyncSession = Depends(get_db)) -> DashboardResponse:
    """Return publishing statistics and scheduler state."""
    total = (
        await db.execute(select(func.count()).select_from(Post))
    ).scalar_one()

    published = (
        await db.execute(
            select(func.count())
            .select_from(Post)
            .where(Post.status == PostStatus.PUBLISHED.value)
        )
    ).scalar_one()

    pending = (
        await db.execute(
            select(func.count())
            .select_from(Post)
            .where(Post.status == PostStatus.PENDING.value)
        )
    ).scalar_one()

    failed = (
        await db.execute(
            select(func.count())
            .select_from(Post)
            .where(Post.status == PostStatus.FAILED.value)
        )
    ).scalar_one()

    today_start = datetime.now().date()
    posts_today = (
        await db.execute(
            select(func.count())
            .select_from(Post)
            .where(
                Post.status == PostStatus.PUBLISHED.value,
                func.date(Post.published_at) >= today_start,
            )
        )
    ).scalar_one()

    latest = (
        await db.execute(
            select(Post)
            .where(Post.status == PostStatus.PUBLISHED.value)
            .order_by(Post.published_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    return DashboardResponse(
        total_posts=total,
        published=published,
        pending=pending,
        failed=failed,
        posts_today=posts_today,
        scheduler_status=scheduler_manager.status,
        next_publish_time=scheduler_manager.next_run_time,
        last_publish_time=(
            to_post_out(latest).published_at if latest else None
        ),
        latest_post=to_post_out(latest) if latest else None,
        last_run_time=publisher.state.last_run_time,
        last_run_success=publisher.state.last_run_success,
        last_run_error=publisher.state.last_run_error,
    )
