"""
AI Intelligence Foundation - Mock Provider Implementation

Provides an offline mock implementation of BaseAIProvider for testing,
development, and local demonstrations without external API calls or keys.
"""

import logging
from typing import Optional

from ai_intelligence.config import AIConfig
from ai_intelligence.models import AnalysisResult, PreparedArticleInput
from ai_intelligence.providers.base import BaseAIProvider

logger = logging.getLogger(__name__)


class MockAIProvider(BaseAIProvider):
    """
    Mock AI Provider simulating structured AI outputs locally.
    Does not require network connectivity or external API credentials.
    """

    def __init__(self, config: Optional[AIConfig] = None) -> None:
        """Initialize Mock Provider using default mock settings if none provided."""
        cfg = config or AIConfig(provider_name="mock", model_name="mock-v1-offline")
        super().__init__(config=cfg)

    def _execute_analysis(self, article_input: PreparedArticleInput) -> AnalysisResult:
        """
        Generates a deterministic, structured AnalysisResult based on input metadata.
        """
        logger.info(
            "Executing local mock AI analysis for article ID: %s",
            article_input.article_id,
        )

        title = article_input.raw_title
        metadata = article_input.metadata
        category = metadata.get("category", "General")
        tags = metadata.get("tags", [])

        # Construct simulated structured response
        mock_summary = f"[Mock Summary] Analyzed '{title}'. Highlights key developments in {category}."
        mock_topics = list(set([category] + tags[:3] + ["AI Intelligence"]))
        mock_keywords = [t.lower() for t in tags if t] or ["technology", "innovation"]
        mock_entities = ["Cortex AI Engine", "Research Team"]

        return AnalysisResult(
            article_id=article_input.article_id,
            status="success",
            summary=mock_summary,
            topics=mock_topics,
            category=category,
            keywords=mock_keywords,
            entities=mock_entities,
            importance_explanation="Article scored high priority in discovery pipeline.",
            confidence=0.95,
            provider_name=self.config.provider_name,
            model_name=self.config.model_name,
            raw_response={
                "mock_prompt_received_len": len(article_input.formatted_prompt_text),
                "simulated_tokens": 120,
            },
        )