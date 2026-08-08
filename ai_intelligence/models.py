"""
AI Intelligence Foundation - Data Models Contract

Defines structured input and output contracts for AI article analysis.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass
class PreparedArticleInput:
    """
    Standardized AI-ready text representation derived from normalized article dictionaries.
    """

    article_id: str
    formatted_prompt_text: str
    raw_title: str
    raw_url: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AnalysisResult:
    """
    Structured output contract produced by AI analysis providers.
    Designed for future capabilities: summarization, topic extraction, entity analysis, and scoring.
    """

    article_id: str
    status: str = "success"  # Options: "success", "error", "fallback"
    error_message: Optional[str] = None
    summary: Optional[str] = None
    topics: List[str] = field(default_factory=list)
    category: Optional[str] = None
    keywords: List[str] = field(default_factory=list)
    entities: List[str] = field(default_factory=list)
    importance_explanation: Optional[str] = None
    confidence: float = 0.0
    provider_name: str = "unknown"
    model_name: str = "unknown"
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    raw_response: Optional[Dict[str, Any]] = field(default=None, repr=False)
    execution_time_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Converts the analysis result to a clean, JSON-serializable dictionary."""
        return {
            "article_id": self.article_id,
            "status": self.status,
            "error_message": self.error_message,
            "summary": self.summary,
            "topics": self.topics,
            "category": self.category,
            "keywords": self.keywords,
            "entities": self.entities,
            "importance_explanation": self.importance_explanation,
            "confidence": self.confidence,
            "provider_name": self.provider_name,
            "model_name": self.model_name,
            "created_at": self.created_at,
            "execution_time_ms": self.execution_time_ms,
        }