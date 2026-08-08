"""Central autonomous publishing workflow for the Publisher module.

The scheduler and the manual ``POST /api/publish`` endpoint both delegate
to this service. Publishing logic lives here and only here -- never
duplicated.

Workflow:
    approved topic(s) -> publish queue -> persona -> AI generation
        -> persist as published (with 3-attempt retry on failure)
"""

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from publisher.config import settings
from publisher.generator import ProviderConfigurationError, generate_post
from publisher.models import Post, PostStatus, utcnow
from publisher.utils.logger import get_logger

logger = get_logger("publisher.service")


class SchedulerState:
    """In-memory state describing the latest publishing cycle.

    Kept outside the database so the dashboard stays readable even before
    the first successful cycle.
    """

    def __init__(self) -> None:
        self.last_run_time: datetime | None = None
        self.last_run_success: bool | None = None
        self.last_run_error: str | None = None

    def mark_start(self) -> None:
        self.last_run_time = datetime.now(timezone.utc)

    def mark_success(self) -> None:
        self.last_run_success = True
        self.last_run_error = None

    def mark_failure(self, error: str) -> None:
        self.last_run_success = False
        self.last_run_error = error


@dataclass
class CycleResult:
    """Outcome of one publishing cycle."""

    enqueued: int = 0
    published: int = 0
    failed: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "enqueued": self.enqueued,
            "published": self.published,
            "failed": self.failed,
        }


class Publisher:
    """Implements the complete autonomous publishing pipeline."""

    def __init__(self) -> None:
        self.state = SchedulerState()

    # ------------------------------------------------------------------ #
    # Public entry points
    # ------------------------------------------------------------------ #

    async def run_cycle(self, session: AsyncSession) -> CycleResult:
        """Run one scheduler tick: enqueue approved topics, drain the queue."""
        self.state.mark_start()
        try:
            enqueued = await self._enqueue_approved_topics(session)
            published = await self._process_pending_queue(
                session, limit=settings.publication_batch_size
            )
            self.state.mark_success()
            result = CycleResult(
                enqueued=enqueued,
                published=len(published),
                failed=0,
            )
            logger.info(
                "Cycle finished enqueued=%s published=%s",
                result.enqueued,
                result.published,
            )
            return result
        except ProviderConfigurationError as exc:
            self.state.mark_failure(str(exc))
            logger.error("AI provider configuration error: %s", exc)
            raise
        except Exception as exc:
            self.state.mark_failure(str(exc))
            logger.exception("Publishing cycle failed")
            raise

    async def manual_publish(self, session: AsyncSession) -> dict[str, Any]:
        """Enqueue approved topics and process them immediately.

        Used by ``POST /api/publish`` for demos and testing.
        """
        self.state.mark_start()
        try:
            enqueued = await self._enqueue_approved_topics(session)
            published = await self._process_pending_queue(
                session, limit=settings.queue_batch_size
            )
            self.state.mark_success()
            logger.info(
                "Manual publish finished enqueued=%s published=%s",
                enqueued,
                len(published),
            )
            return {
                "enqueued": enqueued,
                "published": [self._as_dict(post) for post in published],
            }
        except ProviderConfigurationError as exc:
            self.state.mark_failure(str(exc))
            logger.error("AI provider configuration error: %s", exc)
            raise
        except Exception as exc:
            self.state.mark_failure(str(exc))
            logger.exception("Manual publish failed")
            raise

    # ------------------------------------------------------------------ #
    # Publish queue
    # ------------------------------------------------------------------ #

    async def _enqueue_approved_topics(self, session: AsyncSession) -> int:
        """Fetch approved topics and insert new ones as pending queue items."""
        topics = await self._fetch_approved_topics()
        if not topics:
            logger.info("No approved topics available; nothing to enqueue")
            return 0

        enqueued = 0
        for topic in topics[: settings.queue_batch_size]:
            title = str(topic.get("title") or "").strip()
            if not title:
                continue
            if await self._exists_in_queue(session, title):
                logger.info("Skipping duplicate queued title=%r", title)
                continue

            post = Post(
                title=title,
                description=str(topic.get("description") or "").strip(),
                sources=json.dumps(
                    topic.get("sources") or [], ensure_ascii=False
                ),
                status=PostStatus.PENDING.value,
            )
            session.add(post)
            enqueued += 1
            logger.info("Enqueued approved topic title=%r", title)

        await session.commit()
        return enqueued

    async def _exists_in_queue(self, session: AsyncSession, title: str) -> bool:
        """Whether a pending or published post already uses this title."""
        normalized = title.strip().lower()
        result = await session.execute(
            select(Post).where(
                Post.title == title,
                Post.status.in_(
                    [PostStatus.PENDING.value, PostStatus.PUBLISHED.value]
                ),
            )
        )
        for existing in result.scalars().all():
            if existing.title.strip().lower() == normalized:
                return True
        return False

    async def _process_pending_queue(
        self, session: AsyncSession, limit: int
    ) -> list[Post]:
        """Process due pending queue items with 3-attempt retry."""
        now = utcnow()
        result = await session.execute(
            select(Post)
            .where(
                Post.status == PostStatus.PENDING.value,
                or_(Post.next_retry_at.is_(None), Post.next_retry_at <= now),
            )
            .order_by(Post.created_at.asc())
            .limit(limit)
        )
        items = list(result.scalars().all())
        if not items:
            return []

        try:
            persona = await self._fetch_persona()
        except Exception as exc:
            # Infrastructure failure: record it as a failed attempt for every
            # due item so retry accounting stays consistent. Items remain
            # pending and retry on the next cycle.
            logger.error(
                "Persona fetch failed; marking %s item(s) for retry: %s",
                len(items),
                exc,
            )
            for post in items:
                self._mark_retry_or_failed(post, exc)
            await session.commit()
            return []

        published: list[Post] = []

        for post in items:
            try:
                generation = await generate_post(
                    {
                        "title": post.title,
                        "description": post.description,
                        "sources": post.sources_list,
                    },
                    persona,
                )
                self._mark_published(post, generation)
                published.append(post)
                logger.info("Published post id=%s title=%r", post.id, post.title)
            except ProviderConfigurationError:
                raise
            except Exception as exc:
                self._mark_retry_or_failed(post, exc)
            await session.commit()

        return published

    def _mark_published(self, post: Post, generation: dict) -> None:
        """Apply a successful generation to the queue item."""
        post.text = generation.get("text") or ""
        post.rationale = generation.get("rationale") or ""
        post.sources = json.dumps(
            generation.get("sources") or [], ensure_ascii=False
        )
        post.status = PostStatus.PUBLISHED.value
        post.attempts += 1
        post.last_error = None
        post.published_at = utcnow()
        post.next_retry_at = None

    def _mark_retry_or_failed(self, post: Post, exc: Exception) -> None:
        """Record a failed attempt, scheduling a retry until max attempts."""
        post.attempts += 1
        post.last_error = str(exc)

        if post.attempts >= settings.publish_max_attempts:
            post.status = PostStatus.FAILED.value
            post.next_retry_at = None
            logger.error(
                "Post id=%s failed permanently after %s attempts: %s",
                post.id,
                post.attempts,
                exc,
            )
        else:
            backoff = settings.retry_backoff_seconds * post.attempts
            post.next_retry_at = utcnow() + timedelta(seconds=backoff)
            logger.warning(
                "Post id=%s failed (attempt %s/%s), retrying in %ss: %s",
                post.id,
                post.attempts,
                settings.publish_max_attempts,
                backoff,
                exc,
            )

    # ------------------------------------------------------------------ #
    # Member 2 integration (approved topics)
    # ------------------------------------------------------------------ #

    async def _fetch_approved_topics(self) -> list[dict]:
        """Fetch and normalize approved topics from the Discovery layer."""
        logger.info("Fetching approved topics from %s", settings.member2_topics_url)
        try:
            async with httpx.AsyncClient(
                timeout=settings.request_timeout_seconds
            ) as client:
                response = await client.get(settings.member2_topics_url)
                response.raise_for_status()
                payload = response.json()
        except (httpx.TimeoutException, httpx.RequestError) as exc:
            logger.error(
                "Approved topic fetch failed (network/timeout): %s", exc
            )
            raise
        except Exception as exc:
            logger.error("Approved topic fetch failed (invalid response): %s", exc)
            raise

        topics = self._normalize_topics(payload)
        logger.info("Received %s approved topic(s)", len(topics))
        return topics

    def _normalize_topics(self, payload: Any) -> list[dict]:
        """Accept the documented topic payload plus reasonable variations."""
        if not isinstance(payload, dict):
            return []

        topics: list[dict] = []

        if isinstance(payload.get("topic"), dict):
            topics.append(payload["topic"])
        elif isinstance(payload.get("topics"), list):
            topics.extend(
                item for item in payload["topics"] if isinstance(item, dict)
            )
        elif payload.get("title"):
            topics.append(payload)

        normalized: list[dict] = []
        for data in topics:
            title = str(data.get("title") or "").strip()
            if not title:
                continue
            description = str(data.get("description") or "").strip()
            sources = data.get("sources") or []
            if not isinstance(sources, list):
                sources = []
            normalized.append(
                {
                    "title": title,
                    "description": description,
                    "sources": [
                        str(s).strip() for s in sources if str(s).strip()
                    ],
                }
            )
        return normalized

    # ------------------------------------------------------------------ #
    # Member 1 integration (persona)
    # ------------------------------------------------------------------ #

    async def _fetch_persona(self) -> dict:
        """Fetch and normalize the current persona from the Brain layer."""
        logger.info("Fetching persona from %s", settings.member1_persona_url)
        try:
            async with httpx.AsyncClient(
                timeout=settings.request_timeout_seconds
            ) as client:
                response = await client.get(settings.member1_persona_url)
                response.raise_for_status()
                payload = response.json()
        except (httpx.TimeoutException, httpx.RequestError) as exc:
            logger.error("Persona fetch failed (network/timeout): %s", exc)
            raise
        except Exception as exc:
            logger.error("Persona fetch failed (invalid response): %s", exc)
            raise

        persona = self._normalize_persona(payload)
        logger.info("Received persona name=%r", persona.get("name"))
        return persona

    def _normalize_persona(self, payload: Any) -> dict:
        """Accept the documented persona payload plus reasonable variations."""
        if not isinstance(payload, dict):
            return {}
        data = (
            payload.get("persona")
            if isinstance(payload.get("persona"), dict)
            else payload
        )
        if not isinstance(data, dict):
            return {}
        return {
            "name": str(data.get("name") or "Nova"),
            "role": str(data.get("role") or "AI Technology Thinker"),
            "tone": str(data.get("tone") or "analytical"),
            "style": str(data.get("style") or "concise and insightful"),
            "values": data.get("values") if isinstance(data.get("values"), list) else [],
            "opinions": (
                data.get("opinions")
                if isinstance(data.get("opinions"), list)
                else []
            ),
        }

    # ------------------------------------------------------------------ #
    # Serialization helper
    # ------------------------------------------------------------------ #

    @staticmethod
    def _as_dict(post: Post) -> dict[str, Any]:
        """Lightweight dict serialization for API responses."""
        return {
            "id": post.id,
            "title": post.title,
            "text": post.text,
            "rationale": post.rationale,
            "sources": post.sources_list,
            "status": post.status,
            "attempts": post.attempts,
            "created_at": post.created_at,
            "published_at": post.published_at,
        }


publisher = Publisher()
