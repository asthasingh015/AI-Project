"""Opinion engine module for Cortex AI.

This module defines the OpinionEngine class, responsible for analyzing
discovered AI and technology topics, deciding whether they deserve
publishing, generating editorial opinions (rather than plain summaries),
and rejecting weak, repetitive, or low-value topics. The engine maintains
a consistent editorial philosophy aligned with the loaded PersonaEngine.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Set

from brain.persona import PersonaEngine, WritingGuideline

logger = logging.getLogger(__name__)


# Categories that are always rejected regardless of persona interests.
BLOCKED_CATEGORIES: Set[str] = {
    "clickbait",
    "celebrity",
    "celebrity gossip",
    "gossip",
    "politics",
    "political",
    "religion",
    "religious",
    "sports",
    "sport",
}

# Lightweight keyword hints used to detect blocked categories in free text.
BLOCKED_KEYWORDS: Dict[str, List[str]] = {
    "clickbait": ["you won't believe", "shocking", "goes viral", "gone wrong"],
    "celebrity": ["celebrity", "actor", "actress", "singer", "kardashian"],
    "politics": ["election", "senator", "president", "congress", "parliament"],
    "religion": ["religion", "religious", "church", "temple", "mosque"],
    "sports": ["football", "cricket", "basketball", "olympics", "soccer"],
}


@dataclass
class TopicScore:
    """Represents the multi-criteria scoring breakdown for a topic.

    Attributes:
        ai_relevance: Score for how relevant the topic is to AI (0-1).
        technical_depth: Score for technical depth of the topic (0-1).
        industry_impact: Score for potential industry impact (0-1).
        educational_value: Score for educational value (0-1).
        innovation: Score for how innovative the topic is (0-1).
        originality: Score for originality of the topic (0-1).
        duplicate_risk: Estimated risk that the topic is a duplicate
            of previously covered content (0-1, higher means riskier).
    """

    ai_relevance: float = 0.0
    technical_depth: float = 0.0
    industry_impact: float = 0.0
    educational_value: float = 0.0
    innovation: float = 0.0
    originality: float = 0.0
    duplicate_risk: float = 0.0

    def to_dict(self) -> Dict[str, float]:
        """Converts the score breakdown to a dictionary.

        Returns:
            A dictionary representation of the score breakdown.
        """
        return asdict(self)

    def aggregate(self) -> float:
        """Computes a weighted aggregate confidence score.

        Returns:
            A float between 0 and 1 representing overall topic quality,
            penalized by duplicate risk.
        """
        weights = {
            "ai_relevance": 0.25,
            "technical_depth": 0.20,
            "industry_impact": 0.15,
            "educational_value": 0.15,
            "innovation": 0.15,
            "originality": 0.10,
        }
        base_score = sum(
            getattr(self, key) * weight for key, weight in weights.items()
        )
        penalty = self.duplicate_risk * 0.5
        final_score = max(0.0, min(1.0, base_score - penalty))
        return round(final_score, 4)


@dataclass
class OpinionResult:
    """Represents the final output of the OpinionEngine analysis.

    Attributes:
        topic: The original topic string that was analyzed.
        publish: Whether the topic is approved for publishing.
        confidence: The aggregate confidence score (0-1).
        reason: A human-readable explanation of the decision.
        editorial_opinion: The generated editorial opinion text, present
            only when `publish` is True.
        score_breakdown: The detailed per-criterion score breakdown.
    """

    topic: str
    publish: bool
    confidence: float
    reason: str
    editorial_opinion: Optional[str] = None
    score_breakdown: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Converts the opinion result to a dictionary.

        Returns:
            A dictionary representation of the opinion result.
        """
        return asdict(self)


class OpinionEngine:
    """Engine responsible for editorial analysis of discovered topics.

    The OpinionEngine consumes topics (typically from a Discovery module),
    evaluates them against a fixed set of editorial criteria, filters out
    low-value or disallowed categories, and produces either a rejection
    with reasoning or an accepted publishing decision accompanied by a
    generated editorial opinion and confidence score.

    Attributes:
        _persona_engine: The PersonaEngine used to align editorial voice
            and relevance checks with the persona's domain.
        _seen_topics: A set of normalized topic fingerprints used for
            lightweight duplicate/novelty detection.
        _min_confidence: The minimum aggregate score required to accept
            a topic for publishing.
        _extensions: Reserved dictionary for future extension hooks
            (e.g., Memory module integration).
    """

    def __init__(
        self,
        persona_engine: PersonaEngine,
        min_confidence: float = 0.55,
    ) -> None:
        """Initializes the OpinionEngine.

        Args:
            persona_engine: A loaded PersonaEngine instance used to align
                editorial decisions with the active persona.
            min_confidence: The minimum confidence score required for a
                topic to be approved for publishing. Defaults to 0.55.

        Raises:
            TypeError: If `persona_engine` is not a PersonaEngine
                instance.
            ValueError: If `min_confidence` is not within [0, 1].
        """
        if not isinstance(persona_engine, PersonaEngine):
            raise TypeError(
                "persona_engine must be an instance of PersonaEngine, "
                f"got {type(persona_engine).__name__}"
            )
        if not 0.0 <= min_confidence <= 1.0:
            raise ValueError("min_confidence must be between 0 and 1")

        self._persona_engine = persona_engine
        self._min_confidence = min_confidence
        self._seen_topics: Set[str] = set()
        self._extensions: Dict[str, Any] = {}

        logger.info(
            "OpinionEngine initialized with min_confidence=%.2f",
            min_confidence,
        )

    def _normalize(self, text: str) -> str:
        """Normalizes text for comparison purposes.

        Args:
            text: The raw text to normalize.

        Returns:
            A lowercased, whitespace-collapsed, punctuation-stripped
            version of the input text.
        """
        cleaned = re.sub(r"[^a-z0-9\s]", "", text.lower())
        return re.sub(r"\s+", " ", cleaned).strip()

    def _detect_blocked_category(self, topic: str) -> Optional[str]:
        """Detects whether a topic falls into a permanently blocked category.

        Args:
            topic: The topic string to inspect.

        Returns:
            The name of the blocked category if detected, otherwise None.
        """
        normalized = self._normalize(topic)

        for category in BLOCKED_CATEGORIES:
            if category in normalized:
                return category

        for category, keywords in BLOCKED_KEYWORDS.items():
            for keyword in keywords:
                if keyword in normalized:
                    return category

        return None

    def evaluate_relevance(self, topic: str) -> float:
        """Evaluates how relevant a topic is to AI/technology and persona.

        Args:
            topic: The topic string to evaluate.

        Returns:
            A relevance score between 0 and 1.
        """
        normalized = self._normalize(topic)
        ai_keywords = [
            "ai", "artificial intelligence", "machine learning", "ml",
            "llm", "neural network", "deep learning", "genai",
            "generative ai", "transformer", "model", "algorithm",
            "automation", "robotics", "data science", "chatbot",
            "agent", "computer vision", "nlp",
        ]

        keyword_hits = sum(1 for kw in ai_keywords if kw in normalized)
        keyword_score = min(1.0, keyword_hits * 0.25)

        try:
            persona_relevant = self._persona_engine.is_topic_relevant(topic)
        except (RuntimeError, ValueError):
            persona_relevant = False

        persona_score = 1.0 if persona_relevant else 0.3

        return round((keyword_score * 0.6) + (persona_score * 0.4), 4)

    def evaluate_novelty(self, topic: str) -> float:
        """Evaluates how novel a topic is relative to previously seen topics.

        Args:
            topic: The topic string to evaluate.

        Returns:
            A novelty score between 0 and 1, where 1 means highly novel
            and 0 means an exact duplicate of a previously seen topic.
        """
        normalized = self._normalize(topic)

        if normalized in self._seen_topics:
            return 0.0

        topic_words = set(normalized.split())
        max_similarity = 0.0
        for seen in self._seen_topics:
            seen_words = set(seen.split())
            if not topic_words or not seen_words:
                continue
            overlap = len(topic_words & seen_words)
            union = len(topic_words | seen_words)
            similarity = overlap / union if union else 0.0
            max_similarity = max(max_similarity, similarity)

        return round(1.0 - max_similarity, 4)

    def score_topic(
        self, topic: str, metadata: Optional[Dict[str, Any]] = None
    ) -> TopicScore:
        """Computes a full multi-criteria score breakdown for a topic.

        Args:
            topic: The topic string to score.
            metadata: Optional additional metadata (e.g., source signals,
                engagement stats) that may refine scoring in the future.

        Returns:
            A TopicScore instance containing all evaluated criteria.
        """
        metadata = metadata or {}
        normalized = self._normalize(topic)

        relevance = self.evaluate_relevance(topic)
        novelty = self.evaluate_novelty(topic)
        duplicate_risk = round(1.0 - novelty, 4)

        technical_terms = [
            "architecture", "framework", "algorithm", "training",
            "inference", "benchmark", "dataset", "parameters",
            "fine-tuning", "optimization", "protocol", "api", "research",
            "paper", "open source", "performance", "scalability",
        ]
        technical_hits = sum(1 for t in technical_terms if t in normalized)
        technical_depth = min(1.0, technical_hits * 0.2 + 0.1)

        impact_terms = [
            "industry", "enterprise", "adoption", "market", "startup",
            "funding", "regulation", "policy", "workforce", "economy",
            "launch", "release", "acquisition", "partnership",
        ]
        impact_hits = sum(1 for t in impact_terms if t in normalized)
        industry_impact = min(1.0, impact_hits * 0.2 + 0.15)

        educational_terms = [
            "how", "guide", "explained", "tutorial", "introduction",
            "understanding", "deep dive", "explainer", "breakdown",
        ]
        educational_hits = sum(1 for t in educational_terms if t in normalized)
        educational_value = min(1.0, educational_hits * 0.25 + 0.2)

        innovation_terms = [
            "new", "breakthrough", "novel", "first", "next-generation",
            "state-of-the-art", "sota", "cutting-edge", "innovative",
        ]
        innovation_hits = sum(1 for t in innovation_terms if t in normalized)
        innovation = min(1.0, innovation_hits * 0.25 + 0.1)

        originality = novelty

        score = TopicScore(
            ai_relevance=relevance,
            technical_depth=round(technical_depth, 4),
            industry_impact=round(industry_impact, 4),
            educational_value=round(educational_value, 4),
            innovation=round(innovation, 4),
            originality=round(originality, 4),
            duplicate_risk=duplicate_risk,
        )
        return score

    def generate_editorial_opinion(
        self, topic: str, score: TopicScore
    ) -> str:
        """Generates an editorial opinion for an accepted topic.

        Produces an opinionated editorial perspective rather than a plain
        summary, aligned with the persona's tone and writing style.

        Args:
            topic: The topic to generate an opinion about.
            score: The TopicScore breakdown used to shape the angle of
                the opinion.

        Returns:
            A string containing the generated editorial opinion.
        """
        try:
            guideline: WritingGuideline = (
                self._persona_engine.get_writing_instruction(topic)
            )
            tone = guideline.tone
        except (RuntimeError, ValueError):
            tone = "analytical"

        if score.innovation >= 0.6:
            angle = (
                "This signals a meaningful shift rather than incremental "
                "progress, and deserves scrutiny beyond the headline."
            )
        elif score.industry_impact >= 0.6:
            angle = (
                "The real story here is not the technology itself but "
                "what it means for the industry adopting it."
            )
        elif score.technical_depth >= 0.6:
            angle = (
                "Beneath the surface-level announcement lies a technical "
                "decision worth unpacking for practitioners."
            )
        else:
            angle = (
                "While not groundbreaking, this development is a useful "
                "data point in a fast-moving landscape."
            )

        opinion = (
            f"On '{topic}': {angle} In a {tone} voice, the position taken "
            "here is that readers should evaluate this development on its "
            "practical merits and long-term implications, not on hype "
            "alone. The value of covering this topic lies in connecting "
            "it to the broader trajectory of AI and technology, offering "
            "perspective that a plain summary would miss."
        )
        return opinion

    def should_publish(self, score: TopicScore) -> bool:
        """Determines whether a topic's score qualifies it for publishing.

        Args:
            score: The TopicScore breakdown to evaluate.

        Returns:
            True if the aggregate confidence meets the minimum threshold,
            False otherwise.
        """
        return score.aggregate() >= self._min_confidence

    def get_publish_reason(
        self, topic: str, score: TopicScore, publish: bool
    ) -> str:
        """Builds a human-readable explanation for the publish decision.

        Args:
            topic: The topic being evaluated.
            score: The TopicScore breakdown for the topic.
            publish: Whether the topic was approved for publishing.

        Returns:
            A string explaining why the topic was accepted or rejected.
        """
        confidence = score.aggregate()

        if publish:
            strongest = max(
                score.to_dict().items(),
                key=lambda item: item[1] if item[0] != "duplicate_risk"
                else -1,
            )
            return (
                f"Accepted '{topic}' with confidence {confidence:.2f}. "
                f"Strongest signal: {strongest[0].replace('_', ' ')} "
                f"({strongest[1]:.2f}). Meets minimum threshold of "
                f"{self._min_confidence:.2f}."
            )

        if score.duplicate_risk >= 0.7:
            return (
                f"Rejected '{topic}': too similar to previously covered "
                f"content (duplicate risk {score.duplicate_risk:.2f})."
            )
        if score.ai_relevance < 0.3:
            return (
                f"Rejected '{topic}': insufficient AI/technology "
                f"relevance ({score.ai_relevance:.2f})."
            )
        return (
            f"Rejected '{topic}': aggregate confidence {confidence:.2f} "
            f"below minimum threshold of {self._min_confidence:.2f}."
        )

    def analyze_topic(
        self, topic: str, metadata: Optional[Dict[str, Any]] = None
    ) -> OpinionResult:
        """Performs full editorial analysis of a topic.

        This is the primary entry point of the OpinionEngine. It checks
        for blocked categories, scores the topic across all editorial
        criteria, decides whether to publish, and generates either an
        editorial opinion (if accepted) or a rejection reason.

        Args:
            topic: The topic string to analyze.
            metadata: Optional additional context about the topic, such
                as source information supplied by a Discovery module.

        Returns:
            An OpinionResult containing the full decision and reasoning.

        Raises:
            ValueError: If the topic string is empty.
        """
        if not topic or not topic.strip():
            raise ValueError("topic must be a non-empty string")

        blocked_category = self._detect_blocked_category(topic)
        if blocked_category:
            score = TopicScore()
            reason = (
                f"Rejected '{topic}': falls under disallowed category "
                f"'{blocked_category}'."
            )
            logger.info(reason)
            result = OpinionResult(
                topic=topic,
                publish=False,
                confidence=0.0,
                reason=reason,
                editorial_opinion=None,
                score_breakdown=score.to_dict(),
            )
            return result

        score = self.score_topic(topic, metadata)
        confidence = score.aggregate()
        publish = self.should_publish(score)
        reason = self.get_publish_reason(topic, score, publish)

        editorial_opinion: Optional[str] = None
        if publish:
            editorial_opinion = self.generate_editorial_opinion(topic, score)
            self._seen_topics.add(self._normalize(topic))

        logger.info(reason)

        return OpinionResult(
            topic=topic,
            publish=publish,
            confidence=confidence,
            reason=reason,
            editorial_opinion=editorial_opinion,
            score_breakdown=score.to_dict(),
        )

    def register_extension(self, key: str, value: Any) -> None:
        """Registers arbitrary extension data for future capabilities.

        This method exists to support future integration with Memory,
        Discovery, and Publisher modules without breaking the existing
        interface.

        Args:
            key: The identifier for the extension data.
            value: The extension data to store.
        """
        self._extensions[key] = value
        logger.debug("Extension '%s' registered on OpinionEngine.", key)

    def export(self) -> Dict[str, Any]:
        """Exports the engine's state for persistence or transfer.

        Returns:
            A dictionary containing the engine's configuration, seen
            topic fingerprints, and registered extensions.
        """
        return {
            "min_confidence": self._min_confidence,
            "seen_topics_count": len(self._seen_topics),
            "seen_topics": sorted(self._seen_topics),
            "extensions": dict(self._extensions),
        }

    def __repr__(self) -> str:
        """Returns a developer-friendly representation of the engine.

        Returns:
            A string representation of the OpinionEngine instance.
        """
        return (
            f"OpinionEngine(min_confidence={self._min_confidence!r}, "
            f"seen_topics={len(self._seen_topics)})"
        )