from intelligence.discovery import discover_arxiv_topics
from intelligence.content_generator import generate_article


print("Finding fresh arXiv topic...")

topics = discover_arxiv_topics(limit=1)

if not topics:

    print("No topic found.")

else:

    topic = topics[0]

    print("\nTopic found:")
    print(topic.title)

    article = generate_article(topic)

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