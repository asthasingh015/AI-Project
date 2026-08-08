"""
Cortex AI Discovery Engine - Article Filter Module

Module: filter.py
Purpose: Receives normalized article dictionaries from fetcher.py and filters out
         low-quality, invalid, duplicate, short, or off-topic articles prior to
         scoring and topic queuing.
"""

from dataclasses import dataclass, field
import logging
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urlparse

# Configure logger
logger = logging.getLogger(__name__)


@dataclass
class FilterConfig:
    """Configuration settings for article filtering rules."""

    minimum_title_length: int = 10
    maximum_title_length: int = 300
    minimum_description_length: int = 0
    blocked_keywords: Set[str] = field(default_factory=set)
    required_keywords: Set[str] = field(default_factory=set)
    remove_duplicates: bool = True
    case_sensitive_keywords: bool = False

    def __post_init__(self) -> None:
        """Ensure keywords are standardized according to case sensitivity settings."""
        if not self.case_sensitive_keywords:
            self.blocked_keywords = {kw.strip().lower() for kw in self.blocked_keywords if kw and kw.strip()}
            self.required_keywords = {kw.strip().lower() for kw in self.required_keywords if kw and kw.strip()}
        else:
            self.blocked_keywords = {kw.strip() for kw in self.blocked_keywords if kw and kw.strip()}
            self.required_keywords = {kw.strip() for kw in self.required_keywords if kw and kw.strip()}


class ArticleFilter:
    """
    Production-ready filter pipeline for article dictionaries.
    Ensures data integrity, quality control, deduplication, and keyword filtering.
    """

    def __init__(self, config: Optional[FilterConfig] = None) -> None:
        """Initialize the filter with optional custom configuration."""
        self.config = config or FilterConfig()

    @staticmethod
    def _normalize_url(raw_url: str) -> str:
        """Normalize URL string for robust duplicate detection."""
        if not isinstance(raw_url, str):
            return ""
        url = raw_url.strip().rstrip("/")
        try:
            parsed = urlparse(url)
            # Remove default ports and force lowercase scheme & hostname
            scheme = parsed.scheme.lower()
            netloc = parsed.netloc.lower()
            path = parsed.path
            return f"{scheme}://{netloc}{path}"
        except Exception:
            return url.lower()

    def is_valid_article(self, article: Dict[str, Any]) -> bool:
        """
        Validates structural integrity, URL validity, title length, and description requirements.
        Never throws exceptions; returns False on invalid/malformed structures.
        """
        if not isinstance(article, dict):
            logger.debug("Filtered out article: Input is not a dictionary.")
            return False

        try:
            # 1. Validate Title
            title = article.get("title")
            if not isinstance(title, str) or not title.strip():
                logger.debug("Filtered out article: Title is missing or empty.")
                return False

            clean_title = title.strip()
            title_len = len(clean_title)
            if title_len < self.config.minimum_title_length:
                logger.debug("Filtered out article: Title too short (%d chars): '%s'", title_len, clean_title)
                return False
            if title_len > self.config.maximum_title_length:
                logger.debug("Filtered out article: Title too long (%d chars): '%s'", title_len, clean_title[:30])
                return False

            # 2. Validate URL
            url = article.get("url")
            if not isinstance(url, str) or not url.strip():
                logger.debug("Filtered out article: URL is missing or empty.")
                return False

            clean_url = url.strip()
            parsed_url = urlparse(clean_url)
            if not (parsed_url.scheme in ("http", "https") and parsed_url.netloc):
                logger.debug("Filtered out article: Invalid HTTP/HTTPS URL: '%s'", clean_url)
                return False

            # 3. Validate Description
            description = article.get("description") or ""
            if not isinstance(description, str):
                description = str(description)

            clean_desc = description.strip()
            if self.config.minimum_description_length > 0:
                if len(clean_desc) < self.config.minimum_description_length:
                    logger.debug("Filtered out article: Description too short (%d chars).", len(clean_desc))
                    return False

            return True

        except Exception as err:
            logger.warning("Unexpected error during article validation: %s", err)
            return False

    def is_duplicate(self, article: Dict[str, Any], seen_urls: Set[str]) -> bool:
        """
        Checks if an article's URL has already been processed.
        If remove_duplicates is enabled and URL is seen, returns True.
        Otherwise adds normalized URL to seen_urls and returns False.
        """
        if not self.config.remove_duplicates:
            return False

        if not isinstance(article, dict):
            return False

        raw_url = article.get("url", "")
        normalized_url = self._normalize_url(raw_url)

        if not normalized_url:
            return False

        if normalized_url in seen_urls:
            logger.debug("Duplicate detected for URL: %s", normalized_url)
            return True

        seen_urls.add(normalized_url)
        return False

    def matches_keywords(self, article: Dict[str, Any]) -> bool:
        """
        Evaluates article against configured blocked and required keywords.
        Inspects title, description, and tags fields safely.
        """
        if not self.config.blocked_keywords and not self.config.required_keywords:
            return True

        if not isinstance(article, dict):
            return False

        try:
            # Extract text elements safely
            title = str(article.get("title") or "")
            description = str(article.get("description") or "")
            tags_list = article.get("tags") or []
            tags_text = " ".join(str(t) for t in tags_list) if isinstance(tags_list, (list, tuple, set)) else ""

            content = f"{title} {description} {tags_text}"
            if not self.config.case_sensitive_keywords:
                content = content.lower()

            # Check Blocked Keywords (Reject if ANY match)
            for blocked in self.config.blocked_keywords:
                if blocked in content:
                    logger.debug("Filtered out article: Matched blocked keyword '%s'", blocked)
                    return False

            # Check Required Keywords (Require AT LEAST ONE match if rule is configured)
            if self.config.required_keywords:
                matched_required = any(req in content for req in self.config.required_keywords)
                if not matched_required:
                    logger.debug("Filtered out article: Failed required keywords check.")
                    return False

            return True

        except Exception as err:
            logger.warning("Unexpected error during keyword evaluation: %s", err)
            return False

    def filter_articles(self, articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Filters a list of normalized article dictionaries.
        
        Guarantees:
        - Input list and inner dictionaries are never mutated.
        - Malformed or corrupt articles do not crash execution.
        - Detailed statistics are logged upon completion.
        """
        if not isinstance(articles, list):
            logger.error("filter_articles expects a list, received %s", type(articles))
            return []

        filtered_articles: List[Dict[str, Any]] = []
        seen_urls: Set[str] = set()

        stats = {
            "total_received": len(articles),
            "passed": 0,
            "invalid": 0,
            "duplicates": 0,
            "keyword_mismatch": 0,
            "processing_errors": 0,
        }

        for article in articles:
            try:
                # Basic validation
                if not self.is_valid_article(article):
                    stats["invalid"] += 1
                    continue

                # Duplicate detection
                if self.is_duplicate(article, seen_urls):
                    stats["duplicates"] += 1
                    continue

                # Keyword filtering
                if not self.matches_keywords(article):
                    stats["keyword_mismatch"] += 1
                    continue

                # Passed all filters
                filtered_articles.append(article)
                stats["passed"] += 1

            except Exception as err:
                stats["processing_errors"] += 1
                logger.error("Uncaught exception filtering article: %s", err, exc_info=True)

        logger.info(
            "Article filtering complete: Total=%d | Passed=%d | Invalid=%d | Duplicates=%d | Keyword Filtered=%d | Errors=%d",
            stats["total_received"],
            stats["passed"],
            stats["invalid"],
            stats["duplicates"],
            stats["keyword_mismatch"],
            stats["processing_errors"],
        )

        return filtered_articles

    def filter_by_category(self, articles: List[Dict[str, Any]], category: str) -> List[Dict[str, Any]]:
        """
        Filters input articles matching the specified category (case-insensitive).
        Returns a new list without modifying original inputs.
        """
        if not isinstance(articles, list) or not isinstance(category, str):
            return []

        target_category = category.strip().lower()
        result: List[Dict[str, Any]] = []

        for article in articles:
            if isinstance(article, dict):
                art_category = str(article.get("category") or "").strip().lower()
                if art_category == target_category:
                    result.append(article)

        return result

    def filter_by_source(self, articles: List[Dict[str, Any]], source_name: str) -> List[Dict[str, Any]]:
        """
        Filters input articles matching the specified source_name (case-insensitive).
        Returns a new list without modifying original inputs.
        """
        if not isinstance(articles, list) or not isinstance(source_name, str):
            return []

        target_source = source_name.strip().lower()
        result: List[Dict[str, Any]] = []

        for article in articles:
            if isinstance(article, dict):
                art_source = str(article.get("source_name") or "").strip().lower()
                if art_source == target_source:
                    result.append(article)

        return result


# -----------------------------------------------------------------------------
# Demonstration / Local Verification Block
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    # Setup standard console logging for demonstration
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    logger.info("Starting local demonstration for filter.py ...")

    # Sample test dataset mimicking fetcher.py normalized dictionaries
    sample_articles: List[Dict[str, Any]] = [
        {
            "title": "Breakthrough in Generative AI Architecture Unveiled",
            "url": "https://tech-news.org/articles/gen-ai-breakthrough",
            "description": "Researchers introduce a highly scalable neural transformer design.",
            "published": "2026-08-08T10:00:00Z",
            "source_name": "TechNews",
            "source_url": "https://tech-news.org",
            "category": "Artificial Intelligence",
            "priority": 1,
            "tags": ["AI", "Machine Learning", "Research"],
        },
        {
            # Duplicate URL (normalized match with article 1)
            "title": "Breakthrough in Generative AI Architecture Unveiled!",
            "url": "https://tech-news.org/articles/gen-ai-breakthrough/",
            "description": "Researchers introduce a highly scalable neural transformer design.",
            "published": "2026-08-08T10:05:00Z",
            "source_name": "TechNews",
            "source_url": "https://tech-news.org",
            "category": "Artificial Intelligence",
            "priority": 1,
            "tags": ["AI"],
        },
        {
            # Invalid: Title too short
            "title": "Short",
            "url": "https://example.com/short-title",
            "description": "Valid description length for testing purposes.",
            "published": "2026-08-08T11:00:00Z",
            "source_name": "ExampleBlog",
            "source_url": "https://example.com",
            "category": "General",
            "priority": 2,
            "tags": [],
        },
        {
            # Invalid: Missing scheme/bad URL
            "title": "Invalid URL Article Format",
            "url": "not-a-valid-url-string",
            "description": "This article has a completely broken URL format.",
            "published": "2026-08-08T12:00:00Z",
            "source_name": "BadSource",
            "source_url": "http://bad.source",
            "category": "Engineering",
            "priority": 3,
            "tags": ["Bug"],
        },
        {
            # Contains Blocked Keyword ("crypto")
            "title": "New Crypto Scam targeting Web3 Users Exposed",
            "url": "https://security-today.com/crypto-scam-alert",
            "description": "Security analysts identify phishing campaigns targeting wallets.",
            "published": "2026-08-08T13:00:00Z",
            "source_name": "SecurityToday",
            "source_url": "https://security-today.com",
            "category": "Security",
            "priority": 1,
            "tags": ["Security", "Crypto"],
        },
        {
            # Valid AI Article
            "title": "Next-Gen Quantum Computing Chips Enter Production",
            "url": "https://hardware-weekly.com/quantum-chip-production",
            "description": "Fab units report successful yield for 100-qubit processors.",
            "published": "2026-08-08T14:00:00Z",
            "source_name": "HardwareWeekly",
            "source_url": "https://hardware-weekly.com",
            "category": "Hardware",
            "priority": 2,
            "tags": ["Quantum", "Hardware"],
        },
        # Malformed item in batch
        None,  # type: ignore
        "Invalid non-dict item",  # type: ignore
    ]

    # Instantiate Filter Configuration
    config = FilterConfig(
        minimum_title_length=10,
        minimum_description_length=15,
        blocked_keywords={"crypto", "casino", "sponsored"},
        required_keywords=set(),  # Open filter
        remove_duplicates=True,
    )

    filter_engine = ArticleFilter(config=config)

    # Execute main filter pipeline
    print("\n--- Running Main Filter Pipeline ---")
    clean_articles = filter_engine.filter_articles(sample_articles)

    print(f"\nRemaining Articles ({len(clean_articles)}):")
    for idx, art in enumerate(clean_articles, 1):
        print(f"{idx}. [{art['source_name']}] {art['title']} ({art['url']})")

    # Demonstrate Category Sub-filtering
    print("\n--- Filtering by Category: 'Artificial Intelligence' ---")
    ai_articles = filter_engine.filter_by_category(clean_articles, "Artificial Intelligence")
    print(f"Found {len(ai_articles)} AI article(s):")
    for art in ai_articles:
        print(f"- {art['title']}")

    # Demonstrate Source Sub-filtering
    print("\n--- Filtering by Source: 'HardwareWeekly' ---")
    hw_articles = filter_engine.filter_by_source(clean_articles, "HardwareWeekly")
    print(f"Found {len(hw_articles)} HardwareWeekly article(s):")
    for art in hw_articles:
        print(f"- {art['title']}")