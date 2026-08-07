"""Persona engine module for Cortex AI.

This module defines the PersonaEngine class, which is responsible for
loading a PersonaIdentity, maintaining a consistent writing style, tone,
and audience preferences, validating topic relevance against the persona's
domain, and producing writing instructions consumable by the Publisher
module.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

from brain.identity import PersonaIdentity

logger = logging.getLogger(__name__)


@dataclass
class WritingGuideline:
    """Represents a structured writing guideline for content generation.

    Attributes:
        tone: The tone to be used in the content (e.g., "professional").
        style: The writing style to be used (e.g., "concise, analytical").
        audience: The target audience description.
        vocabulary_level: The complexity level of vocabulary to use.
        do_list: A list of practices the writer should follow.
        avoid_list: A list of practices the writer should avoid.
        signature_phrases: Recurring phrases that reinforce persona voice.
    """

    tone: str
    style: str
    audience: str
    vocabulary_level: str
    do_list: List[str] = field(default_factory=list)
    avoid_list: List[str] = field(default_factory=list)
    signature_phrases: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Converts the writing guideline to a dictionary.

        Returns:
            A dictionary representation of the writing guideline.
        """
        return asdict(self)


class PersonaEngine:
    """Engine responsible for maintaining a consistent AI persona.

    The PersonaEngine loads a PersonaIdentity and ensures that all
    downstream content generation (via the Publisher module) reflects a
    consistent tone, writing style, and audience alignment. It also acts
    as a gatekeeper, rejecting topics that fall outside the persona's
    defined domain of interest.

    Attributes:
        _identity: The currently loaded PersonaIdentity instance.
        _is_loaded: Whether a persona has been successfully loaded.
        _extensions: A dictionary reserved for future extension data,
            such as plugin-specific configuration or memory hooks.
    """

    def __init__(self, identity: Optional[PersonaIdentity] = None) -> None:
        """Initializes the PersonaEngine.

        Args:
            identity: An optional PersonaIdentity instance to load
                immediately. If not provided, `load_persona()` must be
                called before using the engine.
        """
        self._identity: Optional[PersonaIdentity] = None
        self._is_loaded: bool = False
        self._extensions: Dict[str, Any] = {}

        if identity is not None:
            self.load_persona(identity)

    def load_persona(self, identity: PersonaIdentity) -> None:
        """Loads a PersonaIdentity into the engine.

        Args:
            identity: The PersonaIdentity instance to load.

        Raises:
            TypeError: If `identity` is not a PersonaIdentity instance.
            ValueError: If the identity fails basic validation checks.
        """
        if not isinstance(identity, PersonaIdentity):
            raise TypeError(
                "identity must be an instance of PersonaIdentity, "
                f"got {type(identity).__name__}"
            )

        self._validate_identity(identity)
        self._identity = identity
        self._is_loaded = True
        logger.info(
            "Persona '%s' loaded successfully.",
            getattr(identity, "name", "unknown"),
        )

    def _validate_identity(self, identity: PersonaIdentity) -> None:
        """Validates that the identity contains the minimum required data.

        Args:
            identity: The PersonaIdentity instance to validate.

        Raises:
            ValueError: If required attributes are missing or empty.
        """
        required_attrs = ("name", "tone", "writing_style", "interests")
        for attr in required_attrs:
            if not hasattr(identity, attr):
                raise ValueError(
                    f"PersonaIdentity is missing required attribute: {attr}"
                )
            value = getattr(identity, attr)
            if not value:
                raise ValueError(
                    f"PersonaIdentity attribute '{attr}' cannot be empty"
                )

    def _ensure_loaded(self) -> None:
        """Ensures a persona has been loaded before use.

        Raises:
            RuntimeError: If no persona has been loaded yet.
        """
        if not self._is_loaded or self._identity is None:
            raise RuntimeError(
                "No PersonaIdentity has been loaded. Call load_persona() "
                "first."
            )

    def get_profile(self) -> Dict[str, Any]:
        """Returns the full persona profile.

        Returns:
            A dictionary representing the persona's identity, tone,
            writing style, audience, and interests.

        Raises:
            RuntimeError: If no persona has been loaded.
        """
        self._ensure_loaded()
        identity = self._identity

        profile: Dict[str, Any] = {
            "name": getattr(identity, "name", None),
            "bio": getattr(identity, "bio", None),
            "tone": getattr(identity, "tone", None),
            "writing_style": getattr(identity, "writing_style", None),
            "interests": list(getattr(identity, "interests", []) or []),
            "audience": getattr(identity, "audience", None),
            "values": list(getattr(identity, "values", []) or []),
            "vocabulary_level": getattr(
                identity, "vocabulary_level", "intermediate"
            ),
            "signature_phrases": list(
                getattr(identity, "signature_phrases", []) or []
            ),
            "extensions": dict(self._extensions),
        }
        return profile

    def is_topic_relevant(self, topic: str) -> bool:
        """Checks whether a given topic matches the persona's interests.

        Performs a case-insensitive substring and keyword match between
        the provided topic and the persona's declared interests/domain
        keywords.

        Args:
            topic: The topic string to evaluate.

        Returns:
            True if the topic is relevant to the persona's domain,
            False otherwise.

        Raises:
            RuntimeError: If no persona has been loaded.
            ValueError: If the topic string is empty.
        """
        self._ensure_loaded()

        if not topic or not topic.strip():
            raise ValueError("topic must be a non-empty string")

        normalized_topic = topic.lower().strip()
        interests: List[str] = [
            interest.lower()
            for interest in (getattr(self._identity, "interests", []) or [])
        ]

        if not interests:
            logger.warning(
                "Persona '%s' has no defined interests; rejecting topic "
                "by default.",
                getattr(self._identity, "name", "unknown"),
            )
            return False

        for interest in interests:
            if interest in normalized_topic or normalized_topic in interest:
                return True

        topic_keywords = set(normalized_topic.replace("-", " ").split())
        for interest in interests:
            interest_keywords = set(interest.replace("-", " ").split())
            if topic_keywords & interest_keywords:
                return True

        return False

    def get_writing_instruction(
        self, topic: Optional[str] = None
    ) -> WritingGuideline:
        """Generates a writing guideline for the Publisher module.

        Args:
            topic: An optional topic used to validate relevance before
                producing the guideline.

        Returns:
            A WritingGuideline instance encapsulating tone, style,
            audience, and constraints for content generation.

        Raises:
            RuntimeError: If no persona has been loaded.
            ValueError: If the topic is provided but is not relevant to
                the persona's domain.
        """
        self._ensure_loaded()
        identity = self._identity

        if topic is not None and not self.is_topic_relevant(topic):
            raise ValueError(
                f"Topic '{topic}' is outside the persona's domain of "
                f"interest and was rejected."
            )

        avoid_list = list(getattr(identity, "avoid_topics", []) or [])
        avoid_list.append("content that contradicts the persona's values")

        guideline = WritingGuideline(
            tone=getattr(identity, "tone", "neutral"),
            style=getattr(identity, "writing_style", "clear and concise"),
            audience=getattr(identity, "audience", "general audience"),
            vocabulary_level=getattr(
                identity, "vocabulary_level", "intermediate"
            ),
            do_list=list(getattr(identity, "writing_do", []) or []),
            avoid_list=avoid_list,
            signature_phrases=list(
                getattr(identity, "signature_phrases", []) or []
            ),
        )
        return guideline

    def update_persona(self, **updates: Any) -> None:
        """Updates attributes of the currently loaded persona identity.

        This allows incremental refinement of the persona (e.g., adding
        new interests, adjusting tone) without reloading a completely new
        PersonaIdentity instance.

        Args:
            **updates: Keyword arguments mapping attribute names to their
                new values.

        Raises:
            RuntimeError: If no persona has been loaded.
            AttributeError: If an update key does not correspond to an
                existing attribute on the PersonaIdentity.
        """
        self._ensure_loaded()

        for key, value in updates.items():
            if not hasattr(self._identity, key):
                raise AttributeError(
                    f"PersonaIdentity has no attribute '{key}' to update."
                )
            setattr(self._identity, key, value)
            logger.info("Persona attribute '%s' updated.", key)

        self._validate_identity(self._identity)

    def export(self) -> Dict[str, Any]:
        """Exports the full persona state for persistence or transfer.

        Returns:
            A dictionary containing the persona profile and engine
            metadata, suitable for serialization (e.g., to JSON).

        Raises:
            RuntimeError: If no persona has been loaded.
        """
        self._ensure_loaded()
        return {
            "profile": self.get_profile(),
            "is_loaded": self._is_loaded,
            "extensions": dict(self._extensions),
        }

    def register_extension(self, key: str, value: Any) -> None:
        """Registers arbitrary extension data for future capabilities.

        This method exists to support future extension of the
        PersonaEngine (e.g., plugin systems, memory modules, custom
        scoring functions) without breaking the existing interface.

        Args:
            key: The identifier for the extension data.
            value: The extension data to store.
        """
        self._extensions[key] = value
        logger.debug("Extension '%s' registered on PersonaEngine.", key)

    def __repr__(self) -> str:
        """Returns a developer-friendly representation of the engine.

        Returns:
            A string representation of the PersonaEngine instance.
        """
        name = (
            getattr(self._identity, "name", "unloaded")
            if self._identity
            else "unloaded"
        )
        return f"PersonaEngine(persona={name!r}, loaded={self._is_loaded})"