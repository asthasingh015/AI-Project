from intelligence.intelligence_pipeline import run_intelligence_pipeline


results = run_intelligence_pipeline()


for result in results:

    print("\n-----------------------------")

    print("Topic:", result["topic"])
    print("Category:", result["category"])
    print("Trend Score:", result["trend_score"])
    print("Source Confidence:", result["source_confidence"])
    print("Decision:", result["decision"])
    print("Reason:", result["reason"])