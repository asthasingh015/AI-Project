"""
AI Intelligence Foundation - Article Preprocessor Module

Transforms raw normalized article dictionaries from Module 1 into bounded,
sanitized, and structured text inputs for AI model prompts without mutating inputs.
"""

import hashlib
import logging
from typing import Any, Dict, Optional

from ai_intelligence.config import AIConfig
from ai_intelligence.models import PreparedArticleInput

logger = logging.getLogger(__name__)


class ArticlePreprocessor:
    """
    Normalizes, truncates, and constructs standardized AI prompts
    from article dictionaries cleanly and safely.
    """

    def __init__(self, config: Optional[AIConfig] = None) -> None:
        """Initialize preprocessor with optional configuration settings."""
        self.config = config or AIConfig()

    @staticmethod
    def _generate_article_id(url: str, title: str) -> str:
        """Generates a deterministic unique identifier for the article."""
        seed = f"{url.strip()}|{title.strip()}"
        return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]

    def prepare(self, article: Dict[str, Any]) -> PreparedArticleInput:
        """
        Extracts fields safely from an article dictionary and converts them into
        a PreparedArticleInput object ready for AI analysis.
        """
        if not isinstance(article, dict):
            logger.error("Preprocessor received non-dictionary item: %s", type(article))
            return PreparedArticleInput(
                article_id="invalid",
                formatted_prompt_text="",
                raw_title="",
                raw_url="",
                metadata={"error": "Input is not a dictionary"},
            )

        try:
            # Safe extraction with fallback defaults
            title = str(article.get("title") or "").strip()
            url = str(article.get("url") or "").strip()
            description = str(article.get("description") or "").strip()
            source_name = str(article.get("source_name") or "Unknown Source").strip()
            category = str(article.get("category") or "Uncategorized").strip()
            score = article.get("score", 0.0)

            # Handle tags list safely
            raw_tags = article.get("tags") or []
            if isinstance(raw_tags, (list, tuple, set)):
                tags = [str(t).strip() for t in raw_tags if t]
            else:
                tags = []

            tags_str = ", ".join(tags) if tags else "None"
            article_id = self._generate_article_id(url, title)

            # Construct standardized input text
            text_block = (
                f"ARTICLE TITLE: {title}\n"
                f"SOURCE: {source_name}\n"
                f"CATEGORY: {category}\n"
                f"PRIORITY SCORE: {score}\n"
                f"TAGS: {tags_str}\n"
                f"SUMMARY/DESCRIPTION:\n{description}"
            )

            # Enforce maximum input character length limit
            if len(text_block) > self.config.max_input_chars:
                logger.debug(
                    "Truncating input text from %d to %d chars for article ID: %s",
                    len(text_block),
                    self.config.max_input_chars,
                    article_id,
                )
                text_block = text_block[: self.config.max_input_chars] + "\n[TRUNCATED]"

            metadata = {
                "source_name": source_name,
                "category": category,
                "published": article.get("published"),
                "original_score": score,
                "tags": tags,
            }

            return PreparedArticleInput(
                article_id=article_id,
                formatted_prompt_text=text_block,
                raw_title=title,
                raw_url=url,
                metadata=metadata,
            )

        except Exception as err:
            logger.error("Error preprocessing article dictionary: %s", err, exc_info=True)
            return PreparedArticleInput(
                article_id="error",
                formatted_prompt_text="",
                raw_title=str(article.get("title") or ""),
                raw_url=str(article.get("url") or ""),
                metadata={"error": str(err)},
            )