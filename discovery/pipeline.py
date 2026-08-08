"""
Cortex AI Discovery Engine - Discovery Pipeline Module

Module: pipeline.py
Purpose: Orchestrates the complete discovery workflow from source registry,
         feed fetching, filtering, scoring/ranking, to topic queuing.
"""

from dataclasses import dataclass, field
import logging
from typing import Any, Dict, List, Optional

# Import discovery pipeline modules
from discovery.sources import SourceRegistry, default_registry
from discovery.fetcher import FeedFetcher, FetcherConfig
from discovery.filter import ArticleFilter, FilterConfig
from discovery.scorer import ArticleScorer, ScoreConfig
from discovery.topic_queue import TopicQueue, TopicQueueConfig

# Configure logger
logger = logging.getLogger(__name__)


@dataclass
class PipelineConfig:
    """Configuration container encapsulating settings for each stage of the pipeline."""

    fetcher_config: Optional[FetcherConfig] = None
    filter_config: Optional[FilterConfig] = None
    score_config: Optional[ScoreConfig] = None
    topic_queue_config: Optional[TopicQueueConfig] = None


@dataclass
class PipelineRunResult:
    """Summary of pipeline execution metrics and results."""

    fetched_count: int = 0
    filtered_count: int = 0
    scored_count: int = 0
    queued_count: int = 0
    top_topic: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Converts stats object to standard dictionary representation."""
        return {
            "fetched_count": self.fetched_count,
            "filtered_count": self.filtered_count,
            "scored_count": self.scored_count,
            "queued_count": self.queued_count,
            "top_topic": self.top_topic,
        }


class DiscoveryPipeline:
    """
    Central orchestrator for the Cortex AI Discovery Engine.
    
    Executes the multi-stage pipeline:
        SourceRegistry -> FeedFetcher -> ArticleFilter -> ArticleScorer -> TopicQueue
    """

    def __init__(
        self,
        config: Optional[PipelineConfig] = None,
        registry: Optional[SourceRegistry] = None,
    ) -> None:
        """Initialize pipeline with optional stage configurations and source registry."""
        self.config = config or PipelineConfig()
        self.registry = registry or default_registry

        # Instantiate pipeline stage handlers
        self.fetcher = FeedFetcher(
            config=self.config.fetcher_config,
            registry=self.registry,
        )
        self.filter = ArticleFilter(config=self.config.filter_config)
        self.scorer = ArticleScorer(config=self.config.score_config)
        self.topic_queue = TopicQueue(config=self.config.topic_queue_config)

        logger.info("DiscoveryPipeline initialized successfully.")

    def fetch_articles(self) -> List[Dict[str, Any]]:
        """
        Fetches normalized articles from enabled sources via FeedFetcher.
        Returns a list of raw normalized article dictionaries.
        """
        logger.info("Pipeline stage 1: Fetching articles from enabled sources...")
        try:
            if hasattr(self.fetcher, "fetch_all"):
                articles = self.fetcher.fetch_all()
            elif hasattr(self.fetcher, "fetch_articles"):
                articles = self.fetcher.fetch_articles()
            else:
                articles = []

            if not isinstance(articles, list):
                logger.error("FeedFetcher returned invalid type %s, defaulting to empty list.", type(articles))
                return []

            logger.info("Successfully fetched %d raw articles.", len(articles))
            return articles

        except Exception as err:
            logger.error("Error occurred during fetch stage: %s", err, exc_info=True)
            return []

    def filter_articles(self, articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Passes fetched articles through ArticleFilter.
        Returns only valid, deduplicated, and clean articles.
        """
        logger.info("Pipeline stage 2: Filtering %d raw articles...", len(articles))
        try:
            filtered = self.filter.filter_articles(articles)
            logger.info("Filtering complete: %d clean articles retained.", len(filtered))
            return filtered
        except Exception as err:
            logger.error("Error occurred during filter stage: %s", err, exc_info=True)
            return []

    def score_articles(self, articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Scores and ranks clean articles using ArticleScorer.
        Returns scored and ranked articles in descending order.
        """
        logger.info("Pipeline stage 3: Scoring %d clean articles...", len(articles))
        try:
            scored = self.scorer.rank_articles(articles)
            logger.info("Scoring complete: %d articles scored and ranked.", len(scored))
            return scored
        except Exception as err:
            logger.error("Error occurred during scoring stage: %s", err, exc_info=True)
            return []

    def queue_articles(self, articles: List[Dict[str, Any]]) -> int:
        """
        Enqueues scored articles into TopicQueue.
        Returns the number of articles successfully queued.
        """
        logger.info("Pipeline stage 4: Queuing %d scored articles...", len(articles))
        try:
            queued_count = self.topic_queue.add_articles(articles)
            logger.info("Queuing complete: %d articles accepted into TopicQueue.", queued_count)
            return queued_count
        except Exception as err:
            logger.error("Error occurred during queue stage: %s", err, exc_info=True)
            return 0

    def run(self) -> PipelineRunResult:
        """
        Executes the complete discovery pipeline end-to-end:
            fetch -> filter -> score -> queue
        
        Returns a PipelineRunResult containing stats and the top queued topic.
        """
        logger.info("--- Starting DiscoveryPipeline Execution ---")

        # 1. Fetch
        raw_articles = self.fetch_articles()
        fetched_count = len(raw_articles)

        # 2. Filter
        clean_articles = self.filter_articles(raw_articles)
        filtered_count = len(clean_articles)

        # 3. Score & Rank
        scored_articles = self.score_articles(clean_articles)
        scored_count = len(scored_articles)

        # 4. Queue
        queued_count = self.queue_articles(scored_articles)

        top_topic = self.get_top_topic()

        result = PipelineRunResult(
            fetched_count=fetched_count,
            filtered_count=filtered_count,
            scored_count=scored_count,
            queued_count=queued_count,
            top_topic=top_topic,
        )

        logger.info(
            "--- Pipeline Execution Finished: Fetched=%d | Filtered=%d | Scored=%d | Queued=%d ---",
            result.fetched_count,
            result.filtered_count,
            result.scored_count,
            result.queued_count,
        )

        return result

    def get_topics(self) -> List[Dict[str, Any]]:
        """Returns all currently queued topics."""
        return self.topic_queue.get_all()

    def get_top_topic(self) -> Optional[Dict[str, Any]]:
        """Returns the highest-ranked queued topic without removing it from queue, or None if empty."""
        return self.topic_queue.peek()

    def clear_queue(self) -> None:
        """Clears all items in the TopicQueue."""
        self.topic_queue.clear()
        logger.info("Pipeline queue cleared.")

    def close(self) -> None:
        """Closes network connections and cleans up underlying stage resources."""
        if hasattr(self.fetcher, "close") and callable(self.fetcher.close):
            try:
                self.fetcher.close()
                logger.info("FeedFetcher resources closed.")
            except Exception as err:
                logger.warning("Error closing FeedFetcher: %s", err)

    def __enter__(self) -> "DiscoveryPipeline":
        """Context manager entry support."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit support with automatic resource cleanup."""
        self.close()

    def __repr__(self) -> str:
        """String representation of the pipeline instance."""
        queue_size = self.topic_queue.get_size()
        return f"<DiscoveryPipeline(sources={len(self.registry.get_enabled())}, queued_topics={queue_size})>"


# -----------------------------------------------------------------------------
# Demonstration / Local Run Block
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    logger.info("Starting local test demonstration for pipeline.py ...")

    # Demonstrate usage with Context Manager
    with DiscoveryPipeline() as pipeline:
        print(f"\nPipeline Instance: {pipeline}")

        # Run pipeline end-to-end
        run_results = pipeline.run()

        print("\n--- Pipeline Results Summary ---")
        print(f"Fetched Count  : {run_results.fetched_count}")
        print(f"Filtered Count : {run_results.filtered_count}")
        print(f"Scored Count   : {run_results.scored_count}")
        print(f"Queued Count   : {run_results.queued_count}")

        top = pipeline.get_top_topic()
        if top:
            print("\nTop Topic Discovered:")
            print(f"  Title: {top.get('title')}")
            print(f"  Score: {top.get('score')}")
            print(f"  URL  : {top.get('url')}")
        else:
            print("\nNo topics currently in queue.")