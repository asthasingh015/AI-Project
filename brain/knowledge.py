"""Knowledge engine module for Cortex AI.

This module defines the KnowledgeEngine class, responsible for
maintaining the AI's technology knowledge domains, classifying discovered
topics into knowledge areas, scoring topic relevance, and rejecting
topics that fall outside the system's expertise. The engine is designed
to work alongside the PersonaEngine and OpinionEngine to keep editorial
decisions grounded in a well-defined domain of competence.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


# Default knowledge domains with associated keyword fingerprints used for
# lightweight topic classification.
DEFAULT_DOMAINS: Dict[str, List[str]] = {
    "Artificial Intelligence": [
        "artificial intelligence", "ai", "intelligent system",
    ],
    "Machine Learning": [
        "machine learning", "ml", "supervised learning",
        "unsupervised learning", "reinforcement learning", "regression",
        "classification model",
    ],
    "Deep Learning": [
        "deep learning", "neural network", "cnn", "rnn", "gan",
        "backpropagation", "gradient descent",
    ],
    "Generative AI": [
        "generative ai", "genai", "diffusion model", "text-to-image",
        "image generation", "generative model",
    ],
    "Large Language Models": [
        "large language model", "llm", "gpt", "transformer", "chatgpt",
        "claude", "gemini", "language model", "tokenization",
        "fine-tuning",
    ],
    "AI Agents": [
        "ai agent", "autonomous agent", "multi-agent", "agentic",
        "agent framework", "tool use", "orchestration",
    ],
    "Prompt Engineering": [
        "prompt engineering", "prompt design", "prompt tuning",
        "few-shot", "chain of thought", "system prompt",
    ],
    "Robotics": [
        "robotics", "robot", "autonomous vehicle", "humanoid",
        "robotic arm", "drone",
    ],
    "Computer Vision": [
        "computer vision", "image recognition", "object detection",
        "facial recognition", "image segmentation", "opencv",
    ],
    "NLP": [
        "nlp", "natural language processing", "text classification",
        "sentiment analysis", "named entity recognition", "tokenizer",
    ],
    "MLOps": [
        "mlops", "model deployment", "model monitoring", "ci/cd",
        "pipeline orchestration", "model registry", "kubeflow",
    ],
    "Open Source AI": [
        "open source ai", "open-source model", "huggingface",
        "open weights", "github ai project",
    ],
    "AI Security": [
        "ai security", "adversarial attack", "prompt injection",
        "model poisoning", "jailbreak", "ai vulnerability",
    ],
    "AI Ethics": [
        "ai ethics", "responsible ai", "ai bias", "fairness",
        "ai governance", "ai regulation",
    ],
    "Cloud AI": [
        "cloud ai", "aws ai", "azure ai", "google cloud ai",
        "ai infrastructure", "gpu cluster", "cloud computing",
    ],
    "Python Development": [
        "python", "django", "flask", "fastapi", "pandas", "numpy",
        "pytorch", "tensorflow",
    ],
}

# Topics that are permanently unsupported regardless of keyword overlap.
UNSUPPORTED_TOPICS: Dict[str, List[str]] = {
    "Politics": [
        "politics", "election", "senator", "president", "congress",
        "parliament", "government policy",
    ],
    "Religion": [
        "religion", "religious", "church", "temple", "mosque",
        "spirituality",
    ],
    "Celebrity News": [
        "celebrity", "actor", "actress", "singer", "kardashian",
        "hollywood gossip",
    ],
    "Sports": [
        "football", "cricket", "basketball", "olympics", "soccer",
        "tennis", "sports match",
    ],
    "Entertainment Gossip": [
        "gossip", "reality tv", "scandal", "tabloid", "viral drama",
    ],
}


@dataclass
class ClassificationResult:
    """Represents the result of classifying a topic against the knowledge base.

    Attributes:
        topic: The original topic string that was classified.
        category: The best-matching knowledge domain, or None if no
            domain matched or the topic is unsupported.
        relevance_score: A relevance score between 0 and 1.
        supported: Whether the topic is supported by the knowledge base.
        reason: A human-readable explanation of the classification
            decision.
    """

    topic: str
    category: Optional[str]
    relevance_score: float
    supported: bool
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        """Converts the classification result to a dictionary.

        Returns:
            A dictionary representation of the classification result.
        """
        return asdict(self)


class KnowledgeEngine:
    """Engine responsible for maintaining Cortex AI's domain expertise.

    The KnowledgeEngine holds a registry of knowledge domains (each with
    associated keyword fingerprints) that define the system's area of
    expertise. It classifies discovered topics into the best-matching
    domain, computes a relevance score, and rejects topics that fall
    into permanently unsupported categories or that fail to match any
    known domain with sufficient confidence.

    The engine is intended to be used alongside the PersonaEngine (for
    voice/interest alignment) and the OpinionEngine (for editorial
    scoring), acting as the authoritative gatekeeper for whether a topic
    falls within Cortex AI's technical competence.

    Attributes:
        _domains: A mapping of domain name to a set of normalized
            keyword fingerprints used for classification.
        _unsupported: A mapping of unsupported category name to a set of
            normalized keyword fingerprints used for rejection.
        _min_relevance: The minimum relevance score required for a topic
            to be considered supported.
        _extensions: Reserved dictionary for future extension hooks
            (e.g., embedding-based classification, external ontologies).
    """

    def __init__(
        self,
        domains: Optional[Dict[str, List[str]]] = None,
        unsupported_topics: Optional[Dict[str, List[str]]] = None,
        min_relevance: float = 0.25,
    ) -> None:
        """Initializes the KnowledgeEngine.

        Args:
            domains: An optional custom mapping of domain name to a list
                of keyword fingerprints. Defaults to DEFAULT_DOMAINS if
                not provided.
            unsupported_topics: An optional custom mapping of unsupported
                category name to a list of keyword fingerprints. Defaults
                to UNSUPPORTED_TOPICS if not provided.
            min_relevance: The minimum relevance score required for a
                topic to be considered supported. Defaults to 0.25.

        Raises:
            ValueError: If `min_relevance` is not within [0, 1].
        """
        if not 0.0 <= min_relevance <= 1.0:
            raise ValueError("min_relevance must be between 0 and 1")

        self._domains: Dict[str, Set[str]] = {}
        self._unsupported: Dict[str, Set[str]] = {}
        self._min_relevance = min_relevance
        self._extensions: Dict[str, Any] = {}

        self.load_domains(domains or DEFAULT_DOMAINS)
        self._load_unsupported(unsupported_topics or UNSUPPORTED_TOPICS)

        logger.info(
            "KnowledgeEngine initialized with %d domains and %d "
            "unsupported categories.",
            len(self._domains),
            len(self._unsupported),
        )

    def _normalize(self, text: str) -> str:
        """Normalizes text for keyword comparison.

        Args:
            text: The raw text to normalize.

        Returns:
            A lowercased, whitespace-collapsed, punctuation-stripped
            version of the input text.
        """
        cleaned = re.sub(r"[^a-z0-9\s]", "", text.lower())
        return re.sub(r"\s+", " ", cleaned).strip()

    def load_domains(self, domains: Dict[str, List[str]]) -> None:
        """Loads (or reloads) the full set of knowledge domains.

        Args:
            domains: A mapping of domain name to a list of keyword
                fingerprints.

        Raises:
            ValueError: If `domains` is empty.
        """
        if not domains:
            raise ValueError("domains mapping must not be empty")

        self._domains = {
            name: {self._normalize(kw) for kw in keywords}
            for name, keywords in domains.items()
        }
        logger.info("Loaded %d knowledge domains.", len(self._domains))

    def _load_unsupported(self, unsupported: Dict[str, List[str]]) -> None:
        """Loads the set of permanently unsupported topic categories.

        Args:
            unsupported: A mapping of unsupported category name to a
                list of keyword fingerprints.
        """
        self._unsupported = {
            name: {self._normalize(kw) for kw in keywords}
            for name, keywords in unsupported.items()
        }

    def add_domain(self, name: str, keywords: List[str]) -> None:
        """Adds a new knowledge domain, supporting future learning.

        If the domain already exists, its keyword set is extended with
        the newly provided keywords rather than being overwritten.

        Args:
            name: The name of the knowledge domain.
            keywords: A list of keyword fingerprints associated with the
                domain.

        Raises:
            ValueError: If `name` is empty or `keywords` is empty.
        """
        if not name or not name.strip():
            raise ValueError("domain name must be a non-empty string")
        if not keywords:
            raise ValueError("keywords must be a non-empty list")

        normalized_keywords = {self._normalize(kw) for kw in keywords}

        if name in self._domains:
            self._domains[name].update(normalized_keywords)
            logger.info("Extended existing domain '%s'.", name)
        else:
            self._domains[name] = normalized_keywords
            logger.info("Added new knowledge domain '%s'.", name)

    def remove_domain(self, name: str) -> bool:
        """Removes a knowledge domain from the registry.

        Args:
            name: The name of the domain to remove.

        Returns:
            True if the domain existed and was removed, False otherwise.
        """
        if name in self._domains:
            del self._domains[name]
            logger.info("Removed knowledge domain '%s'.", name)
            return True
        return False

    def get_domains(self) -> List[str]:
        """Returns the list of currently registered knowledge domains.

        Returns:
            A list of domain names.
        """
        return sorted(self._domains.keys())

    def _detect_unsupported(self, topic: str) -> Optional[str]:
        """Detects whether a topic matches a permanently unsupported category.

        Args:
            topic: The topic string to inspect.

        Returns:
            The name of the unsupported category if matched, otherwise
            None.
        """
        normalized = self._normalize(topic)
        topic_words = set(normalized.split())

        for category, keywords in self._unsupported.items():
            for keyword in keywords:
                if keyword in normalized:
                    return category
                keyword_words = set(keyword.split())
                if keyword_words and keyword_words.issubset(topic_words):
                    return category
        return None

    def calculate_relevance(self, topic: str, category: str) -> float:
        """Calculates a relevance score for a topic against a domain.

        Args:
            topic: The topic string to evaluate.
            category: The knowledge domain name to score against.

        Returns:
            A relevance score between 0 and 1.

        Raises:
            KeyError: If `category` is not a registered domain.
        """
        if category not in self._domains:
            raise KeyError(f"Unknown knowledge domain: '{category}'")

        normalized_topic = self._normalize(topic)
        topic_words = set(normalized_topic.split())
        keywords = self._domains[category]

        if not keywords or not topic_words:
            return 0.0

        hits = 0
        for keyword in keywords:
            if keyword in normalized_topic:
                hits += 1
            else:
                keyword_words = set(keyword.split())
                if keyword_words & topic_words:
                    hits += 0.5

        raw_score = hits / max(1, len(keywords) ** 0.5)
        return round(min(1.0, raw_score), 4)

    def get_best_category(
        self, topic: str
    ) -> tuple[Optional[str], float]:
        """Finds the best-matching knowledge domain for a topic.

        Args:
            topic: The topic string to classify.

        Returns:
            A tuple of (category, relevance_score). If no domain
            achieves a nonzero score, category is None and the score
            is 0.0.
        """
        best_category: Optional[str] = None
        best_score = 0.0

        for domain_name in self._domains:
            score = self.calculate_relevance(topic, domain_name)
            if score > best_score:
                best_score = score
                best_category = domain_name

        return best_category, best_score

    def is_supported_topic(self, topic: str) -> bool:
        """Checks whether a topic is supported by the knowledge base.

        Args:
            topic: The topic string to check.

        Returns:
            True if the topic is not in an unsupported category and
            achieves at least the minimum relevance score against some
            domain, False otherwise.

        Raises:
            ValueError: If `topic` is empty.
        """
        if not topic or not topic.strip():
            raise ValueError("topic must be a non-empty string")

        if self._detect_unsupported(topic):
            return False

        _, score = self.get_best_category(topic)
        return score >= self._min_relevance

    def classify_topic(self, topic: str) -> ClassificationResult:
        """Classifies a topic and produces a full evaluation result.

        This is the primary entry point of the KnowledgeEngine. It
        checks for unsupported categories first, then determines the
        best-matching knowledge domain and relevance score, and returns
        a structured result with the classification, support status,
        and reasoning.

        Args:
            topic: The topic string to classify.

        Returns:
            A ClassificationResult containing the category, relevance
            score, support status, and reasoning.

        Raises:
            ValueError: If `topic` is empty.
        """
        if not topic or not topic.strip():
            raise ValueError("topic must be a non-empty string")

        unsupported_category = self._detect_unsupported(topic)
        if unsupported_category:
            reason = (
                f"Rejected '{topic}': matches unsupported category "
                f"'{unsupported_category}', which is outside Cortex "
                "AI's knowledge domain."
            )
            logger.info(reason)
            return ClassificationResult(
                topic=topic,
                category=None,
                relevance_score=0.0,
                supported=False,
                reason=reason,
            )

        category, score = self.get_best_category(topic)

        if category is None or score < self._min_relevance:
            reason = (
                f"Rejected '{topic}': no knowledge domain matched with "
                f"sufficient relevance (best score {score:.2f}, minimum "
                f"required {self._min_relevance:.2f})."
            )
            logger.info(reason)
            return ClassificationResult(
                topic=topic,
                category=category,
                relevance_score=score,
                supported=False,
                reason=reason,
            )

        reason = (
            f"Accepted '{topic}': classified under '{category}' with "
            f"relevance score {score:.2f}, meeting the minimum "
            f"threshold of {self._min_relevance:.2f}."
        )
        logger.info(reason)
        return ClassificationResult(
            topic=topic,
            category=category,
            relevance_score=score,
            supported=True,
            reason=reason,
        )

    def register_extension(self, key: str, value: Any) -> None:
        """Registers arbitrary extension data for future capabilities.

        This method exists to support future integration with Discovery,
        Memory, and Publisher modules, as well as advanced classification
        strategies (e.g., embedding-based similarity), without breaking
        the existing interface.

        Args:
            key: The identifier for the extension data.
            value: The extension data to store.
        """
        self._extensions[key] = value
        logger.debug("Extension '%s' registered on KnowledgeEngine.", key)

    def export(self) -> Dict[str, Any]:
        """Exports the engine's full configuration and state.

        Returns:
            A dictionary containing the registered domains, unsupported
            categories, configuration, and extensions, suitable for
            serialization or migration to a future persistent store.
        """
        return {
            "domains": {
                name: sorted(keywords)
                for name, keywords in self._domains.items()
            },
            "unsupported_topics": {
                name: sorted(keywords)
                for name, keywords in self._unsupported.items()
            },
            "min_relevance": self._min_relevance,
            "extensions": dict(self._extensions),
        }

    def __repr__(self) -> str:
        """Returns a developer-friendly representation of the engine.

        Returns:
            A string representation of the KnowledgeEngine instance.
        """
        return (
            f"KnowledgeEngine(domains={len(self._domains)}, "
            f"min_relevance={self._min_relevance!r})"
        )