from .discovery import (
    discover_topics,
    discover_arxiv_topics,
    normalize_title
)

from .trend_analyzer import calculate_trend_score
from .source_validator import calculate_source_confidence
from .editorial_brain import make_editorial_decision
from .memory import is_duplicate_topic, remember_topic
from .content_generator import generate_article


def has_cross_source_match(topic, other_topics):

    topic_words = normalize_title(topic.title)

    for other_topic in other_topics:

        other_words = normalize_title(other_topic.title)

        common_words = topic_words.intersection(other_words)

        if len(common_words) >= 2:
            return True

    return False


def run_intelligence_pipeline():

    hacker_news_topics = discover_topics(limit=20)

    arxiv_topics = discover_arxiv_topics(limit=5)

    topics = hacker_news_topics + arxiv_topics

    results = []

    for topic in topics:

        if topic.source == "Hacker News":

            other_topics = arxiv_topics

            source_strength = 80
            technical_importance = 75
            community_interest = 85

        else:

            other_topics = hacker_news_topics

            source_strength = 95
            technical_importance = 95
            community_interest = 70

        cross_source_match = has_cross_source_match(
            topic,
            other_topics
        )

        duplicate = is_duplicate_topic(
            topic.title
        )

        recency = 90

        if cross_source_match:

            cross_source_confirmation = 100
            source_count = 2

        else:

            cross_source_confirmation = 40
            source_count = 1

        trend_score = calculate_trend_score(
            recency=recency,
            source_strength=source_strength,
            community_interest=community_interest,
            technical_importance=technical_importance,
            cross_source_confirmation=cross_source_confirmation
        )

        source_confidence = calculate_source_confidence(
            source_count,
            source_strength
        )

        editorial_result = make_editorial_decision(
            trend_score=trend_score,
            source_confidence=source_confidence,
            technical_relevance=technical_importance,
            is_duplicate=duplicate
        )

        article = None

        if editorial_result["decision"] == "ACCEPT":

            article = generate_article(topic)

            remember_topic(
                title=topic.title,
                source=topic.source
            )

        result = {
            "topic": topic.title,
            "category": topic.category,
            "source": topic.source,
            "trend_score": trend_score,
            "source_confidence": source_confidence,
            "decision": editorial_result["decision"],
            "reason": editorial_result["reason"],
            "article": article
        }

        results.append(result)

    return results