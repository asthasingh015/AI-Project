"""
Cortex AI Discovery Engine - Sources Package

Exports the article fetching components used by the discovery pipeline.
"""

from discovery.sources.fetcher import (
    ArticleFetcher,
    FeedSource,
    FetcherConfig,
)

__all__ = [
    "ArticleFetcher",
    "FeedSource",
    "FetcherConfig",
]