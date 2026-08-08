"""
Cortex AI Discovery Engine - Discovery Pipeline Module

Module: pipeline.py

Purpose:
    Orchestrates the complete discovery workflow:

    ArticleFetcher
        -> ArticleFilter
        -> ArticleScorer
        -> TopicQueue
"""

from dataclasses import dataclass
import logging
from typing import Any, Dict, List, Optional

from discovery.sources.fetcher import (
    ArticleFetcher,
    FetcherConfig,
    FeedSource,
)
from discovery.filter import ArticleFilter, FilterConfig
from discovery.scorer import ArticleScorer, ScoreConfig
from discovery.topic_queue import TopicQueue, TopicQueueConfig


logger = logging.getLogger(__name__)


# =============================================================================
# Default RSS Sources
# =============================================================================

DEFAULT_SOURCES = [
    FeedSource(
        name="Hacker News",
        url="https://hnrss.org/frontpage",
        category="Technology",
        priority=1,
        tags=["Technology", "AI", "Programming", "Startups"],
    ),
    FeedSource(
        name="MIT Technology Review",
        url="https://www.technologyreview.com/feed/",
        category="Technology",
        priority=2,
        tags=["Technology", "AI", "Research"],
    ),
]


# =============================================================================
# Pipeline Configuration
# =============================================================================

@dataclass
class PipelineConfig:
    """Configuration for all discovery pipeline stages."""

    fetcher_config: Optional[FetcherConfig] = None
    filter_config: Optional[FilterConfig] = None
    score_config: Optional[ScoreConfig] = None
    topic_queue_config: Optional[TopicQueueConfig] = None


# =============================================================================
# Pipeline Result
# =============================================================================

@dataclass
class PipelineRunResult:
    """Stores summary information about one pipeline execution."""

    fetched_count: int = 0
    filtered_count: int = 0
    scored_count: int = 0
    queued_count: int = 0
    top_topic: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert pipeline result into a normal dictionary."""

        return {
            "fetched_count": self.fetched_count,
            "filtered_count": self.filtered_count,
            "scored_count": self.scored_count,
            "queued_count": self.queued_count,
            "top_topic": self.top_topic,
        }


# =============================================================================
# Discovery Pipeline
# =============================================================================

class DiscoveryPipeline:
    """
    Main orchestration layer for the Cortex AI Discovery Engine.

    Pipeline flow:

        ArticleFetcher
             |
             v
        ArticleFilter
             |
             v
        ArticleScorer
             |
             v
        TopicQueue
    """

    def __init__(
        self,
        config: Optional[PipelineConfig] = None,
        fetcher: Optional[ArticleFetcher] = None,
        article_filter: Optional[ArticleFilter] = None,
        scorer: Optional[ArticleScorer] = None,
        topic_queue: Optional[TopicQueue] = None,
    ) -> None:
        """Initialize the discovery pipeline."""

        self.config = config or PipelineConfig()

        # -----------------------------------------------------------------
        # Create default fetcher configuration if none is supplied.
        # This fixes the previous "0 configured source(s)" problem.
        # -----------------------------------------------------------------

        if self.config.fetcher_config is None:
            self.config.fetcher_config = FetcherConfig(
                max_articles_per_source=5,
                timeout=15.0,
                remove_duplicates=True,
                sources=list(DEFAULT_SOURCES),
            )

        # -----------------------------------------------------------------
        # Stage 1 - Article Fetcher
        # -----------------------------------------------------------------

        self.fetcher = (
            fetcher
            or ArticleFetcher(
                config=self.config.fetcher_config
            )
        )

        # -----------------------------------------------------------------
        # Stage 2 - Article Filter
        # -----------------------------------------------------------------

        self.filter = (
            article_filter
            or ArticleFilter(
                config=self.config.filter_config
            )
        )

        # -----------------------------------------------------------------
        # Stage 3 - Article Scorer
        # -----------------------------------------------------------------

        self.scorer = (
            scorer
            or ArticleScorer(
                config=self.config.score_config
            )
        )

        # -----------------------------------------------------------------
        # Stage 4 - Topic Queue
        # -----------------------------------------------------------------

        self.topic_queue = (
            topic_queue
            or TopicQueue(
                config=self.config.topic_queue_config
            )
        )

        logger.info(
            "DiscoveryPipeline initialized successfully."
        )

    # =========================================================================
    # Stage 1 - Fetch Articles
    # =========================================================================

    def fetch_articles(self) -> List[Dict[str, Any]]:
        """Fetch articles from configured RSS/Atom sources."""

        logger.info(
            "Pipeline Stage 1: Fetching articles..."
        )

        try:

            if hasattr(self.fetcher, "fetch_all"):
                articles = self.fetcher.fetch_all()

            elif hasattr(self.fetcher, "fetch"):
                articles = self.fetcher.fetch()

            else:
                logger.error(
                    "ArticleFetcher does not provide fetch_all() or fetch()."
                )
                return []

            if not isinstance(articles, list):
                logger.error(
                    "ArticleFetcher returned invalid type: %s",
                    type(articles),
                )
                return []

            logger.info(
                "Stage 1 complete: %d articles fetched.",
                len(articles),
            )

            return articles

        except Exception as err:

            logger.error(
                "Fetch stage failed: %s",
                err,
                exc_info=True,
            )

            return []

    # =========================================================================
    # Stage 2 - Filter Articles
    # =========================================================================

    def filter_articles(
        self,
        articles: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Filter, validate and deduplicate articles."""

        logger.info(
            "Pipeline Stage 2: Filtering %d articles...",
            len(articles),
        )

        try:

            filtered = self.filter.filter_articles(
                articles
            )

            if not isinstance(filtered, list):
                logger.error(
                    "ArticleFilter returned invalid type: %s",
                    type(filtered),
                )
                return []

            logger.info(
                "Stage 2 complete: %d articles retained.",
                len(filtered),
            )

            return filtered

        except Exception as err:

            logger.error(
                "Filter stage failed: %s",
                err,
                exc_info=True,
            )

            return []

    # =========================================================================
    # Stage 3 - Score and Rank
    # =========================================================================

    def score_articles(
        self,
        articles: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Score and rank filtered articles."""

        logger.info(
            "Pipeline Stage 3: Scoring %d articles...",
            len(articles),
        )

        try:

            scored = self.scorer.rank_articles(
                articles
            )

            if not isinstance(scored, list):
                logger.error(
                    "ArticleScorer returned invalid type: %s",
                    type(scored),
                )
                return []

            logger.info(
                "Stage 3 complete: %d articles scored.",
                len(scored),
            )

            return scored

        except Exception as err:

            logger.error(
                "Scoring stage failed: %s",
                err,
                exc_info=True,
            )

            return []

    # =========================================================================
    # Stage 4 - Queue Articles
    # =========================================================================

    def queue_articles(
        self,
        articles: List[Dict[str, Any]],
    ) -> int:
        """Add scored articles into TopicQueue."""

        logger.info(
            "Pipeline Stage 4: Queuing %d articles...",
            len(articles),
        )

        try:

            queued_count = self.topic_queue.add_articles(
                articles
            )

            if not isinstance(queued_count, int):
                logger.error(
                    "TopicQueue returned invalid count: %s",
                    type(queued_count),
                )
                return 0

            logger.info(
                "Stage 4 complete: %d articles queued.",
                queued_count,
            )

            return queued_count

        except Exception as err:

            logger.error(
                "Queue stage failed: %s",
                err,
                exc_info=True,
            )

            return 0

    # =========================================================================
    # Complete Pipeline
    # =========================================================================

    def run(self) -> PipelineRunResult:
        """Execute the complete discovery pipeline."""

        logger.info("=" * 60)
        logger.info("Starting Cortex AI Discovery Pipeline")
        logger.info("=" * 60)

        # Stage 1
        raw_articles = self.fetch_articles()
        fetched_count = len(raw_articles)

        # Stage 2
        filtered_articles = self.filter_articles(
            raw_articles
        )
        filtered_count = len(filtered_articles)

        # Stage 3
        scored_articles = self.score_articles(
            filtered_articles
        )
        scored_count = len(scored_articles)

        # Stage 4
        queued_count = self.queue_articles(
            scored_articles
        )

        # Top topic
        top_topic = self.get_top_topic()

        # Result
        result = PipelineRunResult(
            fetched_count=fetched_count,
            filtered_count=filtered_count,
            scored_count=scored_count,
            queued_count=queued_count,
            top_topic=top_topic,
        )

        logger.info("=" * 60)
        logger.info("Discovery Pipeline Finished")
        logger.info("Fetched  : %d", result.fetched_count)
        logger.info("Filtered : %d", result.filtered_count)
        logger.info("Scored   : %d", result.scored_count)
        logger.info("Queued   : %d", result.queued_count)
        logger.info("=" * 60)

        return result

    # =========================================================================
    # Queue Helpers
    # =========================================================================

    def get_topics(self) -> List[Dict[str, Any]]:
        """Return all currently queued topics."""

        try:

            topics = self.topic_queue.get_all()

            if isinstance(topics, list):
                return topics

            logger.warning(
                "TopicQueue.get_all() returned invalid type."
            )

            return []

        except Exception as err:

            logger.error(
                "Unable to retrieve topics: %s",
                err,
                exc_info=True,
            )

            return []

    def get_top_topic(
        self,
    ) -> Optional[Dict[str, Any]]:
        """Return the highest-ranked topic without removing it."""

        try:

            topic = self.topic_queue.peek()

            if topic is None:
                return None

            if isinstance(topic, dict):
                return topic

            logger.warning(
                "TopicQueue.peek() returned invalid type."
            )

            return None

        except Exception as err:

            logger.error(
                "Unable to retrieve top topic: %s",
                err,
                exc_info=True,
            )

            return None

    def clear_queue(self) -> None:
        """Clear all queued topics."""

        try:

            self.topic_queue.clear()

            logger.info(
                "Pipeline queue cleared successfully."
            )

        except Exception as err:

            logger.error(
                "Unable to clear pipeline queue: %s",
                err,
                exc_info=True,
            )

    # =========================================================================
    # Resource Management
    # =========================================================================

    def close(self) -> None:
        """Close resources used by ArticleFetcher."""

        if (
            hasattr(self.fetcher, "close")
            and callable(self.fetcher.close)
        ):

            try:

                self.fetcher.close()

                logger.info(
                    "ArticleFetcher resources closed."
                )

            except Exception as err:

                logger.warning(
                    "Error closing ArticleFetcher: %s",
                    err,
                )

    # =========================================================================
    # Context Manager
    # =========================================================================

    def __enter__(self) -> "DiscoveryPipeline":
        """Enter context manager."""

        return self

    def __exit__(
        self,
        exc_type: Any,
        exc_val: Any,
        exc_tb: Any,
    ) -> None:
        """Automatically close resources."""

        self.close()

    # =========================================================================
    # Representation
    # =========================================================================

    def __repr__(self) -> str:
        """Return readable pipeline representation."""

        try:
            source_count = len(
                getattr(
                    self.fetcher.config,
                    "sources",
                    [],
                )
            )
        except Exception:
            source_count = 0

        try:
            queue_size = self.topic_queue.get_size()
        except Exception:
            queue_size = 0

        return (
            "<DiscoveryPipeline("
            f"sources={source_count}, "
            f"queued_topics={queue_size}"
            ")>"
        )


# =============================================================================
# Local Demonstration
# =============================================================================

if __name__ == "__main__":

    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s "
            "[%(levelname)s] "
            "%(name)s: %(message)s"
        ),
    )

    print()
    print("=" * 70)
    print("CORTEX AI DISCOVERY ENGINE")
    print("DISCOVERY PIPELINE TEST")
    print("=" * 70)

    try:

        with DiscoveryPipeline() as pipeline:

            print()
            print("Pipeline Instance:")
            print(pipeline)

            print()
            print("Running discovery pipeline...")
            print()

            result = pipeline.run()

            print()
            print("=" * 70)
            print("PIPELINE RESULTS")
            print("=" * 70)

            print(
                f"Fetched Articles  : {result.fetched_count}"
            )

            print(
                f"Filtered Articles : {result.filtered_count}"
            )

            print(
                f"Scored Articles   : {result.scored_count}"
            )

            print(
                f"Queued Articles   : {result.queued_count}"
            )

            print()
            print("-" * 70)
            print("TOP DISCOVERED TOPIC")
            print("-" * 70)

            top_topic = result.top_topic

            if top_topic:

                print(
                    f"Title    : "
                    f"{top_topic.get('title', 'N/A')}"
                )

                print(
                    f"Score    : "
                    f"{top_topic.get('score', 'N/A')}"
                )

                print(
                    f"Category : "
                    f"{top_topic.get('category', 'N/A')}"
                )

                print(
                    f"URL      : "
                    f"{top_topic.get('url', 'N/A')}"
                )

            else:

                print(
                    "No topics were discovered."
                )

            print()
            print("-" * 70)
            print("RESULT AS DICTIONARY")
            print("-" * 70)

            print(
                result.to_dict()
            )

            print()
            print("=" * 70)
            print("PIPELINE TEST COMPLETED")
            print("=" * 70)

    except Exception as err:

        logger.error(
            "Pipeline demonstration failed: %s",
            err,
            exc_info=True,
        )

        print()
        print("=" * 70)
        print("PIPELINE EXECUTION FAILED")
        print("=" * 70)
        print(f"Error: {err}")
        print("=" * 70)