import requests
import xml.etree.ElementTree as ET

from .models import Topic


def normalize_title(title):

    stop_words = {
        "the",
        "a",
        "an",
        "and",
        "or",
        "of",
        "to",
        "in",
        "on",
        "for",
        "with",
        "from",
        "how",
        "what",
        "when",
        "via",
        "using",
        "new",
        "ai",
        "model",
        "models",
        "learning",
        "system",
        "systems",
        "this",
        "that",
        "into",
        "their",
        "your",
        "our"
    }

    title = title.lower()

    for character in ",.:;!?-()[]{}":
        title = title.replace(character, " ")

    words = title.split()

    meaningful_words = {
        word
        for word in words
        if word not in stop_words and len(word) > 2
    }

    return meaningful_words


def is_ai_topic(title):

    keywords = [
        "artificial intelligence",
        "machine learning",
        "large language model",
        "language model",
        "llm",
        "gpt",
        "gemini",
        "claude",
        "openai",
        "anthropic",
        "deepmind",
        "hugging face",
        "robotics",
        "neural network",
        "generative ai",
        "ai agent",
        "coding agent",
        "ai app",
        "ai tool",
        "ai system",
        "transformer",
        "deep learning",
        "machine intelligence"
    ]

    title_lower = title.lower()

    for keyword in keywords:
        if keyword in title_lower:
            return True

    return False


def discover_topics(limit=20):

    url = "https://hacker-news.firebaseio.com/v0/newstories.json"

    response = requests.get(
        url,
        timeout=10
    )

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

        title = story.get("title", "")

        if not title:
            continue

        if not is_ai_topic(title):
            continue

        article_url = story.get(
            "url",
            f"https://news.ycombinator.com/item?id={story_id}"
        )

        topic = Topic(
            title=title,
            description=title,
            category="Technology",
            source="Hacker News",
            url=article_url
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

    root = ET.fromstring(response.text)

    namespace = {
        "atom": "http://www.w3.org/2005/Atom"
    }

    topics = []

    for entry in root.findall(
        "atom:entry",
        namespace
    ):

        title_element = entry.find(
            "atom:title",
            namespace
        )

        summary_element = entry.find(
            "atom:summary",
            namespace
        )

        published_element = entry.find(
            "atom:published",
            namespace
        )

        link_element = entry.find(
            "atom:id",
            namespace
        )

        if title_element is None:
            continue

        title = " ".join(
            title_element.text.strip().split()
        )

        description = ""

        if summary_element is not None:
            if summary_element.text:
                description = " ".join(
                    summary_element.text.strip().split()
                )

        published_at = None

        if published_element is not None:
            published_at = published_element.text

        article_url = ""

        if link_element is not None:
            if link_element.text:
                article_url = link_element.text.strip()

        topic = Topic(
            title=title,
            description=description,
            category="AI Research",
            source="arXiv",
            url=article_url,
            published_at=published_at
        )

        topics.append(topic)

    return topics