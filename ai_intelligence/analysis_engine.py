"""
Cortex AI Discovery Engine - AI Analysis Engine Orchestrator

Module: analysis_engine.py
Purpose: Acts as the high-level orchestration layer between article preprocessing
         and vendor-neutral AI analysis providers. Manages single and batch analysis
         pipeline execution with defensive error handling and logging.
"""

import json
import logging
import time
from typing import Any, Dict, List, Optional

from ai_intelligence.article_preprocessor import ArticlePreprocessor
from ai_intelligence.config import AIConfig
from ai_intelligence.models import AnalysisResult, PreparedArticleInput
from ai_intelligence.providers.base import BaseAIProvider
from ai_intelligence.providers.mock import MockAIProvider

# Configure logger
logger = logging.getLogger(__name__)


class AIAnalysisEngine:
    """
    High-level orchestrator for AI article analysis.
    
    Coordinates input normalization via ArticlePreprocessor and delegates execution
    to a BaseAIProvider implementation. Guarantees safe exception handling, batch stability,
    and strict contract adherence.
    """

    def __init__(
        self,
        config: Optional[AIConfig] = None,
        provider: Optional[BaseAIProvider] = None,
        preprocessor: Optional[ArticlePreprocessor] = None,
    ) -> None:
        """
        Initialize the analysis engine with dependency-injected components.
        
        Args:
            config: Optional AIConfig instance.
            provider: Concrete BaseAIProvider subclass (defaults to MockAIProvider).
            preprocessor: ArticlePreprocessor instance (defaults to standard preprocessor).
        """
        self.config = config or AIConfig()
        self.preprocessor = preprocessor or ArticlePreprocessor(config=self.config)
        self.provider = provider or MockAIProvider(config=self.config)

        logger.info(
            "AIAnalysisEngine initialized with provider '%s' and model '%s'.",
            self.config.provider_name,
            self.config.model_name,
        )

    def analyze_prepared_article(
        self, article_input: PreparedArticleInput
    ) -> AnalysisResult:
        """
        Analyzes a preprocessed article input using the configured AI provider.
        
        Guarantees that an AnalysisResult is always returned, even in the event
        of provider anomalies or unexpected exceptions.
        """
        if not isinstance(article_input, PreparedArticleInput):
            logger.error(
                "Invalid article_input type provided: %s", type(article_input)
            )
            return AnalysisResult(
                article_id="invalid_input",
                status="error",
                error_message=f"Expected PreparedArticleInput, received {type(article_input)}",
                provider_name=self.config.provider_name,
                model_name=self.config.model_name,
            )

        logger.debug(
            "Dispatching article ID '%s' to provider '%s'.",
            article_input.article_id,
            self.config.provider_name,
        )

        try:
            raw_result = self.provider.analyze_article(article_input)

            # Defensive check: ensure provider returned a valid AnalysisResult object
            if isinstance(raw_result, AnalysisResult):
                return raw_result

            logger.error(
                "Provider '%s' returned an invalid output type: %s",
                self.config.provider_name,
                type(raw_result),
            )
            return AnalysisResult(
                article_id=article_input.article_id,
                status="error",
                error_message=f"Provider returned invalid type {type(raw_result)}",
                provider_name=self.config.provider_name,
                model_name=self.config.model_name,
            )

        except Exception as err:
            logger.error(
                "Unexpected exception in analyze_prepared_article for ID '%s': %s",
                article_input.article_id,
                err,
                exc_info=True,
            )
            return AnalysisResult(
                article_id=article_input.article_id,
                status="error",
                error_message=f"Engine execution error: {str(err)}",
                provider_name=self.config.provider_name,
                model_name=self.config.model_name,
            )

    def analyze_article(self, article: Dict[str, Any]) -> AnalysisResult:
        """
        Validates, preprocesses, and analyzes a single article dictionary.
        
        Args:
            article: Normalized article dictionary from Module 1 pipeline.
            
        Returns:
            Structured AnalysisResult contract.
        """
        # Defensive Input Validation
        if not isinstance(article, dict):
            logger.error("analyze_article received non-dictionary input: %s", type(article))
            return AnalysisResult(
                article_id="malformed_dict",
                status="error",
                error_message=f"Input article must be a dictionary, got {type(article)}",
                provider_name=self.config.provider_name,
                model_name=self.config.model_name,
            )

        title = article.get("title")
        url = article.get("url")

        if not title or not isinstance(title, str) or not title.strip():
            logger.warning("Article missing valid title field.")
            return AnalysisResult(
                article_id="missing_title",
                status="error",
                error_message="Article dictionary missing valid title field",
                provider_name=self.config.provider_name,
                model_name=self.config.model_name,
            )

        if not url or not isinstance(url, str) or not url.strip():
            logger.warning("Article '%s' missing valid URL field.", str(title)[:30])
            return AnalysisResult(
                article_id="missing_url",
                status="error",
                error_message="Article dictionary missing valid URL field",
                provider_name=self.config.provider_name,
                model_name=self.config.model_name,
            )

        try:
            # Stage 1: Preprocessing
            prepared_input = self.preprocessor.prepare(article)

            if not isinstance(prepared_input, PreparedArticleInput):
                logger.error("Preprocessor returned invalid object type.")
                return AnalysisResult(
                    article_id="preprocessor_error",
                    status="error",
                    error_message="Preprocessor failed to produce PreparedArticleInput",
                    provider_name=self.config.provider_name,
                    model_name=self.config.model_name,
                )

            # Stage 2: Provider Execution
            return self.analyze_prepared_article(prepared_input)

        except Exception as err:
            logger.error("Unexpected error in analyze_article pipeline: %s", err, exc_info=True)
            return AnalysisResult(
                article_id="pipeline_error",
                status="error",
                error_message=f"Pipeline exception: {str(err)}",
                provider_name=self.config.provider_name,
                model_name=self.config.model_name,
            )

    def analyze_articles(self, articles: List[Dict[str, Any]]) -> List[AnalysisResult]:
        """
        Batch processes a list of article dictionaries sequentially.
        
        Guarantees:
        - Maintains exact article processing order.
        - Never mutates incoming article dictionaries.
        - Captures malformed items as error AnalysisResults without interrupting execution.
        """
        if not isinstance(articles, list):
            logger.error("analyze_articles expects a list, received %s", type(articles))
            return []

        logger.info("Starting batch AI analysis for %d items...", len(articles))
        start_time = time.perf_counter()

        results: List[AnalysisResult] = []
        stats = {"total": len(articles), "success": 0, "error": 0, "fallback": 0}

        for idx, item in enumerate(articles):
            try:
                result = self.analyze_article(item)
                results.append(result)

                if result.status == "success":
                    stats["success"] += 1
                elif result.status == "fallback":
                    stats["fallback"] += 1
                else:
                    stats["error"] += 1

            except Exception as err:
                stats["error"] += 1
                logger.error(
                    "Uncaught exception processing batch item at index %d: %s",
                    idx,
                    err,
                    exc_info=True,
                )
                results.append(
                    AnalysisResult(
                        article_id=f"batch_index_{idx}",
                        status="error",
                        error_message=f"Batch execution exception: {str(err)}",
                        provider_name=self.config.provider_name,
                        model_name=self.config.model_name,
                    )
                )

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        logger.info(
            "Batch AI analysis complete in %.2f ms | Total=%d | Success=%d | Fallback=%d | Errors=%d",
            elapsed_ms,
            stats["total"],
            stats["success"],
            stats["fallback"],
            stats["error"],
        )

        return results


# -----------------------------------------------------------------------------
# Local Demonstration Block
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    logger.info("Starting local test demonstration for analysis_engine.py ...")

    # 1. Create a sample normalized/scored article dictionary from Module 1
    sample_article: Dict[str, Any] = {
        "title": "Agentic Frameworks for Autonomous AI Research Engines",
        "url": "https://ai-discovery.org/articles/agentic-frameworks",
        "description": "A study on scaling LLM multi-agent systems for discovery engines.",
        "published": "2026-08-08T18:00:00Z",
        "source_name": "AI Discovery Journal",
        "source_url": "https://ai-discovery.org",
        "category": "Artificial Intelligence",
        "priority": 1,
        "tags": ["Agentic AI", "LLM", "Research"],
        "score": 91.5,
        "score_breakdown": {
            "source_priority": 25.0,
            "title_quality": 15.0,
            "description_quality": 15.0,
            "freshness": 20.0,
            "topic_relevance": 16.5,
        },
    }

    # Store a copy to verify immutability
    original_copy = json.dumps(sample_article, sort_keys=True)

    # 2. Setup AI components with Mock provider
    ai_config = AIConfig(provider_name="mock", model_name="mock-v1-offline")
    preprocessor = ArticlePreprocessor(config=ai_config)
    mock_provider = MockAIProvider(config=ai_config)

    # 3. Instantiate AIAnalysisEngine via dependency injection
    engine = AIAnalysisEngine(
        config=ai_config,
        provider=mock_provider,
        preprocessor=preprocessor,
    )

    print("\n" + "=" * 65)
    print("DEMO 1: SINGLE ARTICLE AI ANALYSIS")
    print("=" * 65)

    single_result = engine.analyze_article(sample_article)
    print(json.dumps(single_result.to_dict(), indent=2))

    print("\n" + "=" * 65)
    print("DEMO 2: BATCH PROCESSING (VALID & MALFORMED ITEMS)")
    print("=" * 65)

    batch_dataset: List[Dict[str, Any]] = [
        sample_article,
        {
            # Valid second article
            "title": "Quantum Photonic Processors Reach Production Phase",
            "url": "https://hardware-weekly.com/quantum-photonic-chip",
            "description": "Fab units report breakthrough yield in optical computing chips.",
            "source_name": "HardwareWeekly",
            "category": "Hardware",
            "score": 78.0,
            "tags": ["Quantum", "Hardware"],
        },
        {
            # Malformed item: Missing required title
            "url": "https://broken-source.com/no-title-article",
            "description": "This dictionary lacks a title field completely.",
        },
        # Malformed item: Non-dictionary entry
        "Not a valid article dictionary",  # type: ignore
    ]

    batch_results = engine.analyze_articles(batch_dataset)

    print(f"\nBatch Results Summary ({len(batch_results)} items returned):")
    for idx, res in enumerate(batch_results, 1):
        print(
            f"  Item #{idx} -> Status: '{res.status}' | ID: '{res.article_id}' | "
            f"Category: '{res.category}' | Error: {res.error_message}"
        )

    print("\n" + "=" * 65)
    print("IMMUTABILITY VERIFICATION")
    print("=" * 65)
    current_copy = json.dumps(sample_article, sort_keys=True)
    is_unmutated = original_copy == current_copy
    print(f"Original Article Mutated during analysis? {not is_unmutated}")
    print(f"Verification Check Passed: {is_unmutated}")
    print("=" * 65 + "\n")