from intelligence.editorial_brain import make_editorial_decision


result = make_editorial_decision(
    trend_score=90,
    source_confidence=95,
    technical_relevance=90,
    is_duplicate=True
)

print("Decision:", result["decision"])
print("Reason:", result["reason"])