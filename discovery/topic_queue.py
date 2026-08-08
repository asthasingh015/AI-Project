"""
Cortex AI Discovery Engine - Topic Queue Module

Module: topic_queue.py
Purpose: Receives scored and ranked article dictionaries from scorer.py and manages
         a prioritized, deduplicated, and bounded queue of actionable AI discovery topics.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import difflib
import logging
import re
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urlparse

# Configure logger
logger = logging.getLogger(__name__)


@dataclass
class TopicQueueConfig:
    """Configurable parameters for topic queue thresholding, bounds, and deduplication."""

    minimum_score: float = 40.0
    max_queue_size: int = 100
    deduplicate_topics: bool = True
    topic_similarity_threshold: float = 0.80
    deduplicate_urls: bool = True


class TopicQueue:
    """
    In-memory bounded priority queue for scored discovery articles.
    
    Guarantees:
    - Rejection of invalid, under-scoring, or duplicate items.
    - Highest-scoring and newest items served first.
    - Strict immutability of input article dictionaries.
    - Defensive handling against malformed data and zero external dependencies.
    """

    def __init__(self, config: Optional[TopicQueueConfig] = None) -> None:
        """Initialize the queue with custom or default configuration."""
        self.config = config or TopicQueueConfig()
        self._queue: List[Dict[str, Any]] = []

    @staticmethod
    def _normalize_url(raw_url: str) -> str:
        """Standardizes URL strings to ensure reliable duplicate checking."""
        if not isinstance(raw_url, str):
            return ""
        url = raw_url.strip().rstrip("/")
        try:
            parsed = urlparse(url)
            scheme = parsed.scheme.lower()
            netloc = parsed.netloc.lower()
            path = parsed.path
            return f"{scheme}://{netloc}{path}"
        except Exception:
            return url.lower()

    @staticmethod
    def _normalize_title(title: str) -> str:
        """Normalizes title text by lowercasing and stripping non-alphanumeric characters."""
        if not isinstance(title, str):
            return ""
        cleaned = re.sub(r"[^\w\s]", "", title.lower())
        return re.sub(r"\s+", " ", cleaned).strip()

    @staticmethod
    def _parse_published_timestamp(published: Any) -> datetime:
        """Parses ISO timestamp strings into a timezone-aware datetime for comparison."""
        default_dt = datetime.fromtimestamp(0, tz=timezone.utc)
        if not isinstance(published, str) or not published.strip():
            return default_dt

        try:
            pub_str = published.strip().replace("Z", "+00:00")
            dt = datetime.fromisoformat(pub_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            return default_dt

    def _is_duplicate_topic(self, new_title: str) -> bool:
        """
        Calculates string similarity against queued articles to detect duplicate topics.
        Avoids false positives from single common keyword matches.
        """
        if not self.config.deduplicate_topics or not new_title:
            return False

        norm_new = self._normalize_title(new_title)
        if not norm_new:
            return False

        for existing in self._queue:
            norm_existing = self._normalize_title(str(existing.get("title") or ""))
            if not norm_existing:
                continue

            # Exact match check after normalization
            if norm_new == norm_existing:
                return True

            # Sequence similarity ratio check
            similarity = difflib.SequenceMatcher(None, norm_new, norm_existing).ratio()
            if similarity >= self.config.topic_similarity_threshold:
                logger.debug(
                    "Topic duplicate detected (similarity %.2f >= %.2f):\n  New: '%s'\n  Existing: '%s'",
                    similarity,
                    self.config.topic_similarity_threshold,
                    new_title,
                    existing.get("title"),
                )
                return True

        return False

    def _validate_article(self, article: Dict[str, Any]) -> bool:
        """Performs defensive validation on article fields prior to queue insertion."""
        if not isinstance(article, dict):
            logger.warning("Rejected item: Expected dict, got %s", type(article))
            return False

        # Validate Title
        title = article.get("title")
        if not isinstance(title, str) or not title.strip():
            logger.warning("Rejected article: Missing or non-string title.")
            return False

        # Validate URL
        url = article.get("url")
        if not isinstance(url, str) or not url.strip():
            logger.warning("Rejected article '%s': Missing or non-string URL.", title[:30])
            return False

        parsed_url = urlparse(url.strip())
        if not (parsed_url.scheme in ("http", "https") and parsed_url.netloc):
            logger.warning("Rejected article '%s': Invalid HTTP/HTTPS URL.", title[:30])
            return False

        # Validate Score
        score = article.get("score")
        if not isinstance(score, (int, float)) or isinstance(score, bool):
            logger.warning("Rejected article '%s': Invalid or missing numeric score.", title[:30])
            return False

        if float(score) < self.config.minimum_score:
            logger.debug(
                "Rejected article '%s': Score %.2f below minimum threshold %.2f",
                title[:30],
                float(score),
                self.config.minimum_score,
            )
            return False

        return True

    def _get_sort_key(self, article: Dict[str, Any]) -> tuple[float, datetime]:
        """Creates a comparison key for queue sorting: (Score DESC, Published Date DESC)."""
        score = float(article.get("score", 0.0))
        pub_dt = self._parse_published_timestamp(article.get("published"))
        return (score, pub_dt)

    def rank_queue(self) -> None:
        """Sorts the queue in-place in descending order by score and publish timestamp."""
        self._queue.sort(key=self._get_sort_key, reverse=True)

    def add_article(self, article: Dict[str, Any]) -> bool:
        """
        Validates, deduplicates, and inserts a copy of a scored article into the queue.
        
        Returns True if accepted and queued, False otherwise.
        """
        try:
            if not self._validate_article(article):
                return False

            raw_url = str(article.get("url", ""))
            norm_url = self._normalize_url(raw_url)
            title = str(article.get("title", ""))

            # 1. Deduplicate by URL
            if self.config.deduplicate_urls:
                for item in self._queue:
                    if self._normalize_url(str(item.get("url", ""))) == norm_url:
                        logger.debug("Rejected duplicate URL: %s", norm_url)
                        return False

            # 2. Deduplicate by Topic Similarity
            if self._is_duplicate_topic(title):
                return False

            # Create defensive shallow copy to protect source immutability
            article_copy = article.copy()

            # Insert into queue
            self._queue.append(article_copy)
            self.rank_queue()

            # Maintain queue capacity boundary
            if len(self._queue) > self.config.max_queue_size:
                evicted = self._queue.pop()
                if evicted.get("url") == article_copy.get("url"):
                    logger.debug("Article '%s' rejected: Queue capacity full and score too low.", title[:30])
                    return False
                else:
                    logger.debug("Queue capacity exceeded. Evicted lowest-ranked item: '%s'", evicted.get("title"))

            logger.info("Successfully queued article: '%s' (Score: %s)", title, article_copy.get("score"))
            return True

        except Exception as err:
            logger.error("Unexpected error in add_article: %s", err, exc_info=True)
            return False

    def add_articles(self, articles: List[Dict[str, Any]]) -> int:
        """Batch adds a list of articles to the queue. Returns count of successfully added items."""
        if not isinstance(articles, list):
            logger.error("add_articles expects a list, received %s", type(articles))
            return 0

        added_count = 0
        for article in articles:
            if self.add_article(article):
                added_count += 1

        return added_count

    def pop_next(self) -> Optional[Dict[str, Any]]:
        """Removes and returns the highest-value topic article from the queue. Returns None if empty."""
        if not self._queue:
            return None
        return self._queue.pop(0)

    def peek(self) -> Optional[Dict[str, Any]]:
        """Returns the highest-value topic article without removing it from the queue."""
        if not self._queue:
            return None
        return self._queue[0].copy()

    def get_all(self) -> List[Dict[str, Any]]:
        """Returns a copy of all articles currently in the queue ordered by priority."""
        return [item.copy() for item in self._queue]

    def get_size(self) -> int:
        """Returns current count of queued articles."""
        return len(self._queue)

    def clear(self) -> None:
        """Flushes all items from the topic queue."""
        self._queue.clear()
        logger.info("Topic queue cleared.")

    def contains(self, identifier: str) -> bool:
        """
        Checks if an article exists in the queue by matching exact URL or normalized title.
        """
        if not isinstance(identifier, str) or not identifier.strip():
            return False

        clean_id = identifier.strip()
        norm_url = self._normalize_url(clean_id)
        norm_title = self._normalize_title(clean_id)

        for item in self._queue:
            item_url = self._normalize_url(str(item.get("url", "")))
            item_title = self._normalize_title(str(item.get("title", "")))

            if (norm_url and item_url == norm_url) or (norm_title and item_title == norm_title):
                return True

        return False

    def remove(self, identifier: str) -> bool:
        """
        Removes an article from the queue matching the given URL or title identifier.
        Returns True if item was found and removed, False otherwise.
        """
        if not isinstance(identifier, str) or not identifier.strip():
            return False

        clean_id = identifier.strip()
        norm_url = self._normalize_url(clean_id)
        norm_title = self._normalize_title(clean_id)

        for idx, item in enumerate(self._queue):
            item_url = self._normalize_url(str(item.get("url", "")))
            item_title = self._normalize_title(str(item.get("title", "")))

            if (norm_url and item_url == norm_url) or (norm_title and item_title == norm_title):
                removed_item = self._queue.pop(idx)
                logger.info("Removed article from queue: '%s'", removed_item.get("title"))
                return True

        return False


# -----------------------------------------------------------------------------
# Local Demonstration Block
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    logger.info("Starting local demonstration for topic_queue.py ...")

    # Sample scored articles mimicking output from scorer.py
    sample_scored_articles: List[Dict[str, Any]] = [
        {
            "title": "Agentic AI Frameworks for Autonomous Machine Learning Research",
            "url": "https://ai-journal.org/articles/agentic-ai-frameworks",
            "description": "Research on agentic AI foundation models and automated benchmarks.",
            "published": "2026-08-08T16:00:00Z",
            "source_name": "AI Journal",
            "score": 88.5,
            "score_breakdown": {"source_priority": 25.0, "topic_relevance": 25.0},
        },
        {
            # Near-duplicate topic title of Article 1
            "title": "Agentic AI Frameworks for Autonomous Machine Learning Research!",
            "url": "https://mirror-ai-journal.org/agentic-ai-frameworks-mirror",
            "description": "Republished study on agentic AI systems.",
            "published": "2026-08-08T16:05:00Z",
            "source_name": "AI Journal Mirror",
            "score": 85.0,
            "score_breakdown": {"source_priority": 20.0, "topic_relevance": 25.0},
        },
        {
            # Low score article (below minimum_score of 50.0)
            "title": "Minor Maintenance Patch for Dev Infrastructure",
            "url": "https://dev-updates.org/patch-notes",
            "description": "Routine weekly infrastructure maintenance log.",
            "published": "2026-08-08T12:00:00Z",
            "source_name": "DevUpdates",
            "score": 32.0,
            "score_breakdown": {"source_priority": 10.0, "topic_relevance": 0.0},
        },
        {
            # High quality distinct article
            "title": "Breakthrough in 100-Qubit Quantum Computing Hardware",
            "url": "https://hardware-weekly.com/quantum-chip-breakthrough",
            "description": "Production units yield 100-qubit quantum processors.",
            "published": "2026-08-08T14:00:00Z",
            "source_name": "HardwareWeekly",
            "score": 76.0,
            "score_breakdown": {"source_priority": 18.75, "topic_relevance": 20.0},
        },
        {
            # Same score as Quantum article, but published LATER -> should rank higher when tied
            "title": "Photonic Neural Networks Demonstrate Zero-Latency Inference",
            "url": "https://optics-lab.org/photonic-neural-nets",
            "description": "Optical computing chip demonstrates ultra low-power AI inference.",
            "published": "2026-08-08T17:00:00Z",
            "source_name": "OpticsLab",
            "score": 76.0,
            "score_breakdown": {"source_priority": 18.75, "topic_relevance": 20.0},
        },
    ]

    # Initialize queue configuration
    queue_config = TopicQueueConfig(
        minimum_score=50.0,
        max_queue_size=10,
        deduplicate_topics=True,
        topic_similarity_threshold=0.80,
    )

    t_queue = TopicQueue(config=queue_config)

    print("\n--- Adding Scored Articles to Queue ---")
    added_count = t_queue.add_articles(sample_scored_articles)
    print(f"\nSuccessfully queued {added_count} out of {len(sample_scored_articles)} candidate articles.")

    print(f"\nCurrent Queue Size: {t_queue.get_size()}")

    print("\n--- Ranked Queue Order ---")
    for rank, item in enumerate(t_queue.get_all(), 1):
        print(f"#{rank} [Score: {item['score']}] [{item['published']}] - {item['title']}")

    print("\n--- Popping Highest-Ranked Article ---")
    top_article = t_queue.pop_next()
    if top_article:
        print(f"Popped Topic: '{top_article['title']}' with score {top_article['score']}")

    print(f"\nRemaining Queue Size: {t_queue.get_size()}")