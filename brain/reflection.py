"""Reflection engine module for Cortex AI.

This module defines the ReflectionEngine class, responsible for
reviewing every publishing decision made by the system, analyzing why a
topic was accepted or rejected, evaluating post quality before
publishing, generating structured confidence reports, and suggesting
improvements for future posts. The engine works in concert with the
PersonaEngine, OpinionEngine, and MemoryEngine to track publishing
consistency over time.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from brain.persona import PersonaEngine
    from brain.opinion import OpinionEngine, TopicScore
    from brain.memory import MemoryEngine

logger = logging.getLogger(__name__)


@dataclass
class ReflectionReport:
    """Represents a structured reflection report for a publishing decision.

    Attributes:
        topic: The topic that was analyzed.
        publishing_decision: Either "published" or "rejected".
        quality_score: The overall quality score of the post (0-1).
        confidence_score: The overall confidence score in the decision
            (0-1).
        strengths: A list of identified strengths.
        weaknesses: A list of identified weaknesses.
        improvement_suggestions: A list of actionable suggestions for
            improving future posts.
        generated_at: ISO 8601 UTC timestamp of when the report was
            generated.
        details: Additional structured metadata (e.g., score
            breakdowns) useful for API consumers.
    """

    topic: str
    publishing_decision: str
    quality_score: float
    confidence_score: float
    strengths: List[str] = field(default_factory=list)
    weaknesses: List[str] = field(default_factory=list)
    improvement_suggestions: List[str] = field(default_factory=list)
    generated_at: str = ""
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Converts the reflection report to a dictionary.

        Returns:
            A dictionary representation of the reflection report,
            suitable for serialization through an API layer.
        """
        return asdict(self)


class ReflectionEngine:
    """Engine responsible for reviewing and reflecting on publishing decisions.

    The ReflectionEngine acts as a quality-assurance and self-review
    layer for Cortex AI. It inspects both accepted and rejected topics,
    scores the underlying post or decision across multiple quality
    dimensions, produces a confidence score, and generates a structured
    report containing strengths, weaknesses, and improvement suggestions.
    It also tracks publishing consistency across the history stored in
    the MemoryEngine.

    Attributes:
        _persona_engine: The PersonaEngine used to validate persona
            consistency in generated content.
        _opinion_engine: The OpinionEngine used to re-derive or align
            with editorial scoring.
        _memory_engine: The MemoryEngine used to retrieve publishing
            history for consistency tracking.
        _reports: A list of all generated ReflectionReport instances,
            most recent last.
        _extensions: Reserved dictionary for future extension hooks
            (e.g., Publisher/API integration, external QA tools).
    """

    def __init__(
        self,
        persona_engine: "PersonaEngine",
        opinion_engine: "OpinionEngine",
        memory_engine: "MemoryEngine",
    ) -> None:
        """Initializes the ReflectionEngine.

        Args:
            persona_engine: A loaded PersonaEngine instance.
            opinion_engine: An OpinionEngine instance used for editorial
                scoring context.
            memory_engine: A MemoryEngine instance used for publishing
                history and consistency tracking.
        """
        self._persona_engine = persona_engine
        self._opinion_engine = opinion_engine
        self._memory_engine = memory_engine
        self._reports: List[ReflectionReport] = []
        self._extensions: Dict[str, Any] = {}

        logger.info("ReflectionEngine initialized.")

    def _current_timestamp(self) -> str:
        """Generates the current UTC timestamp in ISO 8601 format.

        Returns:
            A string representing the current UTC time in ISO 8601
            format.
        """
        return datetime.now(timezone.utc).isoformat()

    def calculate_quality_score(
        self,
        score_breakdown: Dict[str, float],
        persona_consistency: float,
        source_credibility: float,
    ) -> float:
        """Calculates an overall quality score from multiple dimensions.

        Combines editorial score components (relevance, technical depth,
        originality, educational value, duplicate risk) with persona
        consistency and source credibility into a single weighted
        quality score.

        Args:
            score_breakdown: A dictionary containing at least
                'ai_relevance', 'technical_depth', 'originality',
                'educational_value', and 'duplicate_risk' keys, each
                valued between 0 and 1.
            persona_consistency: A score between 0 and 1 representing
                how well the content matches the persona's voice.
            source_credibility: A score between 0 and 1 representing the
                trustworthiness of the topic's source.

        Returns:
            A quality score between 0 and 1.
        """
        relevance = score_breakdown.get("ai_relevance", 0.0)
        technical_depth = score_breakdown.get("technical_depth", 0.0)
        originality = score_breakdown.get("originality", 0.0)
        educational_value = score_breakdown.get("educational_value", 0.0)
        duplicate_risk = score_breakdown.get("duplicate_risk", 0.0)

        weights = {
            "relevance": 0.20,
            "technical_depth": 0.15,
            "originality": 0.15,
            "editorial_quality": 0.15,
            "persona_consistency": 0.15,
            "educational_value": 0.10,
            "source_credibility": 0.10,
        }

        # Editorial quality is approximated as the mean of relevance,
        # technical depth, and originality, representing overall
        # editorial substance beyond a plain summary.
        editorial_quality = round(
            (relevance + technical_depth + originality) / 3, 4
        )

        weighted_score = (
            relevance * weights["relevance"]
            + technical_depth * weights["technical_depth"]
            + originality * weights["originality"]
            + editorial_quality * weights["editorial_quality"]
            + persona_consistency * weights["persona_consistency"]
            + educational_value * weights["educational_value"]
            + source_credibility * weights["source_credibility"]
        )

        penalty = duplicate_risk * 0.3
        final_score = max(0.0, min(1.0, weighted_score - penalty))
        return round(final_score, 4)

    def calculate_confidence(
        self, quality_score: float, opinion_confidence: float
    ) -> float:
        """Calculates the overall confidence in a publishing decision.

        Combines the computed quality score with the OpinionEngine's
        original confidence score to produce a single blended
        confidence value.

        Args:
            quality_score: The quality score computed for the post or
                topic (0-1).
            opinion_confidence: The confidence score originally assigned
                by the OpinionEngine (0-1).

        Returns:
            A blended confidence score between 0 and 1.
        """
        blended = (quality_score * 0.6) + (opinion_confidence * 0.4)
        return round(max(0.0, min(1.0, blended)), 4)

    def _evaluate_persona_consistency(
        self, editorial_opinion: Optional[str]
    ) -> float:
        """Estimates how consistent generated content is with the persona.

        Args:
            editorial_opinion: The generated editorial opinion text, or
                None if not available.

        Returns:
            A persona consistency score between 0 and 1.
        """
        if not editorial_opinion:
            return 0.5

        try:
            profile = self._persona_engine.get_profile()
        except RuntimeError:
            return 0.5

        signature_phrases = profile.get("signature_phrases", [])
        tone = (profile.get("tone") or "").lower()

        normalized_opinion = editorial_opinion.lower()
        score = 0.6

        if tone and tone in normalized_opinion:
            score += 0.15

        phrase_hits = sum(
            1
            for phrase in signature_phrases
            if phrase.lower() in normalized_opinion
        )
        score += min(0.25, phrase_hits * 0.1)

        return round(min(1.0, score), 4)

    def _evaluate_source_credibility(self, source: str) -> float:
        """Estimates source credibility based on a simple heuristic.

        Args:
            source: The source identifier or name associated with the
                topic.

        Returns:
            A source credibility score between 0 and 1.
        """
        if not source or not source.strip():
            return 0.4

        trusted_markers = [
            "arxiv", "official", "research", "paper", "docs",
            "documentation", "press release", "verified",
        ]
        normalized_source = source.lower()

        if any(marker in normalized_source for marker in trusted_markers):
            return 0.9

        return 0.65

    def analyze_post(
        self,
        topic: str,
        editorial_opinion: str,
        source: str,
        score_breakdown: Dict[str, float],
        opinion_confidence: float,
    ) -> ReflectionReport:
        """Analyzes an accepted (published or about-to-be-published) post.

        Args:
            topic: The topic of the post.
            editorial_opinion: The generated editorial opinion text.
            source: The origin source of the topic.
            score_breakdown: The OpinionEngine score breakdown dictionary
                for the topic (from TopicScore.to_dict()).
            opinion_confidence: The confidence score originally assigned
                by the OpinionEngine.

        Returns:
            A ReflectionReport summarizing the quality and confidence
            evaluation for the post.

        Raises:
            ValueError: If `topic` or `editorial_opinion` is empty.
        """
        if not topic or not topic.strip():
            raise ValueError("topic must be a non-empty string")
        if not editorial_opinion or not editorial_opinion.strip():
            raise ValueError("editorial_opinion must be a non-empty string")

        persona_consistency = self._evaluate_persona_consistency(
            editorial_opinion
        )
        source_credibility = self._evaluate_source_credibility(source)

        quality_score = self.calculate_quality_score(
            score_breakdown, persona_consistency, source_credibility
        )
        confidence_score = self.calculate_confidence(
            quality_score, opinion_confidence
        )

        strengths, weaknesses = self._identify_strengths_weaknesses(
            score_breakdown, persona_consistency, source_credibility
        )
        suggestions = self.suggest_improvements(weaknesses)

        report = ReflectionReport(
            topic=topic,
            publishing_decision="published",
            quality_score=quality_score,
            confidence_score=confidence_score,
            strengths=strengths,
            weaknesses=weaknesses,
            improvement_suggestions=suggestions,
            generated_at=self._current_timestamp(),
            details={
                "score_breakdown": dict(score_breakdown),
                "persona_consistency": persona_consistency,
                "source_credibility": source_credibility,
                "opinion_confidence": opinion_confidence,
            },
        )

        self._reports.append(report)
        logger.info(
            "Reflection generated for published topic '%s': quality=%.2f "
            "confidence=%.2f",
            topic,
            quality_score,
            confidence_score,
        )
        return report

    def analyze_rejection(
        self,
        topic: str,
        rejection_reason: str,
        score_breakdown: Optional[Dict[str, float]] = None,
        opinion_confidence: float = 0.0,
    ) -> ReflectionReport:
        """Analyzes a rejected topic and explains the rejection.

        Args:
            topic: The topic that was rejected.
            rejection_reason: The reason the topic was rejected.
            score_breakdown: An optional OpinionEngine score breakdown
                dictionary, if scoring was performed prior to rejection.
            opinion_confidence: The confidence score assigned by the
                OpinionEngine at rejection time, if any. Defaults to 0.0.

        Returns:
            A ReflectionReport summarizing the rejection analysis.

        Raises:
            ValueError: If `topic` or `rejection_reason` is empty.
        """
        if not topic or not topic.strip():
            raise ValueError("topic must be a non-empty string")
        if not rejection_reason or not rejection_reason.strip():
            raise ValueError("rejection_reason must be a non-empty string")

        score_breakdown = score_breakdown or {}
        quality_score = round(
            sum(
                score_breakdown.get(key, 0.0)
                for key in (
                    "ai_relevance",
                    "technical_depth",
                    "originality",
                    "educational_value",
                )
            )
            / 4,
            4,
        )
        confidence_score = self.calculate_confidence(
            quality_score, opinion_confidence
        )

        weaknesses = [rejection_reason]
        if score_breakdown.get("duplicate_risk", 0.0) >= 0.5:
            weaknesses.append(
                "High duplicate risk relative to previously published "
                "content."
            )
        if score_breakdown.get("ai_relevance", 1.0) < 0.3:
            weaknesses.append(
                "Insufficient relevance to AI/technology domain."
            )

        suggestions = self.suggest_improvements(weaknesses)

        report = ReflectionReport(
            topic=topic,
            publishing_decision="rejected",
            quality_score=quality_score,
            confidence_score=confidence_score,
            strengths=[],
            weaknesses=weaknesses,
            improvement_suggestions=suggestions,
            generated_at=self._current_timestamp(),
            details={
                "score_breakdown": dict(score_breakdown),
                "rejection_reason": rejection_reason,
                "opinion_confidence": opinion_confidence,
            },
        )

        self._reports.append(report)
        logger.info(
            "Reflection generated for rejected topic '%s': reason='%s'",
            topic,
            rejection_reason,
        )
        return report

    def _identify_strengths_weaknesses(
        self,
        score_breakdown: Dict[str, float],
        persona_consistency: float,
        source_credibility: float,
    ) -> tuple[List[str], List[str]]:
        """Identifies strengths and weaknesses from evaluated dimensions.

        Args:
            score_breakdown: The OpinionEngine score breakdown.
            persona_consistency: The computed persona consistency score.
            source_credibility: The computed source credibility score.

        Returns:
            A tuple of (strengths, weaknesses) lists.
        """
        dimensions = {
            "AI relevance": score_breakdown.get("ai_relevance", 0.0),
            "Technical depth": score_breakdown.get("technical_depth", 0.0),
            "Industry impact": score_breakdown.get("industry_impact", 0.0),
            "Educational value": score_breakdown.get(
                "educational_value", 0.0
            ),
            "Innovation": score_breakdown.get("innovation", 0.0),
            "Originality": score_breakdown.get("originality", 0.0),
            "Persona consistency": persona_consistency,
            "Source credibility": source_credibility,
        }

        strengths: List[str] = []
        weaknesses: List[str] = []

        for label, value in dimensions.items():
            if value >= 0.65:
                strengths.append(f"Strong {label.lower()} ({value:.2f}).")
            elif value < 0.4:
                weaknesses.append(f"Weak {label.lower()} ({value:.2f}).")

        duplicate_risk = score_breakdown.get("duplicate_risk", 0.0)
        if duplicate_risk >= 0.5:
            weaknesses.append(
                f"Elevated duplicate risk ({duplicate_risk:.2f})."
            )
        elif duplicate_risk <= 0.15:
            strengths.append(
                f"Low duplicate risk ({duplicate_risk:.2f})."
            )

        if not strengths:
            strengths.append("No standout strengths identified.")
        if not weaknesses:
            weaknesses.append("No significant weaknesses identified.")

        return strengths, weaknesses

    def suggest_improvements(self, weaknesses: List[str]) -> List[str]:
        """Generates actionable improvement suggestions from weaknesses.

        Args:
            weaknesses: A list of identified weakness descriptions.

        Returns:
            A list of improvement suggestion strings.
        """
        suggestions: List[str] = []

        for weakness in weaknesses:
            normalized = weakness.lower()
            if "technical depth" in normalized:
                suggestions.append(
                    "Add more technical detail or reference underlying "
                    "architecture/benchmarks to strengthen depth."
                )
            elif "ai relevance" in normalized:
                suggestions.append(
                    "Tighten the topic selection to stay closer to core "
                    "AI/technology themes."
                )
            elif "educational value" in normalized:
                suggestions.append(
                    "Include explanatory context or a brief breakdown to "
                    "improve reader takeaway."
                )
            elif "originality" in normalized or "duplicate" in normalized:
                suggestions.append(
                    "Seek a more differentiated angle to reduce overlap "
                    "with previously covered topics."
                )
            elif "persona consistency" in normalized:
                suggestions.append(
                    "Reinforce persona tone and signature phrasing "
                    "during content generation."
                )
            elif "source credibility" in normalized:
                suggestions.append(
                    "Prioritize higher-credibility sources such as "
                    "official research or documentation."
                )
            elif "industry impact" in normalized:
                suggestions.append(
                    "Connect the topic more explicitly to real-world "
                    "industry or market implications."
                )
            elif "innovation" in normalized:
                suggestions.append(
                    "Highlight what is genuinely new or forward-looking "
                    "about the development."
                )

        if not suggestions:
            suggestions.append(
                "Maintain current editorial standards; no immediate "
                "improvements identified."
            )

        # Deduplicate while preserving order.
        seen = set()
        unique_suggestions = []
        for suggestion in suggestions:
            if suggestion not in seen:
                seen.add(suggestion)
                unique_suggestions.append(suggestion)

        return unique_suggestions

    def generate_reflection(
        self,
        topic: str,
        publish: bool,
        reason: str,
        editorial_opinion: Optional[str] = None,
        source: str = "unknown",
        score_breakdown: Optional[Dict[str, float]] = None,
        opinion_confidence: float = 0.0,
    ) -> ReflectionReport:
        """Generates a reflection report for either outcome of a decision.

        This is the primary entry point of the ReflectionEngine, routing
        to `analyze_post` or `analyze_rejection` depending on the
        publishing decision.

        Args:
            topic: The topic being reflected upon.
            publish: Whether the topic was published.
            reason: The publish or rejection reason associated with the
                decision.
            editorial_opinion: The generated editorial opinion, required
                when `publish` is True.
            source: The origin source of the topic. Defaults to
                "unknown".
            score_breakdown: The OpinionEngine score breakdown
                dictionary for the topic.
            opinion_confidence: The confidence score assigned by the
                OpinionEngine.

        Returns:
            A ReflectionReport for the given decision.

        Raises:
            ValueError: If `publish` is True but `editorial_opinion` is
                not provided.
        """
        score_breakdown = score_breakdown or {}

        if publish:
            if not editorial_opinion:
                raise ValueError(
                    "editorial_opinion is required when publish is True"
                )
            return self.analyze_post(
                topic=topic,
                editorial_opinion=editorial_opinion,
                source=source,
                score_breakdown=score_breakdown,
                opinion_confidence=opinion_confidence,
            )

        return self.analyze_rejection(
            topic=topic,
            rejection_reason=reason,
            score_breakdown=score_breakdown,
            opinion_confidence=opinion_confidence,
        )

    def get_summary(self) -> Dict[str, Any]:
        """Provides a summary of publishing consistency and reflection history.

        Aggregates all generated reflection reports along with the
        publishing history from the MemoryEngine to give a high-level
        view of system consistency over time.

        Returns:
            A dictionary summarizing reflection statistics, including
            average quality/confidence scores and counts of accepted vs
            rejected decisions.
        """
        published_reports = [
            r for r in self._reports if r.publishing_decision == "published"
        ]
        rejected_reports = [
            r for r in self._reports if r.publishing_decision == "rejected"
        ]

        avg_quality = (
            round(
                sum(r.quality_score for r in published_reports)
                / len(published_reports),
                4,
            )
            if published_reports
            else 0.0
        )
        avg_confidence = (
            round(
                sum(r.confidence_score for r in self._reports)
                / len(self._reports),
                4,
            )
            if self._reports
            else 0.0
        )

        try:
            memory_summary = self._memory_engine.get_memory_summary()
        except Exception:  # noqa: BLE001 - defensive against backend swaps
            memory_summary = {}

        return {
            "total_reflections": len(self._reports),
            "published_count": len(published_reports),
            "rejected_count": len(rejected_reports),
            "average_quality_score": avg_quality,
            "average_confidence_score": avg_confidence,
            "memory_summary": memory_summary,
        }

    def register_extension(self, key: str, value: Any) -> None:
        """Registers arbitrary extension data for future capabilities.

        This method exists to support future integration with Publisher
        and API modules, or additional QA strategies, without breaking
        the existing interface.

        Args:
            key: The identifier for the extension data.
            value: The extension data to store.
        """
        self._extensions[key] = value
        logger.debug("Extension '%s' registered on ReflectionEngine.", key)

    def export(self) -> Dict[str, Any]:
        """Exports all reflection reports and summary statistics.

        Returns:
            A dictionary containing every generated reflection report
            and an aggregate summary, suitable for exposure through an
            API layer.
        """
        return {
            "reports": [report.to_dict() for report in self._reports],
            "summary": self.get_summary(),
            "extensions": dict(self._extensions),
        }

    def __repr__(self) -> str:
        """Returns a developer-friendly representation of the engine.

        Returns:
            A string representation of the ReflectionEngine instance.
        """
        return f"ReflectionEngine(reports={len(self._reports)})"