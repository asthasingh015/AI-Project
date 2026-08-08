"""
Cortex AI Discovery Engine - AI Content Intelligence Module (Phase 1)

Exposes core AI foundation components: configuration, contract models,
article preprocessor, and provider abstractions.
"""

from ai_intelligence.config import AIConfig
from ai_intelligence.models import AnalysisResult, PreparedArticleInput
from ai_intelligence.article_preprocessor import ArticlePreprocessor
from ai_intelligence.providers.base import BaseAIProvider
from ai_intelligence.providers.mock import MockAIProvider

__all__ = [
    "AIConfig",
    "AnalysisResult",
    "PreparedArticleInput",
    "ArticlePreprocessor",
    "BaseAIProvider",
    "MockAIProvider",
]