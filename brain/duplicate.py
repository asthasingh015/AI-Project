"""Duplicate detection module for Cortex AI.

This module defines the DuplicateDetector class, responsible for
detecting duplicate or near-duplicate topics before publishing. It
compares newly discovered topics against previously published posts
stored in the MemoryEngine, using text normalization and keyword-based
similarity, while remaining extensible for future semantic (embedding
based) similarity integration.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from brain.memory import MemoryEngine, PublishedPost

logger = logging.getLogger(__name__)


@dataclass
class DuplicateCheckResult:
    """Represents the outcome of a duplicate detection check.

    Attributes:
        topic: The topic string that was checked.
        is_duplicate: Whether the topic is considered a duplicate.
        similarity_score: The highest similarity score found (0-1).
        matched_post_id: The post_id of the most similar published post,
            or None if no meaningful match was found.
        matched_topic: The topic string of the most similar published
            post, or None if no meaningful match was found.
        reason: A human-readable explanation of the decision.
    """

    topic: str
    is_duplicate: bool
    similarity_score: float
    matched_post_id: Optional[str]
    matched_topic: Optional[str]
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        """Converts the duplicate check result to a dictionary.

        Returns:
            A dictionary representation of the duplicate check result.
        """
        return asdict(self)


class DuplicateDetector:
    """Engine responsible for detecting duplicate or near-duplicate topics.

    The DuplicateDetector compares newly discovered topics against the
    publishing history maintained by a MemoryEngine instance. It uses
    text normalization and keyword-overlap based similarity (Jaccard
    similarity over normalized word sets) to compute a similarity score,
    and flags topics as duplicates when that score crosses a configurable
    threshold. The class is structured so a future semantic similarity
    backend (e.g., sentence embeddings) can be integrated without
    changing the public interface.

    Attributes:
        _memory_engine: The MemoryEngine instance used as the source of
            previously published posts.
        _duplicate_threshold: The similarity score above which a topic
            is considered a duplicate.
        _near_duplicate_threshold: The similarity score above which a
            topic is flagged as similar but not necessarily rejected.
        _extensions: Reserved dictionary for future extension hooks
            (e.g., embedding models, vector stores).
    """

    def __init__(
        self,
        memory_engine: "MemoryEngine",
        duplicate_threshold: float = 0.75,
        near_duplicate_threshold: float = 0.5,
    ) -> None:
        """Initializes the DuplicateDetector.

        Args:
            memory_engine: A MemoryEngine instance providing access to
                previously published posts.
            duplicate_threshold: The similarity score at or above which
                a topic is considered a duplicate. Defaults to 0.75.
            near_duplicate_threshold: The similarity score at or above
                which a topic is considered similar (used by
                `find_similar_posts`). Defaults to 0.5.

        Raises:
            ValueError: If either threshold is not within [0, 1], or if
                `near_duplicate_threshold` exceeds `duplicate_threshold`.
        """
        if not 0.0 <= duplicate_threshold <= 1.0:
            raise ValueError("duplicate_threshold must be between 0 and 1")
        if not 0.0 <= near_duplicate_threshold <= 1.0:
            raise ValueError(
                "near_duplicate_threshold must be between 0 and 1"
            )
        if near_duplicate_threshold > duplicate_threshold:
            raise ValueError(
                "near_duplicate_threshold cannot exceed duplicate_threshold"
            )

        self._memory_engine = memory_engine
        self._duplicate_threshold = duplicate_threshold
        self._near_duplicate_threshold = near_duplicate_threshold
        self._extensions: Dict[str, Any] = {}

        logger.info(
            "DuplicateDetector initialized with duplicate_threshold=%.2f, "
            "near_duplicate_threshold=%.2f",
            duplicate_threshold,
            near_duplicate_threshold,
        )

    def normalize_text(self, text: str) -> str:
        """Normalizes text for comparison purposes.

        Strips punctuation, collapses whitespace, and lowercases the
        input to ensure comparisons are case- and formatting-insensitive.

        Args:
            text: The raw text to normalize.

        Returns:
            A normalized version of the input text.

        Raises:
            ValueError: If `text` is empty.
        """
        if not text or not text.strip():
            raise ValueError("text must be a non-empty string")

        cleaned = re.sub(r"[^a-z0-9\s]", "", text.lower())
        return re.sub(r"\s+", " ", cleaned).strip()

    def calculate_similarity(self, text_a: str, text_b: str) -> float:
        """Calculates a similarity score between two text strings.

        Uses Jaccard similarity over normalized word sets as the default
        keyword-based comparison strategy. This method is the designated
        extension point for future semantic similarity (e.g., embedding
        cosine similarity) integration.

        Args:
            text_a: The first text string.
            text_b: The second text string.

        Returns:
            A similarity score between 0 and 1, where 1 means identical
            normalized content and 0 means no overlap.
        """
        normalized_a = self.normalize_text(text_a)
        normalized_b = self.normalize_text(text_b)

        if normalized_a == normalized_b:
            return 1.0

        words_a = set(normalized_a.split())
        words_b = set(normalized_b.split())

        if not words_a or not words_b:
            return 0.0

        intersection = words_a & words_b
        union = words_a | words_b

        jaccard_score = len(intersection) / len(union) if union else 0.0

        substring_bonus = 0.0
        if normalized_a in normalized_b or normalized_b in normalized_a:
            substring_bonus = 0.2

        final_score = min(1.0, jaccard_score + substring_bonus)
        return round(final_score, 4)

    def compare_topics(
        self, topic_a: str, topic_b: str
    ) -> Dict[str, Any]:
        """Compares two topics and returns a detailed comparison result.

        Args:
            topic_a: The first topic string.
            topic_b: The second topic string.

        Returns:
            A dictionary containing both original topics, their
            normalized forms, and the computed similarity score.
        """
        similarity_score = self.calculate_similarity(topic_a, topic_b)

        return {
            "topic_a": topic_a,
            "topic_b": topic_b,
            "normalized_a": self.normalize_text(topic_a),
            "normalized_b": self.normalize_text(topic_b),
            "similarity_score": similarity_score,
        }

    def _best_match(
        self, topic: str
    ) -> tuple[Optional["PublishedPost"], float]:
        """Finds the most similar previously published post for a topic.

        Args:
            topic: The topic string to compare against publishing
                history.

        Returns:
            A tuple of (best_matching_post, similarity_score). If no
            posts exist in memory, returns (None, 0.0).
        """
        best_post: Optional["PublishedPost"] = None
        best_score = 0.0

        for post in self._memory_engine.get_all_posts():
            score = self.calculate_similarity(topic, post.topic)
            if score > best_score:
                best_score = score
                best_post = post

        return best_post, best_score

    def is_duplicate(self, topic: str) -> bool:
        """Checks whether a topic is a duplicate of a previously published post.

        Args:
            topic: The topic string to check.

        Returns:
            True if the topic's highest similarity score against
            publishing history meets or exceeds the duplicate threshold,
            False otherwise.

        Raises:
            ValueError: If `topic` is empty.
        """
        if not topic or not topic.strip():
            raise ValueError("topic must be a non-empty string")

        _, score = self._best_match(topic)
        return score >= self._duplicate_threshold

    def get_duplicate_reason(
        self, topic: str, matched_post: Optional["PublishedPost"], score: float
    ) -> str:
        """Builds a human-readable explanation for the duplicate decision.

        Args:
            topic: The topic being checked.
            matched_post: The most similar published post found, or None
                if no posts exist in memory.
            score: The similarity score computed against `matched_post`.

        Returns:
            A string explaining why the topic was or was not flagged as
            a duplicate.
        """
        if matched_post is None:
            return (
                f"'{topic}' is not a duplicate: no previously published "
                "posts exist for comparison."
            )

        if score >= self._duplicate_threshold:
            return (
                f"'{topic}' is a duplicate of post '{matched_post.post_id}' "
                f"('{matched_post.topic}') with similarity score "
                f"{score:.2f}, meeting the duplicate threshold of "
                f"{self._duplicate_threshold:.2f}."
            )

        if score >= self._near_duplicate_threshold:
            return (
                f"'{topic}' is not a duplicate but is similar to post "
                f"'{matched_post.post_id}' ('{matched_post.topic}') with "
                f"score {score:.2f}, below the duplicate threshold of "
                f"{self._duplicate_threshold:.2f}."
            )

        return (
            f"'{topic}' is not a duplicate: highest similarity score "
            f"{score:.2f} against post '{matched_post.post_id}' is below "
            f"the near-duplicate threshold of "
            f"{self._near_duplicate_threshold:.2f}."
        )

    def find_similar_posts(
        self, topic: str, limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Finds previously published posts similar to a given topic.

        Args:
            topic: The topic string to compare against publishing
                history.
            limit: The maximum number of similar posts to return.
                Defaults to 5.

        Returns:
            A list of dictionaries, each containing `post_id`, `topic`,
            and `similarity_score`, sorted by descending similarity and
            filtered to the near-duplicate threshold or above.

        Raises:
            ValueError: If `topic` is empty or `limit` is not positive.
        """
        if not topic or not topic.strip():
            raise ValueError("topic must be a non-empty string")
        if limit <= 0:
            raise ValueError("limit must be a positive integer")

        results: List[Dict[str, Any]] = []

        for post in self._memory_engine.get_all_posts():
            score = self.calculate_similarity(topic, post.topic)
            if score >= self._near_duplicate_threshold:
                results.append(
                    {
                        "post_id": post.post_id,
                        "topic": post.topic,
                        "similarity_score": score,
                    }
                )

        results.sort(key=lambda item: item["similarity_score"], reverse=True)
        return results[:limit]

    def check(self, topic: str) -> DuplicateCheckResult:
        """Performs a full duplicate check for a topic.

        This is the primary entry point of the DuplicateDetector. It
        finds the closest matching previously published post, computes
        the similarity score, determines duplicate status, and builds a
        structured result with reasoning.

        Args:
            topic: The topic string to check.

        Returns:
            A DuplicateCheckResult containing the full decision and
            reasoning.

        Raises:
            ValueError: If `topic` is empty.
        """
        if not topic or not topic.strip():
            raise ValueError("topic must be a non-empty string")

        matched_post, score = self._best_match(topic)
        duplicate = score >= self._duplicate_threshold
        reason = self.get_duplicate_reason(topic, matched_post, score)

        logger.info(reason)

        return DuplicateCheckResult(
            topic=topic,
            is_duplicate=duplicate,
            similarity_score=score,
            matched_post_id=matched_post.post_id if matched_post else None,
            matched_topic=matched_post.topic if matched_post else None,
            reason=reason,
        )

    def register_extension(self, key: str, value: Any) -> None:
        """Registers arbitrary extension data for future capabilities.

        This method exists to support future integration with semantic
        similarity backends (e.g., embedding models, vector databases)
        and other modules (Discovery, OpinionEngine, Publisher) without
        breaking the existing interface.

        Args:
            key: The identifier for the extension data.
            value: The extension data to store.
        """
        self._extensions[key] = value
        logger.debug(
            "Extension '%s' registered on DuplicateDetector.", key
        )

    def export(self) -> Dict[str, Any]:
        """Exports the detector's configuration and state.

        Returns:
            A dictionary containing the configured thresholds and
            registered extensions, suitable for serialization or
            diagnostics.
        """
        return {
            "duplicate_threshold": self._duplicate_threshold,
            "near_duplicate_threshold": self._near_duplicate_threshold,
            "tracked_posts": len(self._memory_engine.get_all_posts()),
            "extensions": dict(self._extensions),
        }

    def __repr__(self) -> str:
        """Returns a developer-friendly representation of the detector.

        Returns:
            A string representation of the DuplicateDetector instance.
        """
        return (
            f"DuplicateDetector(duplicate_threshold="
            f"{self._duplicate_threshold!r}, "
            f"near_duplicate_threshold={self._near_duplicate_threshold!r})"
        )