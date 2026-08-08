from pydantic import BaseModel
from typing import Optional


class Topic(BaseModel):
    title: str
    description: str
    category: str
    source: str
    url: str
    published_at: Optional[str] = None


class IntelligenceResult(BaseModel):
    topic: Topic
    trend_score: float
    community_interest: float
    source_confidence: float
    decision: str
    reason: str