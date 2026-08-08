"""
Cortex AI Discovery Engine - Local Demonstration Script for Module 2 Phase 1

Demonstrates end-to-end execution of the AI Processing Foundation:
  Module 1 Scored Article -> Article Preparation -> AI Provider Abstraction -> Mock Provider -> Structured AI Result
"""

import json
import logging
from ai_intelligence.config import AIConfig
from ai_intelligence.article_preprocessor import ArticlePreprocessor
from ai_intelligence.providers.mock import MockAIProvider


def run_demo() -> None:
    # Configure console logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    logger = logging.getLogger("ai_intelligence.demo")
    logger.info("Starting Module 2 Phase 1 Demonstration...")

    # 1. Sample Scored Article Dictionary (mimicking Module 1 pipeline output)
    sample_article = {
        "title": "Agentic AI Frameworks Revolutionize Autonomous Systems",
        "url": "https://ai-discovery.org/articles/agentic-ai-frameworks",
        "description": "Researchers publish a novel framework for multi-agent LLM systems with real-time tool orchestration.",
        "published": "2026-08-08T18:00:00Z",
        "source_name": "AI Discovery Journal",
        "source_url": "https://ai-discovery.org",
        "category": "Artificial Intelligence",
        "priority": 1,
        "tags": ["Agentic AI", "LLM", "Multi-Agent", "Autonomous Systems"],
        "score": 92.5,
        "score_breakdown": {
            "source_priority": 25.0,
            "title_quality": 15.0,
            "description_quality": 15.0,
            "freshness": 20.0,
            "topic_relevance": 17.5,
        },
    }

    logger.info("Received scored article dictionary from Module 1: '%s'", sample_article["title"])

    # 2. Step 1: Preprocess Article
    config = AIConfig(provider_name="mock", model_name="mock-v1-offline")
    preprocessor = ArticlePreprocessor(config=config)
    prepared_input = preprocessor.prepare(sample_article)

    print("\n" + "=" * 65)
    print("STEP 1: PREPROCESSED ARTICLE INPUT")
    print("=" * 65)
    print(f"Article ID    : {prepared_input.article_id}")
    print(f"Raw Title     : {prepared_input.raw_title}")
    print("\nFormatted Prompt Text:")
    print("-" * 45)
    print(prepared_input.formatted_prompt_text)
    print("-" * 45)

    # 3. Step 2 & 3: AI Provider Abstraction via Mock AI Provider
    provider = MockAIProvider(config=config)
    analysis_result = provider.analyze_article(prepared_input)

    # 4. Step 4: Output Structured Result
    print("\n" + "=" * 65)
    print("STEP 2 & 3: STRUCTURED AI ANALYSIS RESULT")
    print("=" * 65)
    print(json.dumps(analysis_result.to_dict(), indent=2))

    # Verification Checks
    print("\n" + "=" * 65)
    print("VERIFICATION CHECKS")
    print("=" * 65)
    print(f"Original Article Mutated? {'analysis_result' in sample_article} (Expected: False)")
    print(f"Analysis Status         : {analysis_result.status} (Expected: success)")
    print(f"Execution Time          : {analysis_result.execution_time_ms} ms")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    run_demo()