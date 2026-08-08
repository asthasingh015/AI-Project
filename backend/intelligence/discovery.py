import requests

from .models import Topic


def is_ai_topic(title):

    keywords = [
        "ai",
        "artificial intelligence",
        "machine learning",
        "llm",
        "gpt",
        "gemini",
        "claude",
        "openai",
        "anthropic",
        "google deepmind",
        "hugging face",
        "robotics",
        "neural network",
        "generative ai",
        "agent",
        "ai agent",
        "transformer",
        "deep learning"
    ]

    title_lower = title.lower()

    for keyword in keywords:
        if keyword in title_lower:
            return True

    return False


def discover_topics(limit=10):

    url = "https://hacker-news.firebaseio.com/v0/newstories.json"

    response = requests.get(url, timeout=10)
    response.raise_for_status()

    story_ids = response.json()

    topics = []

    for story_id in story_ids[:limit]:

        story_url = (
            f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json"
        )

        story_response = requests.get(
            story_url,
            timeout=10
        )

        story_response.raise_for_status()

        story = story_response.json()

        if not story:
            continue

        title = story.get("title")

        if not title:
            continue

        if not is_ai_topic(title):
            continue

        url = story.get(
            "url",
            f"https://news.ycombinator.com/item?id={story_id}"
        )

        topic = Topic(
            title=title,
            description=title,
            category="Technology",
            source="Hacker News",
            url=url
        )

        topics.append(topic)

    return topics


def discover_arxiv_topics(limit=5):

    url = "https://export.arxiv.org/api/query"

    params = {
        "search_query": "cat:cs.AI OR cat:cs.LG OR cat:cs.RO",
        "start": 0,
        "max_results": limit,
        "sortBy": "submittedDate",
        "sortOrder": "descending"
    }

    response = requests.get(
        url,
        params=params,
        timeout=15
    )

    response.raise_for_status()

    return []