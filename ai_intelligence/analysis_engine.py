"""
Cortex AI Discovery Engine - AI Analysis Engine Orchestrator

Module: analysis_engine.py

Purpose:
    High-level orchestration layer between article preprocessing and
    vendor-neutral AI analysis providers.

Responsibilities:
    - Validate article input
    - Preprocess normalized articles
    - Select provider through AIProviderFactory
    - Execute single and batch analysis
    - Preserve input immutability
    - Return structured AnalysisResult objects
    - Handle provider/preprocessor failures defensively
    - Maintain stable execution for malformed batch items
"""

import json
import logging
import time
from typing import Any, Dict, List, Optional

from ai_intelligence.article_preprocessor import ArticlePreprocessor
from ai_intelligence.config import AIConfig
from ai_intelligence.models import AnalysisResult, PreparedArticleInput
from ai_intelligence.providers.base import BaseAIProvider
from ai_intelligence.providers.factory import AIProviderFactory


logger = logging.getLogger(__name__)


class AIAnalysisEngine:
    """
    High-level orchestrator for AI article analysis.

    The engine is intentionally vendor-neutral. Provider selection is handled
    by AIProviderFactory, allowing the system to switch between mock, OpenAI,
    Gemini, Anthropic, or future providers without changing orchestration logic.
    """

    def __init__(
        self,
        config: Optional[AIConfig] = None,
        provider: Optional[BaseAIProvider] = None,
        preprocessor: Optional[ArticlePreprocessor] = None,
    ) -> None:
        """
        Initialize the analysis engine.

        Args:
            config:
                Optional AIConfig instance.

            provider:
                Optional explicitly injected provider.
                Useful for testing and dependency injection.

            preprocessor:
                Optional ArticlePreprocessor instance.
                Defaults to the standard preprocessor.

        Provider selection:
            If provider is explicitly supplied, it is used.
            Otherwise AIProviderFactory creates the configured provider.
        """

        self.config = config or AIConfig()

        self.preprocessor = (
            preprocessor
            or ArticlePreprocessor(config=self.config)
        )

        # Use explicit provider when supplied.
        # Otherwise delegate provider creation to the factory.
        self.provider = (
            provider
            or AIProviderFactory.create(config=self.config)
        )

        logger.info(
            "AIAnalysisEngine initialized with provider '%s' and model '%s'.",
            self.config.provider_name,
            self.config.model_name,
        )

    # -------------------------------------------------------------------------
    # Prepared Article Analysis
    # -------------------------------------------------------------------------

    def analyze_prepared_article(
        self,
        article_input: PreparedArticleInput,
    ) -> AnalysisResult:
        """
        Analyze an already-preprocessed article.

        Guarantees that an AnalysisResult is returned even if the provider
        raises an unexpected exception.
        """

        if not isinstance(article_input, PreparedArticleInput):
            logger.error(
                "Invalid article_input type provided: %s",
                type(article_input),
            )

            return AnalysisResult(
                article_id="invalid_input",
                status="error",
                error_message=(
                    "Expected PreparedArticleInput, "
                    f"received {type(article_input)}"
                ),
                provider_name=self.config.provider_name,
                model_name=self.config.model_name,
            )

        if not article_input.formatted_prompt_text:
            logger.warning(
                "Prepared article input contains empty prompt text: %s",
                article_input.article_id,
            )

            return AnalysisResult(
                article_id=article_input.article_id,
                status="error",
                error_message="Prepared article input text is empty",
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

            # Defensive contract validation.
            if isinstance(raw_result, AnalysisResult):
                return raw_result

            logger.error(
                "Provider '%s' returned invalid output type: %s",
                self.config.provider_name,
                type(raw_result),
            )

            return AnalysisResult(
                article_id=article_input.article_id,
                status="error",
                error_message=(
                    "Provider returned invalid type "
                    f"{type(raw_result)}"
                ),
                provider_name=self.config.provider_name,
                model_name=self.config.model_name,
            )

        except Exception as err:
            logger.error(
                "Unexpected exception in analyze_prepared_article "
                "for article ID '%s': %s",
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

    # -------------------------------------------------------------------------
    # Single Article Analysis
    # -------------------------------------------------------------------------

    def analyze_article(
        self,
        article: Dict[str, Any],
    ) -> AnalysisResult:
        """
        Validate, preprocess, and analyze a single article dictionary.

        Args:
            article:
                Normalized/scored article dictionary produced by Module 1.

        Returns:
            Structured AnalysisResult.
        """

        # Defensive input validation.
        if not isinstance(article, dict):
            logger.error(
                "analyze_article received non-dictionary input: %s",
                type(article),
            )

            return AnalysisResult(
                article_id="malformed_dict",
                status="error",
                error_message=(
                    "Input article must be a dictionary, "
                    f"got {type(article)}"
                ),
                provider_name=self.config.provider_name,
                model_name=self.config.model_name,
            )

        title = article.get("title")
        url = article.get("url")

        # Validate title.
        if (
            not title
            or not isinstance(title, str)
            or not title.strip()
        ):
            logger.warning(
                "Article missing valid title field."
            )

            return AnalysisResult(
                article_id="missing_title",
                status="error",
                error_message=(
                    "Article dictionary missing valid title field"
                ),
                provider_name=self.config.provider_name,
                model_name=self.config.model_name,
            )

        # Validate URL.
        if (
            not url
            or not isinstance(url, str)
            or not url.strip()
        ):
            logger.warning(
                "Article '%s' missing valid URL field.",
                str(title)[:30],
            )

            return AnalysisResult(
                article_id="missing_url",
                status="error",
                error_message=(
                    "Article dictionary missing valid URL field"
                ),
                provider_name=self.config.provider_name,
                model_name=self.config.model_name,
            )

        try:
            # Stage 1: preprocessing.
            prepared_input = self.preprocessor.prepare(article)

            if not isinstance(
                prepared_input,
                PreparedArticleInput,
            ):
                logger.error(
                    "Preprocessor returned invalid object type: %s",
                    type(prepared_input),
                )

                return AnalysisResult(
                    article_id="preprocessor_error",
                    status="error",
                    error_message=(
                        "Preprocessor failed to produce "
                        "PreparedArticleInput"
                    ),
                    provider_name=self.config.provider_name,
                    model_name=self.config.model_name,
                )

            # Stage 2: provider execution.
            return self.analyze_prepared_article(
                prepared_input
            )

        except Exception as err:
            logger.error(
                "Unexpected error in analyze_article pipeline: %s",
                err,
                exc_info=True,
            )

            return AnalysisResult(
                article_id="pipeline_error",
                status="error",
                error_message=f"Pipeline exception: {str(err)}",
                provider_name=self.config.provider_name,
                model_name=self.config.model_name,
            )

    # -------------------------------------------------------------------------
    # Batch Article Analysis
    # -------------------------------------------------------------------------

    def analyze_articles(
        self,
        articles: List[Dict[str, Any]],
    ) -> List[AnalysisResult]:
        """
        Batch-process a list of article dictionaries sequentially.

        Guarantees:
            - Original processing order is preserved.
            - Input dictionaries are never mutated.
            - Malformed items do not stop the batch.
            - Every processed item produces an AnalysisResult.
        """

        if not isinstance(articles, list):
            logger.error(
                "analyze_articles expects a list, received %s",
                type(articles),
            )
            return []

        logger.info(
            "Starting batch AI analysis for %d items...",
            len(articles),
        )

        start_time = time.perf_counter()

        results: List[AnalysisResult] = []

        stats = {
            "total": len(articles),
            "success": 0,
            "error": 0,
            "fallback": 0,
        }

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
                    "Uncaught exception processing batch item "
                    "at index %d: %s",
                    idx,
                    err,
                    exc_info=True,
                )

                results.append(
                    AnalysisResult(
                        article_id=f"batch_index_{idx}",
                        status="error",
                        error_message=(
                            f"Batch execution exception: {str(err)}"
                        ),
                        provider_name=self.config.provider_name,
                        model_name=self.config.model_name,
                    )
                )

        elapsed_ms = (
            time.perf_counter() - start_time
        ) * 1000.0

        logger.info(
            "Batch AI analysis complete in %.2f ms | "
            "Total=%d | Success=%d | Fallback=%d | Errors=%d",
            elapsed_ms,
            stats["total"],
            stats["success"],
            stats["fallback"],
            stats["error"],
        )

        return results


# =============================================================================
# Local Demonstration
# =============================================================================

if __name__ == "__main__":

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    logger.info(
        "Starting local test demonstration for analysis_engine.py ..."
    )

    # -------------------------------------------------------------------------
    # Sample Module 1 Article
    # -------------------------------------------------------------------------

    sample_article: Dict[str, Any] = {
        "title": (
            "Agentic Frameworks for Autonomous AI "
            "Research Engines"
        ),
        "url": (
            "https://ai-discovery.org/articles/"
            "agentic-frameworks"
        ),
        "description": (
            "A study on scaling LLM multi-agent "
            "systems for discovery engines."
        ),
        "published": "2026-08-08T18:00:00Z",
        "source_name": "AI Discovery Journal",
        "source_url": "https://ai-discovery.org",
        "category": "Artificial Intelligence",
        "priority": 1,
        "tags": [
            "Agentic AI",
            "LLM",
            "Research",
        ],
        "score": 91.5,
        "score_breakdown": {
            "source_priority": 25.0,
            "title_quality": 15.0,
            "description_quality": 15.0,
            "freshness": 20.0,
            "topic_relevance": 16.5,
        },
    }

    # Store copy to verify immutability.
    original_copy = json.dumps(
        sample_article,
        sort_keys=True,
    )

    # -------------------------------------------------------------------------
    # Configure AI
    # -------------------------------------------------------------------------

    ai_config = AIConfig(
        provider_name="mock",
        model_name="mock-v1-offline",
    )

    preprocessor = ArticlePreprocessor(
        config=ai_config
    )

    # Provider is intentionally NOT passed here.
    # AIProviderFactory will create it automatically.
    engine = AIAnalysisEngine(
        config=ai_config,
        preprocessor=preprocessor,
    )

    # -------------------------------------------------------------------------
    # Demo 1: Single Article
    # -------------------------------------------------------------------------

    print("\n" + "=" * 65)
    print("DEMO 1: SINGLE ARTICLE AI ANALYSIS")
    print("=" * 65)

    single_result = engine.analyze_article(
        sample_article
    )

    print(
        json.dumps(
            single_result.to_dict(),
            indent=2,
        )
    )

    # -------------------------------------------------------------------------
    # Demo 2: Batch Processing
    # -------------------------------------------------------------------------

    print("\n" + "=" * 65)
    print(
        "DEMO 2: BATCH PROCESSING "
        "(VALID & MALFORMED ITEMS)"
    )
    print("=" * 65)

    batch_dataset: List[Dict[str, Any]] = [
        sample_article,
        {
            "title": (
                "Quantum Photonic Processors "
                "Reach Production Phase"
            ),
            "url": (
                "https://hardware-weekly.com/"
                "quantum-photonic-chip"
            ),
            "description": (
                "Fab units report breakthrough "
                "yield in optical computing chips."
            ),
            "source_name": "HardwareWeekly",
            "category": "Hardware",
            "score": 78.0,
            "tags": [
                "Quantum",
                "Hardware",
            ],
        },
        {
            # Malformed item: missing title.
            "url": (
                "https://broken-source.com/"
                "no-title-article"
            ),
            "description": (
                "This dictionary lacks a "
                "title field completely."
            ),
        },
        # Malformed item: non-dictionary entry.
        "Not a valid article dictionary",  # type: ignore
    ]

    batch_results = engine.analyze_articles(
        batch_dataset
    )

    print(
        f"\nBatch Results Summary "
        f"({len(batch_results)} items returned):"
    )

    for idx, result in enumerate(
        batch_results,
        1,
    ):
        print(
            f"  Item #{idx} -> "
            f"Status: '{result.status}' | "
            f"ID: '{result.article_id}' | "
            f"Category: '{result.category}' | "
            f"Error: {result.error_message}"
        )

    # -------------------------------------------------------------------------
    # Immutability Verification
    # -------------------------------------------------------------------------

    print("\n" + "=" * 65)
    print("IMMUTABILITY VERIFICATION")
    print("=" * 65)

    current_copy = json.dumps(
        sample_article,
        sort_keys=True,
    )

    is_unmutated = (
        original_copy == current_copy
    )

    print(
        "Original Article Mutated during analysis? "
        f"{not is_unmutated}"
    )

    print(
        f"Verification Check Passed: "
        f"{is_unmutated}"
    )

    print("=" * 65 + "\n")