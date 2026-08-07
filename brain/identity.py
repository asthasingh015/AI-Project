"""Identity module for the Cortex AI Brain.

This module defines the core persona identity system used by the
Autonomous AI Creator. It provides enumerations for writing style and
tone, a dataclass representing a persona's identity, and a factory
class responsible for generating, validating, and updating personas.

Typical usage example:

    factory = IdentityFactory()
    persona = factory.generate_default_persona()
    data = factory.to_dict(persona)
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class WritingStyle(Enum):
    """Enumeration of supported writing styles.

    Attributes:
        ANALYTICAL: Data-driven, logical, and structured writing.
        CONVERSATIONAL: Casual, dialogue-like writing.
        NARRATIVE: Story-driven writing with a clear arc.
        TECHNICAL: Precise, jargon-heavy, in-depth writing.
        PERSUASIVE: Argument-driven writing intended to convince.
        MINIMALIST: Short, concise, and to-the-point writing.
    """

    ANALYTICAL = "analytical"
    CONVERSATIONAL = "conversational"
    NARRATIVE = "narrative"
    TECHNICAL = "technical"
    PERSUASIVE = "persuasive"
    MINIMALIST = "minimalist"


class Tone(Enum):
    """Enumeration of supported tones.

    Attributes:
        PROFESSIONAL: Formal and business-appropriate tone.
        FRIENDLY: Warm and approachable tone.
        AUTHORITATIVE: Confident, expert-driven tone.
        HUMOROUS: Light-hearted and witty tone.
        INSPIRATIONAL: Motivating and uplifting tone.
        NEUTRAL: Balanced and objective tone.
    """

    PROFESSIONAL = "professional"
    FRIENDLY = "friendly"
    AUTHORITATIVE = "authoritative"
    HUMOROUS = "humorous"
    INSPIRATIONAL = "inspirational"
    NEUTRAL = "neutral"


@dataclass
class PersonaIdentity:
    """Represents the identity configuration of an autonomous AI persona.

    Attributes:
        agent_id: Unique identifier for the persona.
        name: Human-readable name of the persona.
        domain: Primary domain or subject matter expertise.
        writing_style: The persona's writing style.
        tone: The persona's tone of communication.
        audience: List of target audience segments.
        interests: List of topics the persona is interested in.
        editorial_rules: List of editorial rules the persona must follow.
        forbidden_topics: List of topics the persona must never discuss.
        signature: Optional closing signature used in content.
        confidence_threshold: Minimum confidence score (0-1) required
            before the persona publishes content.
        posting_frequency_minutes: Minimum interval, in minutes, between
            posts.
        created_at: UTC timestamp of persona creation.
        updated_at: UTC timestamp of the last persona update.
        is_active: Whether the persona is currently active.
    """

    agent_id: str
    name: str
    domain: str
    writing_style: WritingStyle
    tone: Tone
    audience: list[str] = field(default_factory=list)
    interests: list[str] = field(default_factory=list)
    editorial_rules: list[str] = field(default_factory=list)
    forbidden_topics: list[str] = field(default_factory=list)
    signature: str = ""
    confidence_threshold: float = 0.75
    posting_frequency_minutes: int = 60
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    is_active: bool = True


class IdentityValidationError(ValueError):
    """Raised when a `PersonaIdentity` fails validation."""


class IdentityFactory:
    """Factory responsible for creating, validating, and updating personas.

    This class centralizes all persona lifecycle operations, ensuring
    that every `PersonaIdentity` instance produced or mutated by the
    system adheres to Cortex AI's business rules.
    """

    DEFAULT_NAME: str = "Nova"
    DEFAULT_DOMAIN: str = "AI Technology"
    DEFAULT_AUDIENCE: list[str] = [
        "Developers",
        "Researchers",
        "Startup Founders",
    ]
    DEFAULT_INTERESTS: list[str] = [
        "LLMs",
        "AI Agents",
        "Machine Learning",
        "Open Source",
        "Generative AI",
    ]
    DEFAULT_EDITORIAL_RULES: list[str] = [
        "Never publish clickbait",
        "Always cite sources",
        "Avoid duplicate posts",
        "Prefer technical depth",
    ]
    DEFAULT_FORBIDDEN_TOPICS: list[str] = [
        "Politics",
        "Religion",
        "Celebrity Gossip",
        "Sports",
    ]

    def generate_default_persona(self) -> PersonaIdentity:
        """Generates the default Cortex AI persona ("Nova").

        Returns:
            A fully populated and validated `PersonaIdentity` instance
            representing the default persona.
        """
        persona = PersonaIdentity(
            agent_id=self._generate_agent_id(),
            name=self.DEFAULT_NAME,
            domain=self.DEFAULT_DOMAIN,
            writing_style=WritingStyle.ANALYTICAL,
            tone=Tone.PROFESSIONAL,
            audience=list(self.DEFAULT_AUDIENCE),
            interests=list(self.DEFAULT_INTERESTS),
            editorial_rules=list(self.DEFAULT_EDITORIAL_RULES),
            forbidden_topics=list(self.DEFAULT_FORBIDDEN_TOPICS),
            signature=f"— {self.DEFAULT_NAME}, Cortex AI",
        )
        self.validate_persona(persona)
        return persona

    def create_from_api_input(self, payload: dict[str, Any]) -> PersonaIdentity:
        """Creates a `PersonaIdentity` from raw API input.

        Args:
            payload: A dictionary of persona fields, typically sourced
                from an incoming API request body. Missing optional
                fields fall back to sane defaults.

        Returns:
            A validated `PersonaIdentity` instance.

        Raises:
            IdentityValidationError: If the resulting persona fails
                validation.
            KeyError: If a required field is missing from `payload`.
        """
        try:
            writing_style = self._parse_enum(
                WritingStyle, payload.get("writing_style", "analytical")
            )
            tone = self._parse_enum(Tone, payload.get("tone", "professional"))

            persona = PersonaIdentity(
                agent_id=payload.get("agent_id") or self._generate_agent_id(),
                name=payload["name"],
                domain=payload["domain"],
                writing_style=writing_style,
                tone=tone,
                audience=list(payload.get("audience", [])),
                interests=list(payload.get("interests", [])),
                editorial_rules=list(
                    payload.get(
                        "editorial_rules", self.DEFAULT_EDITORIAL_RULES
                    )
                ),
                forbidden_topics=list(
                    payload.get(
                        "forbidden_topics", self.DEFAULT_FORBIDDEN_TOPICS
                    )
                ),
                signature=payload.get("signature", ""),
                confidence_threshold=float(
                    payload.get("confidence_threshold", 0.75)
                ),
                posting_frequency_minutes=int(
                    payload.get("posting_frequency_minutes", 60)
                ),
                is_active=bool(payload.get("is_active", True)),
            )
        except KeyError as exc:
            raise IdentityValidationError(
                f"Missing required field in API input: {exc}"
            ) from exc

        self.validate_persona(persona)
        return persona

    def validate_persona(self, persona: PersonaIdentity) -> None:
        """Validates a `PersonaIdentity` against Cortex AI business rules.

        Args:
            persona: The persona instance to validate.

        Raises:
            IdentityValidationError: If any validation rule is violated.
        """
        errors: list[str] = []

        if not persona.domain or not persona.domain.strip():
            errors.append("Domain is required.")

        if not 0.0 <= persona.confidence_threshold <= 1.0:
            errors.append("Confidence threshold must be between 0 and 1.")

        if persona.posting_frequency_minutes <= 0:
            errors.append("Posting frequency must be greater than 0.")

        if not persona.audience:
            errors.append("Audience cannot be empty.")

        if not persona.interests:
            errors.append("Interests cannot be empty.")

        if errors:
            raise IdentityValidationError(
                "Persona validation failed: " + "; ".join(errors)
            )

    def update_persona(
        self, persona: PersonaIdentity, updates: dict[str, Any]
    ) -> PersonaIdentity:
        """Applies updates to an existing persona and re-validates it.

        Args:
            persona: The existing persona instance to update.
            updates: A dictionary of field names to new values. Only
                attributes that already exist on `PersonaIdentity` are
                applied; unknown keys are ignored.

        Returns:
            The updated and validated `PersonaIdentity` instance.

        Raises:
            IdentityValidationError: If the updated persona fails
                validation.
        """
        for key, value in updates.items():
            if key == "writing_style" and not isinstance(value, WritingStyle):
                value = self._parse_enum(WritingStyle, value)
            if key == "tone" and not isinstance(value, Tone):
                value = self._parse_enum(Tone, value)

            if hasattr(persona, key):
                setattr(persona, key, value)

        persona.updated_at = datetime.now(timezone.utc)
        self.validate_persona(persona)
        return persona

    def to_dict(self, persona: PersonaIdentity) -> dict[str, Any]:
        """Converts a `PersonaIdentity` into a JSON-serializable dictionary.

        Args:
            persona: The persona instance to convert.

        Returns:
            A dictionary representation of the persona, with enums and
            timestamps converted to strings.
        """
        return {
            "agent_id": persona.agent_id,
            "name": persona.name,
            "domain": persona.domain,
            "writing_style": persona.writing_style.value,
            "tone": persona.tone.value,
            "audience": list(persona.audience),
            "interests": list(persona.interests),
            "editorial_rules": list(persona.editorial_rules),
            "forbidden_topics": list(persona.forbidden_topics),
            "signature": persona.signature,
            "confidence_threshold": persona.confidence_threshold,
            "posting_frequency_minutes": persona.posting_frequency_minutes,
            "created_at": persona.created_at.isoformat(),
            "updated_at": persona.updated_at.isoformat(),
            "is_active": persona.is_active,
        }

    @staticmethod
    def _generate_agent_id() -> str:
        """Generates a unique agent identifier.

        Returns:
            A UUID4-based string prefixed with `agent-`.
        """
        return f"agent-{uuid.uuid4()}"

    @staticmethod
    def _parse_enum(enum_cls: type[Enum], value: Any) -> Enum:
        """Parses a raw value into the given enum type.

        Args:
            enum_cls: The enum class to parse into.
            value: The raw value, either an enum instance or a string
                matching one of the enum's values.

        Returns:
            The corresponding enum member.

        Raises:
            IdentityValidationError: If `value` does not match any
                member of `enum_cls`.
        """
        if isinstance(value, enum_cls):
            return value

        try:
            return enum_cls(str(value).lower())
        except ValueError as exc:
            valid_values = ", ".join(member.value for member in enum_cls)
            raise IdentityValidationError(
                f"Invalid value '{value}' for {enum_cls.__name__}. "
                f"Valid options are: {valid_values}."
            ) from exc