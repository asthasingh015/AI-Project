"""
AI Intelligence Foundation - Base Provider Interface

Defines the abstract interface that all AI model providers (OpenAI, Gemini, Anthropic, Mock)
must implement to ensure vendor neutrality and pluggability.
"""

from abc import ABC, abstractmethod
import logging
import time
from typing import Optional

from ai_intelligence.config import AIConfig
from ai_intelligence.models import AnalysisResult, PreparedArticleInput

logger = logging.getLogger(__name__)


class BaseAIProvider(ABC):
    """
    Abstract base class for AI intelligence providers.
    Subclasses implement vendor-specific API integrations or local mock behavior.
    """

    def __init__(self, config: Optional[AIConfig] = None) -> None:
        """Initialize provider instance with configuration settings."""
        self.config = config or AIConfig()
        logger.info(
            "Initializing AI Provider '%s' using model '%s'",
            self.config.provider_name,
            self.config.model_name,
        )

    @abstractmethod
    def _execute_analysis(self, article_input: PreparedArticleInput) -> AnalysisResult:
        """
        Vendor-specific implementation method to execute analysis on preprocessed input.
        Must be overridden by concrete provider classes.
        """
        pass

    def analyze_article(self, article_input: PreparedArticleInput) -> AnalysisResult:
        """
        Public execution wrapper handling timing, error catching, and state validation.
        Guaranteed never to throw uncaught exceptions.
        """
        if not self.config.enable_ai:
            logger.info("AI processing disabled in configuration. Returning fallback result.")
            return AnalysisResult(
                article_id=article_input.article_id,
                status="fallback",
                error_message="AI processing disabled by configuration",
                provider_name=self.config.provider_name,
                model_name=self.config.model_name,
            )

        if not article_input.formatted_prompt_text:
            logger.warning("Empty article input text for article ID: %s", article_input.article_id)
            return AnalysisResult(
                article_id=article_input.article_id,
                status="error",
                error_message="Preprocessed input text is empty or malformed",
                provider_name=self.config.provider_name,
                model_name=self.config.model_name,
            )

        start_time = time.perf_counter()

        try:
            result = self._execute_analysis(article_input)
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            result.execution_time_ms = round(elapsed_ms, 2)
            return result

        except Exception as err:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            logger.error(
                "Execution error during AI analysis for article ID '%s' via provider '%s': %s",
                article_input.article_id,
                self.config.provider_name,
                err,
                exc_info=True,
            )
            return AnalysisResult(
                article_id=article_input.article_id,
                status="error",
                error_message=f"Provider execution failure: {str(err)}",
                provider_name=self.config.provider_name,
                model_name=self.config.model_name,
                execution_time_ms=round(elapsed_ms, 2),
            )