import requests
import xml.etree.ElementTree as ET

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
        "systems"
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


def discover_topics(limit=10):

    url = "https://hacker-news.firebaseio.com/v0/newstories.json"

    response = requests.get(
        url,
        timeout=15
    )

    response.raise_for_status()

    story_ids = response.json()

    topics = []

    for story_id in story_ids[:limit]:

        story_url = (
            f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json"
        )

        try:

            story_response = requests.get(
                story_url,
                timeout=10
            )

            story_response.raise_for_status()

            story = story_response.json()

        except requests.RequestException:

            continue

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

    try:

        response = requests.get(
            url,
            params=params,
            timeout=45
        )

        response.raise_for_status()

    except requests.RequestException as error:

        print("arXiv request failed:", error)

        return []

    try:

        root = ET.fromstring(response.text)

    except ET.ParseError:

        print("Could not parse arXiv response.")

        return []

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

        if not title_element.text:
            continue

        title = " ".join(
            title_element.text.strip().split()
        )

        description = ""

        if (
            summary_element is not None
            and summary_element.text
        ):

            description = " ".join(
                summary_element.text.strip().split()
            )

        published_at = None

        if (
            published_element is not None
            and published_element.text
        ):

            published_at = published_element.text

        article_url = ""

        if (
            link_element is not None
            and link_element.text
        ):

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