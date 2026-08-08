"""
Cortex AI Discovery Engine - Article Fetcher Module

Module: fetcher.py
Purpose:
    Fetches articles from configured RSS/Atom feeds and converts them
    into a normalized article dictionary format consumed by filter.py.

Design goals:
    - Multiple RSS/Atom sources
    - Defensive parsing
    - Duplicate-safe results
    - Configurable limits
    - No mutation of external data
    - Graceful handling of broken feeds
    - Logging for debugging and production monitoring
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional, Set

import feedparser


logger = logging.getLogger(__name__)


@dataclass
class FeedSource:
    """Configuration for one RSS/Atom article source."""

    name: str
    url: str
    category: str = "General"
    priority: int = 3
    tags: List[str] = field(default_factory=list)


@dataclass
class FetcherConfig:
    """Configuration for article fetching."""

    max_articles_per_source: int = 20
    timeout: float = 15.0
    remove_duplicates: bool = True
    user_agent: str = "Cortex-AI-Discovery-Engine/1.0"

    sources: List[FeedSource] = field(default_factory=list)


class ArticleFetcher:
    """
    Fetches and normalizes RSS/Atom articles.

    Output contract:

    {
        "title": str,
        "url": str,
        "description": str,
        "published": str,
        "source_name": str,
        "source_url": str,
        "category": str,
        "priority": int,
        "tags": list[str]
    }
    """

    def __init__(self, config: Optional[FetcherConfig] = None) -> None:
        """Initialize the article fetcher."""

        self.config = config or FetcherConfig()

        logger.info(
            "ArticleFetcher initialized with %d configured source(s).",
            len(self.config.sources),
        )

    @staticmethod
    def _clean_text(value: Any) -> str:
        """Safely convert a value to clean text."""

        if value is None:
            return ""

        try:
            return str(value).strip()
        except Exception:
            return ""

    @staticmethod
    def _normalize_published(entry: Any) -> str:
        """
        Extract and normalize publication timestamp.

        Returns ISO-8601 UTC timestamp when possible.
        """

        try:
            published_parsed = entry.get("published_parsed")

            if published_parsed:
                dt = datetime(
                    published_parsed.tm_year,
                    published_parsed.tm_mon,
                    published_parsed.tm_mday,
                    published_parsed.tm_hour,
                    published_parsed.tm_min,
                    published_parsed.tm_sec,
                    tzinfo=timezone.utc,
                )

                return dt.isoformat()

            published = (
                entry.get("published")
                or entry.get("updated")
                or entry.get("created")
                or ""
            )

            published = str(published).strip()

            if not published:
                return ""

            return published

        except Exception as err:
            logger.debug(
                "Unable to normalize publication timestamp: %s",
                err,
            )
            return ""

    @staticmethod
    def _extract_tags(entry: Any, source_tags: List[str]) -> List[str]:
        """Extract tags/categories from an RSS/Atom entry."""

        tags: List[str] = []

        try:
            if isinstance(source_tags, list):
                tags.extend(
                    str(tag).strip()
                    for tag in source_tags
                    if str(tag).strip()
                )

            entry_tags = entry.get("tags") or []

            if isinstance(entry_tags, list):
                for tag in entry_tags:
                    if isinstance(tag, dict):
                        term = tag.get("term")

                        if term:
                            clean_term = str(term).strip()

                            if clean_term:
                                tags.append(clean_term)

            # Remove duplicate tags while preserving order.
            unique_tags: List[str] = []
            seen: Set[str] = set()

            for tag in tags:
                key = tag.lower()

                if key not in seen:
                    seen.add(key)
                    unique_tags.append(tag)

            return unique_tags

        except Exception as err:
            logger.debug("Error extracting entry tags: %s", err)
            return list(source_tags)

    @staticmethod
    def _normalize_url(url: str) -> str:
        """Normalize URL for duplicate detection."""

        if not isinstance(url, str):
            return ""

        return url.strip().rstrip("/").lower()

    def _normalize_entry(
        self,
        entry: Any,
        source: FeedSource,
    ) -> Optional[Dict[str, Any]]:
        """
        Convert one feed entry into the normalized article contract.

        Invalid entries return None.
        """

        try:
            if not isinstance(entry, dict):
                return None

            title = self._clean_text(
                entry.get("title")
            )

            url = self._clean_text(
                entry.get("link")
                or entry.get("url")
            )

            description = self._clean_text(
                entry.get("summary")
                or entry.get("description")
                or entry.get("subtitle")
            )

            if not title or not url:
                logger.debug(
                    "Skipping feed entry because title or URL is missing."
                )
                return None

            published = self._normalize_published(entry)

            tags = self._extract_tags(
                entry,
                source.tags,
            )

            article: Dict[str, Any] = {
                "title": title,
                "url": url,
                "description": description,
                "published": published,
                "source_name": source.name,
                "source_url": source.url,
                "category": source.category,
                "priority": source.priority,
                "tags": tags,
            }

            return article

        except Exception as err:
            logger.warning(
                "Failed to normalize feed entry from '%s': %s",
                source.name,
                err,
            )
            return None

    def fetch_source(
        self,
        source: FeedSource,
    ) -> List[Dict[str, Any]]:
        """
        Fetch articles from one RSS/Atom source.

        Returns an empty list if the source cannot be processed.
        """

        if not isinstance(source, FeedSource):
            logger.error("fetch_source received invalid source.")
            return []

        try:
            logger.info(
                "Fetching articles from source: %s",
                source.name,
            )

            feed = feedparser.parse(
                source.url,
                agent=self.config.user_agent,
            )

            if getattr(feed, "bozo", False):
                logger.warning(
                    "Feed parser reported an issue for '%s'.",
                    source.name,
                )

            entries = getattr(feed, "entries", []) or []

            articles: List[Dict[str, Any]] = []

            for entry in entries[
                : self.config.max_articles_per_source
            ]:
                normalized = self._normalize_entry(
                    entry,
                    source,
                )

                if normalized:
                    articles.append(normalized)

            logger.info(
                "Fetched %d normalized article(s) from '%s'.",
                len(articles),
                source.name,
            )

            return articles

        except Exception as err:
            logger.error(
                "Failed to fetch source '%s': %s",
                source.name,
                err,
                exc_info=True,
            )
            return []

    def fetch_all(self) -> List[Dict[str, Any]]:
        """
        Fetch articles from all configured sources.

        Applies optional URL-based deduplication.
        """

        all_articles: List[Dict[str, Any]] = []
        seen_urls: Set[str] = set()

        for source in self.config.sources:
            articles = self.fetch_source(source)

            for article in articles:

                if self.config.remove_duplicates:
                    normalized_url = self._normalize_url(
                        article.get("url", "")
                    )

                    if not normalized_url:
                        continue

                    if normalized_url in seen_urls:
                        logger.debug(
                            "Duplicate article skipped: %s",
                            normalized_url,
                        )
                        continue

                    seen_urls.add(normalized_url)

                all_articles.append(article)

        logger.info(
            "Fetching complete. Total unique articles: %d",
            len(all_articles),
        )

        return all_articles

    def fetch(
        self,
        sources: Optional[List[FeedSource]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Convenience method.

        If sources are supplied, fetches those sources.
        Otherwise uses configured sources.
        """

        if sources is not None:
            original_sources = self.config.sources

            try:
                self.config.sources = sources
                return self.fetch_all()

            finally:
                self.config.sources = original_sources

        return self.fetch_all()


if __name__ == "__main__":

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    logger.info(
        "Starting local ArticleFetcher demonstration..."
    )

    demo_sources = [
        FeedSource(
            name="Hacker News",
            url="https://hnrss.org/frontpage",
            category="Technology",
            priority=1,
            tags=["Technology", "AI", "Programming"],
        ),
        FeedSource(
            name="MIT Technology Review",
            url="https://www.technologyreview.com/feed/",
            category="Technology",
            priority=2,
            tags=["Technology", "Research"],
        ),
    ]

    config = FetcherConfig(
        max_articles_per_source=5,
        remove_duplicates=True,
        sources=demo_sources,
    )

    fetcher = ArticleFetcher(config)

    articles = fetcher.fetch_all()

    print("\n" + "=" * 70)
    print("CORTEX AI DISCOVERY ENGINE - FETCHER TEST")
    print("=" * 70)

    print(
        f"\nTotal articles fetched: {len(articles)}"
    )

    for index, article in enumerate(
        articles[:10],
        start=1,
    ):
        print(
            f"\n#{index} "
            f"[{article['source_name']}]"
        )

        print(
            f"Title: {article['title']}"
        )

        print(
            f"URL: {article['url']}"
        )

        print(
            f"Category: {article['category']}"
        )

        print(
            f"Priority: {article['priority']}"
        )

        print(
            f"Published: {article['published']}"
        )

        print(
            f"Tags: {article['tags']}"
        )

    print("\n" + "=" * 70)
    print("FETCHER TEST COMPLETE")
    print("=" * 70)