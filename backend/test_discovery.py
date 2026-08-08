from intelligence.discovery import discover_arxiv_topics

print("Starting arXiv test...")

topics = discover_arxiv_topics(limit=5)

print("Topics discovered:", len(topics))

for topic in topics:
    print("Title:", topic.title)