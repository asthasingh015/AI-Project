"""Feed API: returns every published post, newest first."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from publisher.database import get_db
from publisher.models import Post, PostStatus
from publisher.schemas import FeedResponse, to_post_out

router = APIRouter(prefix="/api/agent", tags=["feed"])


@router.get("/feed", response_model=FeedResponse)
async def get_feed(db: AsyncSession = Depends(get_db)) -> FeedResponse:
    """Return all published posts, newest first."""
    result = await db.execute(
        select(Post)
        .where(Post.status == PostStatus.PUBLISHED.value)
        .order_by(Post.published_at.desc())
    )
    posts = result.scalars().all()
    return FeedResponse(
        total=len(posts),
        posts=[to_post_out(post) for post in posts],
    )
