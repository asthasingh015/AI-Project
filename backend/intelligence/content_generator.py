from typing import Dict
import json
import ollama


def generate_article(topic) -> Dict:

    title = topic.title

    prompt = f"""
Create an informative article about this topic:

Topic: {title}

Return ONLY valid JSON in this exact format:

{{
    "summary": "Write a short 2-3 sentence summary.",
    "key_points": [
        "Point 1",
        "Point 2",
        "Point 3",
        "Point 4"
    ]
}}

Keep the content factual, clear and easy to understand.
"""

    response = ollama.chat(
        model="llama3.2",
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ]
    )

    content = response["message"]["content"]

    try:
        generated = json.loads(content)
    except json.JSONDecodeError:
        generated = {
            "summary": content,
            "key_points": []
        }

    article = {
        "title": title,
        "summary": generated["summary"],
        "key_points": generated["key_points"],
        "source": topic.source,
        "source_url": topic.url,
        "category": topic.category
    }

    return article