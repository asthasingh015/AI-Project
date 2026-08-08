def calculate_trend_score(
    recency,
    source_strength,
    community_interest,
    technical_importance,
    cross_source_confirmation
):
    score = (
        recency * 0.20
        + source_strength * 0.20
        + community_interest * 0.25
        + technical_importance * 0.20
        + cross_source_confirmation * 0.15
    )

    return round(score, 2)


def get_trend_level(score):

    if score >= 90:
        return "VERY HIGH"

    elif score >= 75:
        return "HIGH"

    elif score >= 50:
        return "MEDIUM"

    else:
        return "LOW"