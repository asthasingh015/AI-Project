
"""
Cortex AI Discovery Engine - Article Scorer Module

Module: scorer.py

Purpose:
    Receives clean, normalized article dictionaries from filter.py and
    assigns a quality/relevance score to each article.

    Ranking considers:
        1. Source priority
        2. Title quality
        3. Description quality
        4. Freshness
        5. AI/ML topic relevance
        6. Research/technical relevance
        7. Category relevance
        8. Keyword placement and diversity

Design goals:
    - Stable 0-100 scoring
    - AI/ML-focused ranking
    - Defensive handling of missing fields
    - No mutation of original article dictionaries
    - Explainable score breakdown
    - Deterministic ranking
"""

from dataclasses import dataclass
from datetime import datetime, timezone
import logging
import re
from typing import Any, Dict, List, Optional


logger = logging.getLogger(__name__)


# =============================================================================
# Configuration
# =============================================================================

@dataclass(frozen=True)
class ScoreConfig:
    """
    Configuration for the article scoring engine.

    The weights intentionally give topic relevance a strong influence so that
    AI/ML-related articles rank above generic technology articles.
    """

    # Main score components
    source_priority_weight: float = 20.0
    title_quality_weight: float = 15.0
    description_quality_weight: float = 10.0
    freshness_weight: float = 20.0
    topic_relevance_weight: float = 30.0

    # Additional relevance bonus
    research_bonus: float = 3.0
    category_bonus: float = 2.0

    max_score: float = 100.0

    # -------------------------------------------------------------------------
    # AI / ML vocabulary
    # -------------------------------------------------------------------------

    ai_keywords: tuple[str, ...] = (
        "artificial intelligence",
        "machine learning",
        "deep learning",
        "generative ai",
        "large language model",
        "large language models",
        "llm",
        "llms",
        "transformer",
        "transformers",
        "natural language processing",
        "nlp",
        "computer vision",
        "neural network",
        "neural networks",
        "foundation model",
        "foundation models",
        "agentic ai",
        "ai agent",
        "ai agents",
        "autonomous agent",
        "autonomous agents",
        "reinforcement learning",
        "robotics",
        "multimodal ai",
        "multimodal model",
        "diffusion model",
        "generative model",
        "generative models",
        "embedding",
        "embeddings",
        "rag",
        "retrieval augmented generation",
        "fine tuning",
        "fine-tuning",
        "prompt engineering",
        "ai safety",
        "responsible ai",
        "machine intelligence",
        "computer intelligence",
    )

    # -------------------------------------------------------------------------
    # Research / technical vocabulary
    # -------------------------------------------------------------------------

    research_keywords: tuple[str, ...] = (
        "arxiv",
        "research",
        "research paper",
        "paper",
        "study",
        "benchmark",
        "benchmarks",
        "dataset",
        "datasets",
        "journal",
        "thesis",
        "preprint",
        "experiment",
        "experimental",
        "evaluation",
        "evaluations",
        "results",
        "model evaluation",
        "accuracy",
        "f1 score",
        "precision",
        "recall",
        "inference",
        "training",
        "training data",
    )

    # -------------------------------------------------------------------------
    # Technology keywords
    # -------------------------------------------------------------------------

    technology_keywords: tuple[str, ...] = (
        "python",
        "javascript",
        "typescript",
        "java",
        "golang",
        "go",
        "rust",
        "api",
        "backend",
        "frontend",
        "full stack",
        "software",
        "programming",
        "developer",
        "database",
        "cloud",
        "aws",
        "azure",
        "google cloud",
        "kubernetes",
        "docker",
        "linux",
        "cybersecurity",
        "security",
        "data science",
        "data engineering",
    )

    # -------------------------------------------------------------------------
    # AI/ML categories
    # -------------------------------------------------------------------------

    relevant_categories: tuple[str, ...] = (
        "artificial intelligence",
        "ai",
        "machine learning",
        "deep learning",
        "data science",
        "robotics",
        "computer vision",
        "natural language processing",
        "nlp",
        "generative ai",
        "technology",
    )


# =============================================================================
# Article Scorer
# =============================================================================

class ArticleScorer:
    """
    Evaluates, scores and ranks normalized articles.

    The scorer does not modify the original article dictionary.
    """

    def __init__(
        self,
        config: Optional[ScoreConfig] = None,
    ) -> None:
        """Initialize the scorer."""

        self.config = config or ScoreConfig()

        logger.info(
            "ArticleScorer initialized successfully."
        )

    # =========================================================================
    # Utility Methods
    # =========================================================================

    @staticmethod
    def _normalize_text(value: Any) -> str:
        """Convert arbitrary input into normalized searchable text."""

        if value is None:
            return ""

        try:
            text = str(value).strip().lower()

            # Normalize common separators
            text = text.replace("_", " ")
            text = text.replace("-", " ")

            # Collapse whitespace
            text = re.sub(r"\s+", " ", text)

            return text

        except Exception:
            return ""

    @staticmethod
    def _get_tags_text(article: Dict[str, Any]) -> str:
        """Return article tags as searchable text."""

        tags = article.get("tags") or []

        if isinstance(tags, (list, tuple, set)):
            return " ".join(
                ArticleScorer._normalize_text(tag)
                for tag in tags
            )

        return ArticleScorer._normalize_text(tags)

    @staticmethod
    def _contains_keyword(
        text: str,
        keyword: str,
    ) -> bool:
        """
        Safely detect a keyword.

        Short keywords such as 'ai', 'go', 'nlp' use word boundaries.
        Longer phrases use normalized substring matching.
        """

        keyword_normalized = ArticleScorer._normalize_text(keyword)

        if not keyword_normalized:
            return False

        if len(keyword_normalized) <= 3:
            return bool(
                re.search(
                    rf"\b{re.escape(keyword_normalized)}\b",
                    text,
                )
            )

        return keyword_normalized in text

    # =========================================================================
    # Stage 1 - Source Priority
    # =========================================================================

    def _score_source_priority(
        self,
        article: Dict[str, Any],
    ) -> float:
        """
        Score source priority.

        Priority:
            1 -> 100%
            2 -> 80%
            3 -> 60%
            4 -> 40%
        """

        try:
            priority = article.get("priority", 4)

            if not isinstance(priority, int):
                priority = 4

            multiplier_map = {
                1: 1.00,
                2: 0.80,
                3: 0.60,
                4: 0.40,
            }

            multiplier = multiplier_map.get(
                priority,
                0.40,
            )

            return (
                self.config.source_priority_weight
                * multiplier
            )

        except Exception as err:
            logger.warning(
                "Source priority scoring failed: %s",
                err,
            )

            return (
                self.config.source_priority_weight
                * 0.40
            )

    # =========================================================================
    # Stage 2 - Title Quality
    # =========================================================================

    def _score_title_quality(
        self,
        article: Dict[str, Any],
    ) -> float:
        """
        Evaluate title quality.

        Good titles are:
            - informative
            - readable
            - neither too short nor too long
            - not excessive in punctuation
            - not ALL CAPS
        """

        try:
            title = article.get("title")

            if not isinstance(title, str):
                return 0.0

            title = title.strip()

            if not title:
                return 0.0

            length = len(title)

            # -------------------------------------------------------------
            # Length score
            # -------------------------------------------------------------

            if 40 <= length <= 110:
                score = 1.00

            elif 25 <= length < 40:
                score = 0.85

            elif 110 < length <= 150:
                score = 0.85

            elif 15 <= length < 25:
                score = 0.65

            elif 150 < length <= 200:
                score = 0.65

            else:
                score = 0.45

            # -------------------------------------------------------------
            # ALL CAPS penalty
            # -------------------------------------------------------------

            if title.isupper() and length > 10:
                score *= 0.70

            # -------------------------------------------------------------
            # Excessive punctuation penalty
            # -------------------------------------------------------------

            punctuation_count = len(
                re.findall(r"[!?]{2,}", title)
            )

            if punctuation_count > 0:
                score *= 0.85

            # -------------------------------------------------------------
            # Excessive repeated characters
            # -------------------------------------------------------------

            if re.search(r"(.)\1{4,}", title):
                score *= 0.80

            return (
                self.config.title_quality_weight
                * score
            )

        except Exception as err:
            logger.warning(
                "Title scoring failed: %s",
                err,
            )

            return 0.0

    # =========================================================================
    # Stage 3 - Description Quality
    # =========================================================================

    def _score_description_quality(
        self,
        article: Dict[str, Any],
    ) -> float:
        """Evaluate description completeness and information density."""

        try:
            description = article.get("description")

            if not isinstance(description, str):
                return 0.0

            description = description.strip()

            if not description:
                return 0.0

            word_count = len(
                description.split()
            )

            character_count = len(
                description
            )

            if (
                word_count >= 40
                and character_count >= 250
            ):
                multiplier = 1.00

            elif (
                word_count >= 25
                and character_count >= 150
            ):
                multiplier = 0.85

            elif (
                word_count >= 12
                and character_count >= 70
            ):
                multiplier = 0.65

            elif word_count >= 5:
                multiplier = 0.45

            else:
                multiplier = 0.25

            return (
                self.config.description_quality_weight
                * multiplier
            )

        except Exception as err:
            logger.warning(
                "Description scoring failed: %s",
                err,
            )

            return 0.0

    # =========================================================================
    # Stage 4 - Freshness
    # =========================================================================

    def _score_freshness(
        self,
        article: Dict[str, Any],
    ) -> float:
        """Score article freshness using publication timestamp."""

        try:
            published = article.get("published")

            if not isinstance(published, str):
                return (
                    self.config.freshness_weight
                    * 0.40
                )

            published = (
                published
                .strip()
                .replace("Z", "+00:00")
            )

            published_dt = datetime.fromisoformat(
                published
            )

            if published_dt.tzinfo is None:
                published_dt = published_dt.replace(
                    tzinfo=timezone.utc
                )

            now = datetime.now(timezone.utc)

            age_hours = (
                now - published_dt
            ).total_seconds() / 3600.0

            # Future timestamps are treated as current.
            if age_hours < 0:
                age_hours = 0

            # -------------------------------------------------------------
            # Freshness curve
            # -------------------------------------------------------------

            if age_hours <= 3:
                multiplier = 1.00

            elif age_hours <= 6:
                multiplier = 0.98

            elif age_hours <= 12:
                multiplier = 0.94

            elif age_hours <= 24:
                multiplier = 0.88

            elif age_hours <= 48:
                multiplier = 0.72

            elif age_hours <= 72:
                multiplier = 0.60

            elif age_hours <= 168:
                multiplier = 0.42

            elif age_hours <= 336:
                multiplier = 0.25

            else:
                multiplier = 0.12

            return (
                self.config.freshness_weight
                * multiplier
            )

        except Exception as err:
            logger.debug(
                "Freshness scoring fallback for '%s': %s",
                article.get("published"),
                err,
            )

            return (
                self.config.freshness_weight
                * 0.40
            )

    # =========================================================================
    # Stage 5 - Topic Relevance
    # =========================================================================

    def _score_topic_relevance(
        self,
        article: Dict[str, Any],
    ) -> float:
        """
        Calculate AI/ML relevance.

        Important design choice:

        A keyword appearing in the TITLE is more important than the same
        keyword appearing only in the description.

        This prevents generic technology articles from receiving the same
        score as genuinely AI/ML-focused articles.
        """

        try:
            title = self._normalize_text(
                article.get("title")
            )

            description = self._normalize_text(
                article.get("description")
            )

            tags = self._get_tags_text(
                article
            )

            category = self._normalize_text(
                article.get("category")
            )

            # -------------------------------------------------------------
            # Find AI keywords
            # -------------------------------------------------------------

            matched_keywords = []

            for keyword in self.config.ai_keywords:

                if self._contains_keyword(
                    title,
                    keyword,
                ):
                    matched_keywords.append(
                        keyword
                    )

            # -------------------------------------------------------------
            # Keyword diversity
            # -------------------------------------------------------------

            # More unique AI concepts = stronger relevance.
            unique_ai_count = len(
                set(matched_keywords)
            )

            # Base relevance points.
            if unique_ai_count == 0:
                ai_relevance = 0.0

            elif unique_ai_count == 1:
                ai_relevance = 8.0

            elif unique_ai_count == 2:
                ai_relevance = 14.0

            elif unique_ai_count == 3:
                ai_relevance = 19.0

            elif unique_ai_count == 4:
                ai_relevance = 23.0

            else:
                ai_relevance = 27.0

            # -------------------------------------------------------------
            # Description AI keywords
            # -------------------------------------------------------------

            description_matches = 0

            for keyword in self.config.ai_keywords:

                if self._contains_keyword(
                    description,
                    keyword,
                ):
                    description_matches += 1

            # Description reinforces relevance.
            description_bonus = min(
                description_matches * 1.25,
                5.0,
            )

            # -------------------------------------------------------------
            # Tags AI keywords
            # -------------------------------------------------------------

            tag_matches = 0

            for keyword in self.config.ai_keywords:

                if self._contains_keyword(
                    tags,
                    keyword,
                ):
                    tag_matches += 1

            tag_bonus = min(
                tag_matches * 1.5,
                5.0,
            )

            # -------------------------------------------------------------
            # Strong title signal
            # -------------------------------------------------------------

            strong_title_terms = (
                "artificial intelligence",
                "machine learning",
                "deep learning",
                "generative ai",
                "large language model",
                "llm",
                "agentic ai",
                "computer vision",
                "neural network",
                "foundation model",
                "reinforcement learning",
            )

            strong_title_match = any(
                self._contains_keyword(
                    title,
                    keyword,
                )
                for keyword in strong_title_terms
            )

            title_relevance_bonus = (
                3.0
                if strong_title_match
                else 0.0
            )

            # -------------------------------------------------------------
            # Research relevance
            # -------------------------------------------------------------

            research_matches = 0

            combined_text = (
                f"{title} "
                f"{description} "
                f"{tags}"
            )

            for keyword in self.config.research_keywords:

                if self._contains_keyword(
                    combined_text,
                    keyword,
                ):
                    research_matches += 1

            research_bonus = min(
                research_matches * 0.75,
                self.config.research_bonus,
            )

            # -------------------------------------------------------------
            # Category relevance
            # -------------------------------------------------------------

            category_bonus = 0.0

            for relevant_category in (
                self.config.relevant_categories
            ):

                if (
                    relevant_category
                    in category
                ):
                    category_bonus = (
                        self.config.category_bonus
                    )
                    break

            # -------------------------------------------------------------
            # Generic technology penalty
            # -------------------------------------------------------------

            # If the article has no AI signal anywhere, do not allow it
            # to receive a high topic-relevance score.
            if (
                unique_ai_count == 0
                and description_matches == 0
                and tag_matches == 0
            ):
                ai_relevance = 0.0

            # -------------------------------------------------------------
            # Final relevance
            # -------------------------------------------------------------

            relevance = (
                ai_relevance
                + description_bonus
                + tag_bonus
                + title_relevance_bonus
                + research_bonus
                + category_bonus
            )

            return min(
                relevance,
                self.config.topic_relevance_weight,
            )

        except Exception as err:
            logger.warning(
                "Topic relevance scoring failed: %s",
                err,
            )

            return 0.0

    # =========================================================================
    # Score One Article
    # =========================================================================

    def score_article(
        self,
        article: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Score one article.

        Returns a NEW dictionary so the original article remains unchanged.
        """

        if not isinstance(article, dict):
            logger.error(
                "score_article received invalid type: %s",
                type(article),
            )
            return {}

        source_score = (
            self._score_source_priority(
                article
            )
        )

        title_score = (
            self._score_title_quality(
                article
            )
        )

        description_score = (
            self._score_description_quality(
                article
            )
        )

        freshness_score = (
            self._score_freshness(
                article
            )
        )

        relevance_score = (
            self._score_topic_relevance(
                article
            )
        )

        # -------------------------------------------------------------
        # Final score
        # -------------------------------------------------------------

        raw_score = (
            source_score
            + title_score
            + description_score
            + freshness_score
            + relevance_score
        )

        final_score = min(
            max(raw_score, 0.0),
            self.config.max_score,
        )

        # -------------------------------------------------------------
        # Breakdown
        # -------------------------------------------------------------

        breakdown = {
            "source_priority": round(
                source_score,
                2,
            ),
            "title_quality": round(
                title_score,
                2,
            ),
            "description_quality": round(
                description_score,
                2,
            ),
            "freshness": round(
                freshness_score,
                2,
            ),
            "topic_relevance": round(
                relevance_score,
                2,
            ),
        }

        # -------------------------------------------------------------
        # Create a new article object
        # -------------------------------------------------------------

        scored_article = article.copy()

        scored_article["score"] = round(
            final_score,
            2,
        )

        scored_article[
            "score_breakdown"
        ] = breakdown

        return scored_article

    # =========================================================================
    # Score Multiple Articles
    # =========================================================================

    def score_articles(
        self,
        articles: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Score a list of articles safely."""

        if not isinstance(articles, list):
            logger.error(
                "score_articles expected list, received %s",
                type(articles),
            )
            return []

        scored_articles = []

        for index, article in enumerate(
            articles
        ):

            if not isinstance(article, dict):
                logger.warning(
                    "Skipping invalid article at index %d.",
                    index,
                )
                continue

            try:

                scored = self.score_article(
                    article
                )

                if scored:
                    scored_articles.append(
                        scored
                    )

            except Exception as err:

                logger.error(
                    "Failed scoring article at index %d: %s",
                    index,
                    err,
                    exc_info=True,
                )

        logger.info(
            "Scored %d out of %d articles.",
            len(scored_articles),
            len(articles),
        )

        return scored_articles

    # =========================================================================
    # Ranking
    # =========================================================================

    def rank_articles(
        self,
        articles: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Score and rank articles in descending order.

        Articles are always re-scored so changes in freshness or configuration
        are reflected immediately.
        """

        if not isinstance(articles, list):
            return []

        scored_articles = []

        for article in articles:

            if not isinstance(article, dict):
                continue

            try:
                scored_articles.append(
                    self.score_article(article)
                )

            except Exception as err:

                logger.error(
                    "Unable to rank article '%s': %s",
                    article.get("title"),
                    err,
                    exc_info=True,
                )

        # -------------------------------------------------------------
        # Deterministic sorting
        # -------------------------------------------------------------

        return sorted(
            scored_articles,
            key=lambda item: (
                item.get("score", 0.0),
                item.get("published", ""),
                item.get("title", ""),
            ),
            reverse=True,
        )


# =============================================================================
# Local Demonstration
# =============================================================================

if __name__ == "__main__":

    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s "
            "[%(levelname)s] "
            "%(name)s: %(message)s"
        ),
    )

    logger.info(
        "Starting local scorer demonstration..."
    )

    sample_articles = [
        {
            "title": (
                "Agentic AI Frameworks for "
                "Autonomous Machine Learning Research"
            ),
            "url": "https://example.com/ai",
            "description": (
                "A research paper evaluating foundation models, "
                "large language models and multi-agent systems "
                "using benchmarks and experimental results."
            ),
            "published": (
                "2026-08-08T16:00:00Z"
            ),
            "source_name": "AI Research Journal",
            "source_url": "https://example.com",
            "category": "Artificial Intelligence",
            "priority": 1,
            "tags": [
                "AI",
                "LLM",
                "Research",
                "Agentic AI",
            ],
        },
        {
            "title": (
                "New Computer Vision Chip "
                "Released for Robotics"
            ),
            "url": "https://example.com/cv",
            "description": (
                "New hardware designed for robotics "
                "and computer vision applications."
            ),
            "published": (
                "2026-08-08T10:00:00Z"
            ),
            "source_name": "TechDaily",
            "source_url": "https://example.com",
            "category": "Technology",
            "priority": 3,
            "tags": [
                "Computer Vision",
                "Robotics",
            ],
        },
        {
            "title": (
                "General Programming Updates "
                "and Patch Notes"
            ),
            "url": "https://example.com/programming",
            "description": (
                "Standard bug fixes and internal "
                "refactoring updates for web applications."
            ),
            "published": (
                "2026-08-01T12:00:00Z"
            ),
            "source_name": "DevBlog",
            "source_url": "https://example.com",
            "category": "Software",
            "priority": 4,
            "tags": [
                "Programming",
                "Web",
            ],
        },
    ]

    scorer = ArticleScorer()

    ranked = scorer.rank_articles(
        sample_articles
    )

    print()
    print("=" * 70)
    print("CORTEX AI DISCOVERY ENGINE")
    print("ARTICLE SCORER TEST")
    print("=" * 70)

    for rank, article in enumerate(
        ranked,
        start=1,
    ):

        print()
        print(
            f"Rank #{rank}: "
            f"{article.get('title')}"
        )

        print(
            f"Score: "
            f"{article.get('score')} / 100"
        )

        print("Breakdown:")

        for key, value in (
            article.get(
                "score_breakdown",
                {}
            ).items()
        ):

            print(
                f"  {key}: {value}"
            )

    # -------------------------------------------------------------
    # Immutability test
    # -------------------------------------------------------------

    print()
    print("=" * 70)
    print("IMMUTABILITY CHECK")
    print("=" * 70)

    print(
        "Original article contains score:",
        "score" in sample_articles[0],
    )

    print(
        "Expected:",
        False,
    )

