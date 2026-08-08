from typing import Dict


def generate_article(topic) -> Dict:

    title = topic.title

    article = {
        "title": title,

        "summary": (
            f"This article explores the latest developments related to "
            f"{title}."
        ),

        "key_points": [
            f"What is {title}",
            "Why this topic is important",
            "Potential impact on AI and technology",
            "What could happen next"
        ],

        "source": topic.source,

        "source_url": topic.url,

        "category": topic.category
    }

    return article