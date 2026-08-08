"""Manual publish API.

``POST /api/publish`` enqueues approved topics from the Discovery layer
and processes the queue immediately, reusing the exact same pipeline as
the scheduler. It never accepts arbitrary topics directly.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from publisher.database import get_db
from publisher.schemas import PostOut, PublishResponse
from publisher.services.publisher import publisher
from publisher.utils.logger import get_logger

router = APIRouter(prefix="/api", tags=["publish"])

logger = get_logger("publisher.routes.publish")


@router.post("/publish", response_model=PublishResponse)
async def manual_publish(db: AsyncSession = Depends(get_db)) -> PublishResponse:
    """Run one manual publishing cycle (for demos and testing)."""
    try:
        result = await publisher.manual_publish(db)
    except Exception as exc:
        logger.error("Manual publish failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "Publishing pipeline failed. Check the Discovery / Brain "
                "APIs and the AI provider configuration."
            ),
        ) from exc

    return PublishResponse(
        enqueued=result["enqueued"],
        published=len(result["published"]),
        posts=[PostOut.model_validate(post) for post in result["published"]],
    )
