"""
AI Intelligence Foundation - Configuration Module

Defines configuration parameters for AI model providers, API limits,
timeouts, retry logic, and environment variable credentials.
"""

from dataclasses import dataclass, field
import os
from typing import Optional


@dataclass
class AIConfig:
    """
    Configuration settings for AI processing providers and preprocessing pipeline.
    """

    provider_name: str = "mock"
    model_name: str = "mock-v1-offline"
    api_timeout: float = 30.0
    max_input_chars: int = 4000
    temperature: float = 0.2
    retry_count: int = 2
    enable_ai: bool = True
    api_key_env_var: str = "AI_API_KEY"
    api_key: Optional[str] = field(default=None, repr=False)

    def __post_init__(self) -> None:
        """Loads API key dynamically from environment variables if not explicitly provided."""
        if self.api_key is None and self.api_key_env_var:
            self.api_key = os.environ.get(self.api_key_env_var)