from intelligence.content_generator import generate_article
from intelligence.discovery import discover_topics


print("Starting content generator test...")

topics = discover_topics(limit=50)

if not topics:

    print("No topics found.")

else:

    topic = topics[0]

    article = generate_article(topic)

    print("\n==============================")
    print("TITLE:")
    print(article["title"])

    print("\nSUMMARY:")
    print(article["summary"])

    print("\nKEY POINTS:")

    for point in article["key_points"]:
        print("-", point)

    print("\nSOURCE:")
    print(article["source"])

    print("\nURL:")
    print(article["source_url"])

    print("\nCATEGORY:")
    print(article["category"])