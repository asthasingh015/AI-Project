"""
Autonomous publishing engine for Cortex AI.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4


class PublisherEngine:
    """Creates feed-ready posts and syncs them with the API feed."""

    def __init__(
        self,
        persona_name: str,
        domain: str,
        agent_id: Optional[str] = None,
        on_publish: Optional[Any] = None,
    ) -> None:
        self.persona_name = persona_name
        self.domain = domain
        self.agent_id = agent_id
        self.on_publish = on_publish
        self._published_posts: List[Dict[str, Any]] = []

    def _utc_now(self) -> str:
        return (
            datetime.now(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
        )

    def _create_post_id(self) -> str:
        return "p-" + uuid4().hex[:12]

    def publish(
        self,
        topic: str,
        editorial_opinion: str,
        rationale: str,
        sources: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Create, store and optionally sync one published post."""

        if not topic or not topic.strip():
            raise ValueError("topic must not be empty")

        if not editorial_opinion or not editorial_opinion.strip():
            raise ValueError("editorial_opinion must not be empty")

        post = {
            "id": self._create_post_id(),
            "createdAt": self._utc_now(),
            "text": editorial_opinion,
            "rationale": rationale,
            "sources": list(sources or []),
            "topic": topic,
            "persona": self.persona_name,
            "domain": self.domain,
        }

        self._published_posts.append(post)

        # Sync published post with API feed.
        if self.on_publish is not None:
            self.on_publish(
                self.agent_id,
                post["text"],
                post["rationale"],
                post["sources"],
            )

        return post

    def get_posts(self) -> List[Dict[str, Any]]:
        """Return posts in newest-first order."""

        return sorted(
            self._published_posts,
            key=lambda post: post["createdAt"],
            reverse=True,
        )

    def has_published(self, topic: str) -> bool:
        """Check whether a topic has already been published."""

        return any(
            post.get("topic", "").strip().lower()
            == topic.strip().lower()
            for post in self._published_posts
        )

    def export(self) -> Dict[str, Any]:
        """Export publisher state."""

        return {
            "persona_name": self.persona_name,
            "domain": self.domain,
            "agent_id": self.agent_id,
            "published_count": len(self._published_posts),
            "posts": self.get_posts(),
        }