from intelligence.intelligence_pipeline import run_intelligence_pipeline


results = run_intelligence_pipeline()


for result in results:

    print("\n-----------------------------")

    print("Topic:", result["topic"])
    print("Category:", result["category"])
    print("Source:", result["source"])
    print("Trend Score:", result["trend_score"])
    print("Source Confidence:", result["source_confidence"])
    print("Decision:", result["decision"])
    print("Reason:", result["reason"])

    article = result.get("article")

    if article:

        print("\n========== GENERATED ARTICLE ==========")

        print("\nTITLE:")
        print(article["title"])

        print("\nSUMMARY:")
        print(article["summary"])

        print("\nKEY POINTS:")

        for point in article["key_points"]:
            print("-", point)

        print("\nSOURCE:")
        print(article["source"])

        print("\nSOURCE URL:")
        print(article["source_url"])

        print("\nCATEGORY:")
        print(article["category"])