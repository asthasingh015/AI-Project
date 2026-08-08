"""Source configuration module for the Cortex AI Discovery Engine.

This module defines a clean, typed configuration system describing the
live information sources (primarily RSS/Atom feeds) that the Discovery
Engine polls to independently find current AI and technology topics. It
contains no network-fetching logic and no hardcoded articles or fake
topics only structured source metadata and validation utilities.

Actual HTTP/feed fetching is handled elsewhere (fetcher.py), which is
expected to consume SourceRegistry.get_enabled_sources() or
SourceRegistry.get_by_category() without needing to know how sources
are configured or added.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class SourceCategory(str, Enum):
    """Enumerates the topical categories a source can belong to.

    Using a string Enum keeps values JSON-serializable while still
    providing type safety and IDE autocompletion.
    """

    RESEARCH = "research"
    AI_NEWS = "ai_news"
    TECH_NEWS = "tech_news"
    ENGINEERING = "engineering"
    OPEN_SOURCE = "open_source"
    INDUSTRY = "industry"


class SourceType(str, Enum):
    """Enumerates the transport/protocol type of a source."""

    RSS = "rss"
    ATOM = "atom"


class SourcePriority(int, Enum):
    """Enumerates reliability/priority tiers for a source.

    Lower numeric value means higher priority. This ordering allows the
    fetcher or discovery pipeline to poll higher-priority sources more
    frequently or weight their topics more heavily.
    """

    CRITICAL = 1
    HIGH = 2
    MEDIUM = 3
    LOW = 4


@dataclass(frozen=True)
class SourceConfig:
    """Represents the configuration of a single discovery source.

    Attributes:
        name: A short, unique, human-readable identifier for the source
            (e.g., "arXiv cs.AI").
        url: The feed URL (RSS or Atom) to be polled by the fetcher.
        category: The topical category this source belongs to.
        priority: The reliability/priority tier of this source.
        source_type: The feed protocol type (RSS or Atom).
        enabled: Whether this source is currently active and should be
            included in fetch cycles.
        description: An optional human-readable description of the
            source's focus.
        tags: Optional free-form tags for finer-grained filtering by
            downstream consumers (e.g., "llm", "robotics").
    """

    name: str
    url: str
    category: SourceCategory
    priority: SourcePriority = SourcePriority.MEDIUM
    source_type: SourceType = SourceType.RSS
    enabled: bool = True
    description: str = ""
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Converts the source configuration to a plain dictionary.

        Returns:
            A dictionary representation of the source configuration with
            enum values resolved to their underlying primitive values.
        """
        data = asdict(self)
        data["category"] = self.category.value
        data["priority"] = self.priority.value
        data["source_type"] = self.source_type.value
        return data


class SourceValidationError(ValueError):
    """Raised when a SourceConfig fails validation."""


class SourceRegistry:
    """Registry maintaining the set of configured discovery sources.

    The SourceRegistry owns the canonical list of sources the Discovery
    Engine may poll. It is intentionally decoupled from any network
    fetching logic: it only stores, validates, and filters source
    configuration. New sources can be registered at runtime via
    add_source() without requiring changes to the fetcher.

    Attributes:
        _sources: A mapping of source name to SourceConfig, preserving
            registration order in insertion order (Python dict
            semantics).
    """

    def __init__(self, load_defaults: bool = True) -> None:
        """Initializes the SourceRegistry.

        Args:
            load_defaults: Whether to populate the registry with the
                built-in default AI/technology sources on
                initialization. Defaults to True.
        """
        self._sources: Dict[str, SourceConfig] = {}

        if load_defaults:
            for source in _build_default_sources():
                self.add_source(source)

        logger.info(
            "SourceRegistry initialized with %d sources.",
            len(self._sources),
        )

    def validate_source(self, source: SourceConfig) -> None:
        """Validates a source configuration for structural correctness.

        Args:
            source: The SourceConfig instance to validate.

        Raises:
            SourceValidationError: If the source fails any validation
                check (missing name, invalid URL, invalid enum values,
                etc.).
        """
        if not source.name or not source.name.strip():
            raise SourceValidationError("Source name must not be empty.")

        if not source.url or not source.url.strip():
            raise SourceValidationError(
                f"Source '{source.name}' has an empty URL."
            )

        parsed_url = urlparse(source.url)
        if parsed_url.scheme not in ("http", "https"):
            raise SourceValidationError(
                f"Source '{source.name}' has an invalid URL scheme: "
                f"'{parsed_url.scheme}'. Only http/https are supported."
            )
        if not parsed_url.netloc:
            raise SourceValidationError(
                f"Source '{source.name}' has a malformed URL: "
                f"'{source.url}'."
            )

        if not isinstance(source.category, SourceCategory):
            raise SourceValidationError(
                f"Source '{source.name}' has an invalid category: "
                f"{source.category!r}."
            )

        if not isinstance(source.priority, SourcePriority):
            raise SourceValidationError(
                f"Source '{source.name}' has an invalid priority: "
                f"{source.priority!r}."
            )

        if not isinstance(source.source_type, SourceType):
            raise SourceValidationError(
                f"Source '{source.name}' has an invalid source_type: "
                f"{source.source_type!r}."
            )

    def add_source(self, source: SourceConfig, replace: bool = False) -> None:
        """Adds a new source to the registry after validation.

        Args:
            source: The SourceConfig instance to register.
            replace: Whether to overwrite an existing source with the
                same name. Defaults to False.

        Raises:
            SourceValidationError: If the source fails validation.
            ValueError: If a source with the same name already exists
                and replace is False.
        """
        self.validate_source(source)

        if source.name in self._sources and not replace:
            raise ValueError(
                f"A source named '{source.name}' is already registered. "
                "Pass replace=True to overwrite it."
            )

        self._sources[source.name] = source
        logger.info(
            "Source registered: name='%s' category=%s priority=%s "
            "enabled=%s",
            source.name,
            source.category.value,
            source.priority.value,
            source.enabled,
        )

    def remove_source(self, name: str) -> bool:
        """Removes a source from the registry by name.

        Args:
            name: The name of the source to remove.

        Returns:
            True if the source existed and was removed, False otherwise.
        """
        if name in self._sources:
            del self._sources[name]
            logger.info("Source removed: name='%s'", name)
            return True
        return False

    def set_enabled(self, name: str, enabled: bool) -> None:
        """Enables or disables a registered source.

        Since SourceConfig is immutable (frozen dataclass), this creates
        a replacement instance with the updated enabled flag.

        Args:
            name: The name of the source to update.
            enabled: The new enabled status.

        Raises:
            KeyError: If no source with the given name is registered.
        """
        if name not in self._sources:
            raise KeyError(f"No source registered under name '{name}'.")

        existing = self._sources[name]
        updated = SourceConfig(
            name=existing.name,
            url=existing.url,
            category=existing.category,
            priority=existing.priority,
            source_type=existing.source_type,
            enabled=enabled,
            description=existing.description,
            tags=list(existing.tags),
        )
        self._sources[name] = updated
        logger.info("Source '%s' enabled=%s", name, enabled)

    def get_all_sources(self) -> List[SourceConfig]:
        """Returns every registered source, regardless of enabled status.

        Returns:
            A list of all SourceConfig instances in registration order.
        """
        return list(self._sources.values())

    def get_enabled_sources(self) -> List[SourceConfig]:
        """Returns all sources currently marked as enabled.

        Sources are returned ordered by priority (highest priority
        first), then by registration order.

        Returns:
            A list of enabled SourceConfig instances.
        """
        enabled = [s for s in self._sources.values() if s.enabled]
        return sorted(enabled, key=lambda s: s.priority.value)

    def get_by_category(
        self, category: SourceCategory, enabled_only: bool = True
    ) -> List[SourceConfig]:
        """Returns sources filtered by category.

        Args:
            category: The SourceCategory to filter by.
            enabled_only: Whether to only include enabled sources.
                Defaults to True.

        Returns:
            A list of SourceConfig instances matching the category,
            ordered by priority.
        """
        candidates = (
            self.get_enabled_sources()
            if enabled_only
            else self.get_all_sources()
        )
        matches = [s for s in candidates if s.category == category]
        return sorted(matches, key=lambda s: s.priority.value)

    def get_by_priority(
        self, priority: SourcePriority, enabled_only: bool = True
    ) -> List[SourceConfig]:
        """Returns sources filtered by priority tier.

        Args:
            priority: The SourcePriority tier to filter by.
            enabled_only: Whether to only include enabled sources.
                Defaults to True.

        Returns:
            A list of SourceConfig instances matching the priority tier.
        """
        candidates = (
            self.get_enabled_sources()
            if enabled_only
            else self.get_all_sources()
        )
        return [s for s in candidates if s.priority == priority]

    def get_source(self, name: str) -> Optional[SourceConfig]:
        """Retrieves a single source by name.

        Args:
            name: The name of the source to retrieve.

        Returns:
            The matching SourceConfig, or None if not found.
        """
        return self._sources.get(name)

    def validate_all(self) -> Dict[str, List[str]]:
        """Validates every registered source and collects any errors.

        Returns:
            A dictionary mapping source name to a list of validation
            error messages. Sources with no errors are omitted.
        """
        errors: Dict[str, List[str]] = {}
        for name, source in self._sources.items():
            try:
                self.validate_source(source)
            except SourceValidationError as exc:
                errors[name] = [str(exc)]
        return errors

    def export(self) -> Dict[str, Any]:
        """Exports the full registry state as plain dictionaries.

        Returns:
            A dictionary containing all sources and summary counts,
            suitable for serialization or diagnostics.
        """
        return {
            "sources": [s.to_dict() for s in self.get_all_sources()],
            "total_count": len(self._sources),
            "enabled_count": len(self.get_enabled_sources()),
        }

    def __len__(self) -> int:
        """Returns the number of registered sources.

        Returns:
            The count of sources currently registered.
        """
        return len(self._sources)

    def __repr__(self) -> str:
        """Returns a developer-friendly representation of the registry.

        Returns:
            A string representation of the SourceRegistry instance.
        """
        return (
            f"SourceRegistry(total={len(self._sources)}, "
            f"enabled={len(self.get_enabled_sources())})"
        )


def _build_default_sources() -> List[SourceConfig]:
    """Builds the built-in list of default AI/technology sources.

    All entries here are real, publicly available RSS/Atom feeds from
    established research and technology publications. No individual
    articles or fabricated topics are included only feed-level
    configuration.

    Returns:
        A list of default SourceConfig instances.
    """
    return [
        SourceConfig(
            name="arXiv cs.AI",
            url="http://export.arxiv.org/rss/cs.AI",
            category=SourceCategory.RESEARCH,
            priority=SourcePriority.CRITICAL,
            source_type=SourceType.RSS,
            description="arXiv Artificial Intelligence research feed.",
            tags=["research", "papers", "ai"],
        ),
        SourceConfig(
            name="arXiv cs.LG",
            url="http://export.arxiv.org/rss/cs.LG",
            category=SourceCategory.RESEARCH,
            priority=SourcePriority.CRITICAL,
            source_type=SourceType.RSS,
            description="arXiv Machine Learning research feed.",
            tags=["research", "papers", "machine-learning"],
        ),
        SourceConfig(
            name="arXiv cs.CL",
            url="http://export.arxiv.org/rss/cs.CL",
            category=SourceCategory.RESEARCH,
            priority=SourcePriority.HIGH,
            source_type=SourceType.RSS,
            description=(
                "arXiv Computation and Language (NLP) research feed."
            ),
            tags=["research", "papers", "nlp"],
        ),
        SourceConfig(
            name="arXiv cs.CV",
            url="http://export.arxiv.org/rss/cs.CV",
            category=SourceCategory.RESEARCH,
            priority=SourcePriority.MEDIUM,
            source_type=SourceType.RSS,
            description=(
                "arXiv Computer Vision and Pattern Recognition feed."
            ),
            tags=["research", "papers", "computer-vision"],
        ),
        SourceConfig(
            name="MIT Technology Review AI",
            url="https://www.technologyreview.com/topic/artificial-intelligence/feed",
            category=SourceCategory.AI_NEWS,
            priority=SourcePriority.HIGH,
            source_type=SourceType.RSS,
            description="MIT Technology Review's AI coverage.",
            tags=["news", "analysis", "ai"],
        ),
        SourceConfig(
            name="VentureBeat AI",
            url="https://venturebeat.com/category/ai/feed/",
            category=SourceCategory.AI_NEWS,
            priority=SourcePriority.HIGH,
            source_type=SourceType.RSS,
            description="VentureBeat's dedicated AI news vertical.",
            tags=["news", "industry", "ai"],
        ),
        SourceConfig(
            name="TechCrunch",
            url="https://techcrunch.com/feed/",
            category=SourceCategory.TECH_NEWS,
            priority=SourcePriority.MEDIUM,
            source_type=SourceType.RSS,
            description="General technology and startup news.",
            tags=["news", "startups", "technology"],
        ),
        SourceConfig(
            name="The Verge",
            url="https://www.theverge.com/rss/index.xml",
            category=SourceCategory.TECH_NEWS,
            priority=SourcePriority.MEDIUM,
            source_type=SourceType.RSS,
            description="Consumer technology and industry news.",
            tags=["news", "technology", "consumer"],
        ),
        SourceConfig(
            name="Ars Technica",
            url="https://feeds.arstechnica.com/arstechnica/index",
            category=SourceCategory.TECH_NEWS,
            priority=SourcePriority.MEDIUM,
            source_type=SourceType.RSS,
            description="In-depth technology news and analysis.",
            tags=["news", "technology", "analysis"],
        ),
        SourceConfig(
            name="Google AI Blog",
            url="https://blog.google/technology/ai/rss/",
            category=SourceCategory.ENGINEERING,
            priority=SourcePriority.HIGH,
            source_type=SourceType.RSS,
            description="Official Google AI research and product blog.",
            tags=["engineering", "research", "official"],
        ),
        SourceConfig(
            name="Hugging Face Blog",
            url="https://huggingface.co/blog/feed.xml",
            category=SourceCategory.OPEN_SOURCE,
            priority=SourcePriority.HIGH,
            source_type=SourceType.ATOM,
            description="Open-source AI models, libraries, and research.",
            tags=["open-source", "models", "engineering"],
        ),
        SourceConfig(
            name="GitHub Blog",
            url="https://github.blog/feed/",
            category=SourceCategory.OPEN_SOURCE,
            priority=SourcePriority.LOW,
            source_type=SourceType.RSS,
            description="Engineering and open-source ecosystem updates.",
            tags=["open-source", "engineering", "developer-tools"],
        ),
        SourceConfig(
            name="Wired AI",
            url="https://www.wired.com/feed/tag/ai/latest/rss",
            category=SourceCategory.AI_NEWS,
            priority=SourcePriority.MEDIUM,
            source_type=SourceType.RSS,
            description="Wired's coverage of artificial intelligence.",
            tags=["news", "ai", "culture"],
        ),
        SourceConfig(
            name="Reuters Technology",
            url="https://www.reutersagency.com/feed/?best-topics=tech",
            category=SourceCategory.INDUSTRY,
            priority=SourcePriority.HIGH,
            source_type=SourceType.RSS,
            description="Reuters industry and technology reporting.",
            tags=["news", "industry", "business"],
        ),
    ]


# Module-level default registry instance for convenient import-and-use
# access by other Discovery Engine components (e.g., fetcher.py).
default_registry = SourceRegistry(load_defaults=True)