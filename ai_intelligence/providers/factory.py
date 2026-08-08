"""
AI Intelligence Foundation - Provider Factory

Creates the configured AI provider without exposing provider-specific
implementation details to the rest of the application.
"""

import logging
from typing import Optional

from ai_intelligence.config import AIConfig
from ai_intelligence.providers.base import BaseAIProvider
from ai_intelligence.providers.mock import MockAIProvider
from ai_intelligence.providers.openai_provider import OpenAIProvider

logger = logging.getLogger(__name__)


class AIProviderFactory:
    """
    Factory responsible for creating the correct AI provider.

    Supported providers:
        - mock
        - openai

    Future providers:
        - gemini
        - anthropic
    """

    @staticmethod
    def create(config: Optional[AIConfig] = None) -> BaseAIProvider:
        """
        Create and return an AI provider based on configuration.

        Defaults to the offline mock provider so the system can run
        without external API keys during development and testing.
        """

        cfg = config or AIConfig()

        provider_name = (cfg.provider_name or "mock").strip().lower()

        # ---------------------------------------------------------
        # MOCK PROVIDER
        # ---------------------------------------------------------
        if provider_name == "mock":
            logger.info(
                "AIProviderFactory: Creating MockAIProvider with model '%s'",
                cfg.model_name,
            )
            return MockAIProvider(config=cfg)

        # ---------------------------------------------------------
        # OPENAI PROVIDER
        # ---------------------------------------------------------
        if provider_name == "openai":
            logger.info(
                "AIProviderFactory: Creating OpenAIProvider with model '%s'",
                cfg.model_name,
            )
            return OpenAIProvider(config=cfg)

        # ---------------------------------------------------------
        # UNKNOWN PROVIDER -> SAFE MOCK FALLBACK
        # ---------------------------------------------------------
        logger.warning(
            "Unknown AI provider '%s'. Falling back to MockAIProvider.",
            provider_name,
        )

        fallback_config = AIConfig(
            provider_name="mock",
            model_name="mock-v1-offline",
            api_timeout=cfg.api_timeout,
            max_input_chars=cfg.max_input_chars,
            temperature=cfg.temperature,
            retry_count=cfg.retry_count,
            enable_ai=cfg.enable_ai,
            api_key_env_var=cfg.api_key_env_var,
            api_key=cfg.api_key,
        )

        return MockAIProvider(config=fallback_config)


__all__ = ["AIProviderFactory"]