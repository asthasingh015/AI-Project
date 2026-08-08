"""
Cortex AI Discovery Engine - Article Scorer Module

Module: scorer.py
Purpose: Receives clean, normalized article dictionaries from filter.py and assigns
         a quality/relevance score to each article. It ranks articles based on
         source priority, title and description quality, published freshness, and AI/ML topic relevance.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
import re
from typing import Any, Dict, List, Optional

# Configure logger
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ScoreConfig:
    """Configurable weights, limits, and keyword criteria for article scoring."""

    source_priority_weight: float = 25.0
    title_quality_weight: float = 15.0
    description_quality_weight: float = 15.0
    freshness_weight: float = 20.0
    topic_relevance_weight: float = 20.0
    research_bonus: float = 5.0
    ai_keyword_bonus: float = 2.5
    max_score: float = 100.0

    ai_keywords: tuple[str, ...] = (
        "ai",
        "artificial intelligence",
        "machine learning",
        "deep learning",
        "llm",
        "generative ai",
        "transformer",
        "nlp",
        "computer vision",
        "robotics",
        "neural network",
        "foundation model",
        "agentic ai",
    )

    research_keywords: tuple[str, ...] = (
        "arxiv",
        "paper",
        "research",
        "study",
        "benchmark",
        "dataset",
        "journal",
        "thesis",
        "preprint",
    )


class ArticleScorer:
    """
    Evaluates, scores, and ranks articles processed by the discovery engine.
    Ensures zero side-effects on original article data and handles missing fields defensively.
    """

    def __init__(self, config: Optional[ScoreConfig] = None) -> None:
        """Initialize ArticleScorer with custom or default configuration."""
        self.config = config or ScoreConfig()

    def _score_source_priority(self, article: Dict[str, Any]) -> float:
        """
        Scores article based on source priority hierarchy.
        Priority 1 (Highest) -> 1.0 multiplier
        Priority 2 (High)    -> 0.75 multiplier
        Priority 3 (Medium)  -> 0.50 multiplier
        Priority 4 (Low)     -> 0.25 multiplier
        """
        try:
            priority = article.get("priority", 4)
            if not isinstance(priority, int) or priority not in (1, 2, 3, 4):
                priority = 4

            multiplier_map = {1: 1.0, 2: 0.75, 3: 0.50, 4: 0.25}
            multiplier = multiplier_map.get(priority, 0.25)
            return self.config.source_priority_weight * multiplier
        except Exception as err:
            logger.warning("Error scoring source priority: %s", err)
            return self.config.source_priority_weight * 0.25

    def _score_title_quality(self, article: Dict[str, Any]) -> float:
        """
        Evaluates title length, casing, and formatting quality.
        Optimal length: 30 to 120 characters.
        """
        try:
            title = article.get("title")
            if not isinstance(title, str) or not title.strip():
                return 0.0

            clean_title = title.strip()
            length = len(clean_title)

            # Ideal length range
            if 30 <= length <= 120:
                multiplier = 1.0
            elif 15 <= length < 30 or 120 < length <= 180:
                multiplier = 0.7
            else:
                multiplier = 0.4

            # Penalize ALL CAPS titles
            if clean_title.isupper() and length > 10:
                multiplier *= 0.5

            return self.config.title_quality_weight * multiplier
        except Exception as err:
            logger.warning("Error scoring title quality: %s", err)
            return 0.0

    def _score_description_quality(self, article: Dict[str, Any]) -> float:
        """
        Evaluates description length, word density, and structure.
        """
        try:
            desc = article.get("description")
            if not isinstance(desc, str) or not desc.strip():
                return 0.0

            clean_desc = desc.strip()
            length = len(clean_desc)
            word_count = len(clean_desc.split())

            if length >= 120 and word_count >= 20:
                multiplier = 1.0
            elif length >= 50 and word_count >= 8:
                multiplier = 0.7
            elif length > 0:
                multiplier = 0.4
            else:
                multiplier = 0.0

            return self.config.description_quality_weight * multiplier
        except Exception as err:
            logger.warning("Error scoring description quality: %s", err)
            return 0.0

    def _score_freshness(self, article: Dict[str, Any]) -> float:
        """
        Scores article freshness based on ISO published timestamp relative to current time.
        """
        try:
            published = article.get("published")
            if not published or not isinstance(published, str):
                return self.config.freshness_weight * 0.5  # Default baseline for missing timestamp

            # Parse ISO date string defensively
            pub_str = published.strip().replace("Z", "+00:00")
            pub_dt = datetime.fromisoformat(pub_str)

            if pub_dt.tzinfo is None:
                pub_dt = pub_dt.replace(tzinfo=timezone.utc)

            now = datetime.now(timezone.utc)
            age_hours = (now - pub_dt).total_seconds() / 3600.0

            if age_hours <= 0:  # Future date or current
                multiplier = 1.0
            elif age_hours <= 6:
                multiplier = 1.0
            elif age_hours <= 24:
                multiplier = 0.85
            elif age_hours <= 48:
                multiplier = 0.65
            elif age_hours <= 168:  # 1 week
                multiplier = 0.40
            else:
                multiplier = 0.15

            return self.config.freshness_weight * multiplier
        except Exception as err:
            logger.debug("Freshness scoring fallback for published value '%s': %s", article.get("published"), err)
            return self.config.freshness_weight * 0.5

    def _score_topic_relevance(self, article: Dict[str, Any]) -> float:
        """
        Evaluates presence of AI/ML domain terms and scientific research indicators.
        Calculates topic relevance score with keyword and research bonuses.
        """
        try:
            title = str(article.get("title") or "").lower()
            description = str(article.get("description") or "").lower()
            tags = article.get("tags") or []
            tags_text = " ".join(str(t).lower() for t in tags) if isinstance(tags, (list, tuple, set)) else ""

            combined_text = f"{title} {description} {tags_text}"

            # 1. AI Keyword Bonuses
            matched_ai_keywords = set()
            for kw in self.config.ai_keywords:
                # Use boundary check for short acronyms like 'ai'
                if len(kw) <= 3:
                    if re.search(r"\b" + re.escape(kw) + r"\b", combined_text):
                        matched_ai_keywords.add(kw)
                else:
                    if kw in combined_text:
                        matched_ai_keywords.add(kw)

            ai_score = len(matched_ai_keywords) * self.config.ai_keyword_bonus
            ai_score = min(ai_score, self.config.topic_relevance_weight)

            # 2. Research Bonus
            has_research_term = any(r_kw in combined_text for r_kw in self.config.research_keywords)
            r_bonus = self.config.research_bonus if has_research_term else 0.0

            return ai_score + r_bonus
        except Exception as err:
            logger.warning("Error scoring topic relevance: %s", err)
            return 0.0

    def score_article(self, article: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculates individual component scores and returns a NEW dictionary with 'score'
        and 'score_breakdown' appended. Does not modify input article.
        """
        if not isinstance(article, dict):
            logger.error("score_article received non-dictionary input: %s", type(article))
            return {}

        source_score = self._score_source_priority(article)
        title_score = self._score_title_quality(article)
        desc_score = self._score_description_quality(article)
        freshness_score = self._score_freshness(article)
        relevance_score = self._score_topic_relevance(article)

        raw_total = source_score + title_score + desc_score + freshness_score + relevance_score
        final_score = min(max(raw_total, 0.0), self.config.max_score)

        breakdown = {
            "source_priority": round(source_score, 2),
            "title_quality": round(title_score, 2),
            "description_quality": round(desc_score, 2),
            "freshness": round(freshness_score, 2),
            "topic_relevance": round(relevance_score, 2),
        }

        # Create a new dictionary without mutating the original input
        scored_article = article.copy()
        scored_article["score"] = round(final_score, 2)
        scored_article["score_breakdown"] = breakdown

        return scored_article

    def score_articles(self, articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Batch scores a list of article dictionaries safely. Skips invalid items.
        """
        if not isinstance(articles, list):
            logger.error("score_articles expected list input, received %s", type(articles))
            return []

        scored_list: List[Dict[str, Any]] = []
        for idx, art in enumerate(articles):
            if not isinstance(art, dict):
                logger.warning("Skipping invalid item at index %d (not a dictionary).", idx)
                continue

            try:
                scored = self.score_article(art)
                if scored:
                    scored_list.append(scored)
            except Exception as err:
                logger.error("Failed to score article at index %d: %s", idx, err, exc_info=True)

        logger.info("Scored %d out of %d incoming articles.", len(scored_list), len(articles))
        return scored_list

    def rank_articles(self, articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Scores articles (if unscored) and returns them sorted by score in descending order.
        """
        if not isinstance(articles, list):
            return []

        # Ensure all articles have scores
        scored_articles: List[Dict[str, Any]] = []
        for art in articles:
            if isinstance(art, dict):
                if "score" in art and isinstance(art["score"], (int, float)):
                    scored_articles.append(art)
                else:
                    scored_articles.append(self.score_article(art))

        # Sort descending by score
        return sorted(scored_articles, key=lambda x: x.get("score", 0.0), reverse=True)


# -----------------------------------------------------------------------------
# Local Demonstration Block
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    logger.info("Starting local test demonstration for scorer.py ...")

    # Sample test dataset mimicking clean articles from filter.py
    sample_clean_articles: List[Dict[str, Any]] = [
        {
            "title": "Agentic AI Frameworks for Autonomous Machine Learning Research",
            "url": "https://ai-journal.org/articles/agentic-ai-frameworks",
            "description": "A comprehensive research paper evaluating foundation models and multi-agent systems on benchmarks.",
            "published": "2026-08-08T16:00:00Z",
            "source_name": "AI Journal",
            "source_url": "https://ai-journal.org",
            "category": "Artificial Intelligence",
            "priority": 1,
            "tags": ["Agentic AI", "LLM", "Research", "Benchmark"],
        },
        {
            "title": "New Computer Vision Chip Released",
            "url": "https://tech-daily.com/cv-chip-release",
            "description": "A brief overview of new hardware designed for robotics and deep learning applications.",
            "published": "2026-08-07T10:00:00Z",
            "source_name": "TechDaily",
            "source_url": "https://tech-daily.com",
            "category": "Hardware",
            "priority": 3,
            "tags": ["Computer Vision", "Robotics"],
        },
        {
            "title": "General Programming Updates and Patch Notes",
            "url": "https://dev-blog.net/updates-august",
            "description": "Standard bug fixes and internal refactoring updates for web applications.",
            "published": "2026-08-01T12:00:00Z",
            "source_name": "DevBlog",
            "source_url": "https://dev-blog.net",
            "category": "Software",
            "priority": 4,
            "tags": ["Dev", "Web"],
        },
    ]

    scorer = ArticleScorer()

    print("\n--- Scoring and Ranking Test Articles ---")
    ranked_articles = scorer.rank_articles(sample_clean_articles)

    for rank, item in enumerate(ranked_articles, 1):
        print(f"\nRank #{rank}: {item['title']}")
        print(f"  Source: {item['source_name']} (Priority {item['priority']})")
        print(f"  Final Score: {item['score']} / 100")
        print("  Breakdown:")
        for component, pts in item["score_breakdown"].items():
            print(f"    - {component}: {pts} pts")

    print("\n--- Immutability Check ---")
    original_has_score = "score" in sample_clean_articles[0]
    print(f"Original article mutated with score field? {original_has_score} (Expected: False)")