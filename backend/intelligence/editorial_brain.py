def make_editorial_decision(
    trend_score,
    source_confidence,
    technical_relevance,
    is_duplicate
):

    # Check if this topic was already covered
    if is_duplicate:
        return {
            "decision": "REJECT",
            "reason": "Similar topic was already covered recently."
        }

    # Check trend score
    if trend_score < 50:
        return {
            "decision": "REJECT",
            "reason": "Trend score is too low."
        }

    # Check source confidence
    if source_confidence < 50:
        return {
            "decision": "REJECT",
            "reason": "Source confidence is too low."
        }

    # Check technical relevance
    if technical_relevance < 40:
        return {
            "decision": "REJECT",
            "reason": "Technical relevance is too low."
        }

    # If all checks pass
    return {
        "decision": "ACCEPT",
        "reason": "Topic has strong relevance and sufficient evidence."
    }