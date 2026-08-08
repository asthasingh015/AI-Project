import json
import os

from .discovery import normalize_title


MEMORY_FILE = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "data",
    "topic_memory.json"
)


def load_memory():

    if not os.path.exists(MEMORY_FILE):
        return []

    with open(
        MEMORY_FILE,
        "r",
        encoding="utf-8"
    ) as file:

        return json.load(file)


def save_memory(memory):

    os.makedirs(
        os.path.dirname(MEMORY_FILE),
        exist_ok=True
    )

    with open(
        MEMORY_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            memory,
            file,
            indent=4,
            ensure_ascii=False
        )


def is_duplicate_topic(title):

    memory = load_memory()

    current_words = normalize_title(title)

    for old_topic in memory:

        old_words = normalize_title(
            old_topic["title"]
        )

        common_words = current_words.intersection(
            old_words
        )

        if len(common_words) >= 3:
            return True

    return False


def remember_topic(title, source):

    memory = load_memory()

    memory.append({
        "title": title,
        "source": source
    })

    save_memory(memory)