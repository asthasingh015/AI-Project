"""Feed fetching module for the Cortex AI Discovery Engine.

This module fetches and parses live RSS/Atom feeds configured in
sources.py. It only retrieves and normalizes feed data; filtering,
scoring, storage, and AI processing are handled by downstream modules.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import feedparser
import requests
from requests.exceptions import RequestException

from discovery.sources import (
    SourceConfig,
    SourceRegistry,
    SourceType,
    default_registry,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FetcherConfig:
    """Configuration settings for FeedFetcher."""

    timeout_seconds: float = 10.0
    user_agent: str = "CortexAI-DiscoveryEngine/1.0"
    max_articles_per_source: int = 20


class FeedFetcher:
    """Fetches and normalizes RSS/Atom feed items."""

    def __init__(self, config: Optional[FetcherConfig] = None) -> None:
        """Initialize the feed fetcher."""
        self._config = config or FetcherConfig()

        self._session = requests.Session()
        self._session.headers.update(
            {"User-Agent": self._config.user_agent}
        )

        logger.info(
            "FeedFetcher initialized "
            "(timeout=%.1fs, max_articles=%d)",
            self._config.timeout_seconds,
            self._config.max_articles_per_source,
        )

    def _download_feed(self, url: str) -> Optional[bytes]:
        """Download raw feed content."""
        try:
            response = self._session.get(
                url,
                timeout=self._config.timeout_seconds,
            )
        except RequestException as exc:
            logger.warning(
                "Request failed for '%s': %s",
                url,
                exc,
            )
            return None

        if response.status_code != 200:
            logger.warning(
                "Non-200 response for '%s': HTTP %d",
                url,
                response.status_code,
            )
            return None

        if not response.content:
            logger.warning(
                "Empty response body for '%s'",
                url,
            )
            return None

        return response.content

    def _extract_published(self, entry: Any) -> Optional[str]:
        """Extract and normalize publication date."""
        time_struct = (
            getattr(entry, "published_parsed", None)
            or getattr(entry, "updated_parsed", None)
        )

        if not time_struct:
            return None

        try:
            dt = datetime(
                *time_struct[:6],
                tzinfo=timezone.utc,
            )
            return dt.isoformat()
        except (TypeError, ValueError) as exc:
            logger.debug(
                "Failed to parse published date: %s",
                exc,
            )
            return None

    def _extract_description(self, entry: Any) -> str:
        """Extract description or summary from an entry."""
        description = (
            getattr(entry, "summary", "")
            or getattr(entry, "description", "")
        )

        return description.strip() if description else ""

    def _build_article_id(
        self,
        url: str,
        title: str,
        source_name: str,
    ) -> str:
        """Build a stable identifier for deduplication."""
        if url:
            return url.strip().lower()

        return (
            f"{title.strip().lower()}::"
            f"{source_name.strip().lower()}"
        )

    def _normalize_entry(
        self,
        entry: Any,
        source: SourceConfig,
    ) -> Optional[Dict[str, Any]]:
        """Convert a feed entry into a normalized dictionary."""
        title = getattr(entry, "title", "").strip()
        url = getattr(entry, "link", "").strip()

        if not url:
            logger.debug(
                "Discarding entry with missing URL "
                "from source '%s'",
                source.name,
            )
            return None

        return {
            "title": title,
            "url": url,
            "description": self._extract_description(entry),
            "published": self._extract_published(entry),
            "source_name": source.name,
            "source_url": source.url,
            "category": source.category.value,
            "priority": source.priority.value,
            "tags": list(source.tags),
        }

    def fetch_source(
        self,
        source: SourceConfig,
    ) -> List[Dict[str, Any]]:
        """Fetch articles from a single source."""
        if source.source_type not in (
            SourceType.RSS,
            SourceType.ATOM,
        ):
            logger.warning(
                "Unsupported source_type '%s' "
                "for source '%s'; skipping.",
                source.source_type,
                source.name,
            )
            return []

        raw_content = self._download_feed(source.url)

        if raw_content is None:
            return []

        try:
            parsed = feedparser.parse(raw_content)
        except Exception as exc:
            logger.warning(
                "Failed to parse feed for source '%s': %s",
                source.name,
                exc,
            )
            return []

        if getattr(parsed, "bozo", False):
            logger.debug(
                "Feed for source '%s' reported parsing issues: %s",
                source.name,
                getattr(
                    parsed,
                    "bozo_exception",
                    "unknown issue",
                ),
            )

        entries = getattr(parsed, "entries", None)

        if not entries:
            logger.info(
                "No entries found for source '%s'.",
                source.name,
            )
            return []

        seen_ids: set[str] = set()
        articles: List[Dict[str, Any]] = []

        for entry in entries:
            normalized = self._normalize_entry(
                entry,
                source,
            )

            if normalized is None:
                continue

            article_id = self._build_article_id(
                normalized["url"],
                normalized["title"],
                source.name,
            )

            if article_id in seen_ids:
                continue

            seen_ids.add(article_id)
            articles.append(normalized)

            if (
                len(articles)
                >= self._config.max_articles_per_source
            ):
                break

        logger.info(
            "Fetched %d article(s) from source '%s'.",
            len(articles),
            source.name,
        )

        return articles

    def fetch_all(
        self,
        sources: Optional[List[SourceConfig]] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch articles from multiple sources."""
        if not sources:
            logger.info(
                "fetch_all called with no sources; returning []."
            )
            return []

        seen_ids: set[str] = set()
        combined: List[Dict[str, Any]] = []

        for source in sources:
            try:
                source_articles = self.fetch_source(source)
            except Exception as exc:
                logger.error(
                    "Unexpected error fetching source '%s': %s",
                    source.name,
                    exc,
                )
                continue

            for article in source_articles:
                article_id = self._build_article_id(
                    article["url"],
                    article["title"],
                    article["source_name"],
                )

                if article_id in seen_ids:
                    continue

                seen_ids.add(article_id)
                combined.append(article)

        logger.info(
            "fetch_all completed: %d source(s) processed, "
            "%d unique article(s) collected.",
            len(sources),
            len(combined),
        )

        return combined

    def fetch_enabled(
        self,
        registry: Optional[SourceRegistry] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch articles from all enabled sources."""
        active_registry = registry or default_registry

        enabled_sources = (
            active_registry.get_enabled_sources()
        )

        logger.info(
            "fetch_enabled: %d enabled source(s) found.",
            len(enabled_sources),
        )

        return self.fetch_all(enabled_sources)

    def close(self) -> None:
        """Close the HTTP session."""
        self._session.close()
        logger.info("FeedFetcher session closed.")

    def __enter__(self) -> "FeedFetcher":
        """Support context-manager usage."""
        return self

    def __exit__(
        self,
        exc_type: Any,
        exc_val: Any,
        exc_tb: Any,
    ) -> None:
        """Close the fetcher when leaving context manager."""
        self.close()

    def __repr__(self) -> str:
        """Return developer-friendly representation."""
        return (
            f"FeedFetcher("
            f"timeout={self._config.timeout_seconds!r}, "
            f"max_articles_per_source="
            f"{self._config.max_articles_per_source!r})"
        )


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s "
            "[%(levelname)s] "
            "%(name)s: %(message)s"
        ),
    )

    demo_fetcher = FeedFetcher(
        FetcherConfig(
            timeout_seconds=10.0,
            max_articles_per_source=5,
        )
    )

    try:
        results = demo_fetcher.fetch_enabled()

        print(
            f"Fetched {len(results)} unique article(s) total."
        )

        for item in results[:5]:
            print(
                f"- [{item['source_name']}] "
                f"{item['title']}"
            )

    finally:
        demo_fetcher.close()