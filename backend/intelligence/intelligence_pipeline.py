from .discovery import discover_topics
from .trend_analyzer import calculate_trend_score
from .source_validator import calculate_source_confidence
from .editorial_brain import make_editorial_decision


def run_intelligence_pipeline():

    topics = discover_topics()

    results = []

    for topic in topics:

        # 1. Calculate trend score
        trend_score = calculate_trend_score(
            recency=95,
            source_strength=90,
            community_interest=85,
            technical_importance=90,
            cross_source_confirmation=85
        )

        # 2. Calculate source confidence
        source_confidence = calculate_source_confidence(5)

        # 3. Editorial decision
        editorial_result = make_editorial_decision(
            trend_score=trend_score,
            source_confidence=source_confidence,
            technical_relevance=90,
            is_duplicate=False
        )

        result = {
            "topic": topic.title,
            "category": topic.category,
            "trend_score": trend_score,
            "source_confidence": source_confidence,
            "decision": editorial_result["decision"],
            "reason": editorial_result["reason"]
        }

        results.append(result)

    return results