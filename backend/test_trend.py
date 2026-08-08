from intelligence.trend_analyzer import (
    calculate_trend_score,
    get_trend_level
)


score = calculate_trend_score(
    recency=95,
    source_strength=90,
    community_interest=88,
    technical_importance=92,
    cross_source_confirmation=85
)

level = get_trend_level(score)

print("Trend Score:", score)
print("Trend Level:", level)