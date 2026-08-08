"""
AI Intelligence Foundation - OpenAI Provider Implementation

Provides an OpenAI SDK-backed implementation of BaseAIProvider for live article
summarization, entity extraction, categorization, and confidence scoring.
"""

import json
import logging
import time
from typing import Any, Dict, List, Optional

try:
    from openai import OpenAI, APIError, APIConnectionError, APITimeoutError
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    OpenAI = None  # type: ignore
    APIError = Exception  # type: ignore
    APIConnectionError = Exception  # type: ignore
    APITimeoutError = Exception  # type: ignore

from ai_intelligence.config import AIConfig
from ai_intelligence.models import AnalysisResult, PreparedArticleInput
from ai_intelligence.providers.base import BaseAIProvider

logger = logging.getLogger(__name__)


class OpenAIProvider(BaseAIProvider):
    """
    OpenAI implementation of BaseAIProvider.
    Communicates with OpenAI Chat Completions API using structured JSON output.
    """

    def __init__(self, config: Optional[AIConfig] = None) -> None:
        """Initialize OpenAIProvider with configuration and client setup."""
        cfg = config or AIConfig(provider_name="openai", model_name="gpt-4o-mini")
        super().__init__(config=cfg)

        self.client: Optional[Any] = None
        if self.config.api_key:
            if not OPENAI_AVAILABLE:
                logger.warning(
                    "openai package is not installed. OpenAIProvider calls will fail gracefully."
                )
            else:
                self.client = OpenAI(
                    api_key=self.config.api_key,
                    timeout=self.config.api_timeout,
                )
        else:
            logger.warning(
                "No API key provided for OpenAIProvider. Calls will return fallback status."
            )

    def _execute_analysis(self, article_input: PreparedArticleInput) -> AnalysisResult:
        """
        Executes article analysis via OpenAI Chat Completions API with structured JSON output.
        Handles API errors, timeouts, retries, and fallback statuses defensively.
        """
        # Handle missing API key
        if not self.config.api_key:
            logger.warning("OpenAI API key missing. Execution skipped with fallback status.")
            return AnalysisResult(
                article_id=article_input.article_id,
                status="fallback",
                error_message="OpenAI API key unavailable",
                provider_name=self.config.provider_name,
                model_name=self.config.model_name,
            )

        # Handle missing OpenAI SDK dependency
        if not self.client:
            logger.error("OpenAI client not initialized (missing openai python library).")
            return AnalysisResult(
                article_id=article_input.article_id,
                status="error",
                error_message="OpenAI SDK dependency missing",
                provider_name=self.config.provider_name,
                model_name=self.config.model_name,
            )

        system_prompt = (
            "You are an expert AI content intelligence analyzer for the Cortex AI Discovery Engine. "
            "Analyze the provided article text and return a STRICT JSON object matching this schema exactly:\n"
            "{\n"
            '  "summary": "string (concise 2-3 sentence overview)",\n'
            '  "topics": ["list of strings (3-5 core technical topics)"],\n'
            '  "category": "string (primary high-level category)",\n'
            '  "keywords": ["list of strings (key concepts and terms)"],\n'
            '  "entities": ["list of strings (key organizations, products, frameworks, or people)"],\n'
            '  "importance_explanation": "string (brief justification of article relevance/importance)",\n'
            '  "confidence": float_between_0.0_and_1.0\n'
            "}\n"
            "Output strictly valid JSON with no markdown formatting or extra text."
        )

        retries = max(1, self.config.retry_count)
        last_error: Optional[Exception] = None

        for attempt in range(1, retries + 1):
            try:
                logger.info(
                    "Calling OpenAI API for article ID '%s' (Attempt %d/%d)",
                    article_input.article_id,
                    attempt,
                    retries,
                )

                response = self.client.chat.completions.create(
                    model=self.config.model_name,
                    temperature=self.config.temperature,
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": article_input.formatted_prompt_text},
                    ],
                )

                content = response.choices[0].message.content
                if not content:
                    raise ValueError("OpenAI API returned an empty content payload.")

                parsed_data = self._parse_and_validate_json(content)
                if parsed_data is None:
                    raise ValueError("Failed to parse or validate JSON output from OpenAI.")

                # Extract token usage metadata safely
                usage_info = {}
                if hasattr(response, "usage") and response.usage:
                    usage_info = {
                        "prompt_tokens": getattr(response.usage, "prompt_tokens", 0),
                        "completion_tokens": getattr(response.usage, "completion_tokens", 0),
                        "total_tokens": getattr(response.usage, "total_tokens", 0),
                    }

                return AnalysisResult(
                    article_id=article_input.article_id,
                    status="success",
                    summary=parsed_data["summary"],
                    topics=parsed_data["topics"],
                    category=parsed_data["category"],
                    keywords=parsed_data["keywords"],
                    entities=parsed_data["entities"],
                    importance_explanation=parsed_data["importance_explanation"],
                    confidence=parsed_data["confidence"],
                    provider_name=self.config.provider_name,
                    model_name=self.config.model_name,
                    raw_response={
                        "id": getattr(response, "id", None),
                        "usage": usage_info,
                    },
                )

            except (APITimeoutError, APIConnectionError) as net_err:
                last_error = net_err
                logger.warning(
                    "Network/Timeout error during OpenAI API call (Attempt %d/%d): %s",
                    attempt,
                    retries,
                    net_err,
                )
                if attempt < retries:
                    time.sleep(1.0 * attempt)

            except APIError as api_err:
                last_error = api_err
                logger.error("OpenAI API error encountered: %s", api_err)
                break

            except Exception as err:
                last_error = err
                logger.error("Unexpected error during OpenAI processing: %s", err, exc_info=True)
                break

        return AnalysisResult(
            article_id=article_input.article_id,
            status="error",
            error_message=f"OpenAI analysis failed: {str(last_error)}",
            provider_name=self.config.provider_name,
            model_name=self.config.model_name,
        )

    def _parse_and_validate_json(self, raw_content: str) -> Optional[Dict[str, Any]]:
        """
        Parses raw text response into structured JSON and validates field types safely.
        Provides safe fallbacks for missing or malformed keys.
        """
        try:
            data = json.loads(raw_content)
            if not isinstance(data, dict):
                logger.warning("Decoded JSON is not a dictionary.")
                return None

            summary = str(data.get("summary") or "").strip()
            category = str(data.get("category") or "Uncategorized").strip()
            importance_explanation = str(
                data.get("importance_explanation") or ""
            ).strip()

            topics = self._clean_string_list(data.get("topics"))
            keywords = self._clean_string_list(data.get("keywords"))
            entities = self._clean_string_list(data.get("entities"))

            # Validate and clamp confidence between 0.0 and 1.0
            raw_conf = data.get("confidence", 0.0)
            try:
                conf = float(raw_conf)
                confidence = min(max(conf, 0.0), 1.0)
            except (ValueError, TypeError):
                confidence = 0.0

            return {
                "summary": summary,
                "topics": topics,
                "category": category,
                "keywords": keywords,
                "entities": entities,
                "importance_explanation": importance_explanation,
                "confidence": confidence,
            }

        except json.JSONDecodeError as err:
            logger.warning("Failed to decode JSON from OpenAI response payload: %s", err)
            return None

    @staticmethod
    def _clean_string_list(raw_list: Any) -> List[str]:
        """Safely cleans and converts raw list input into a list of non-empty strings."""
        if not isinstance(raw_list, (list, tuple, set)):
            return []
        cleaned: List[str] = []
        for item in raw_list:
            if item is not None:
                val = str(item).strip()
                if val:
                    cleaned.append(val)
        return cleaned