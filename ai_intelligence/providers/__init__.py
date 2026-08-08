"""
AI Intelligence Foundation - Providers Package
"""

from ai_intelligence.providers.base import BaseAIProvider
from ai_intelligence.providers.mock import MockAIProvider

__all__ = ["BaseAIProvider", "MockAIProvider"]