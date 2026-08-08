"""AI content generation with a clean OpenAI -> Gemini fallback strategy.

Provider selection:
    * OPENAI_API_KEY present          -> use OpenAI
    * OpenAI fails and GEMINI_API_KEY -> fall back to Gemini
    * Only GEMINI_API_KEY             -> use Gemini
    * Neither key                     -> ProviderConfigurationError

SDKs are imported lazily so the application still boots even if a
provider SDK is not installed. No API keys are ever logged.
"""

import json
import re
from typing import Any
from urllib.parse import urlparse

from publisher.config import settings
from publisher.utils.logger import get_logger

logger = get_logger("publisher.generator")


class ProviderConfigurationError(RuntimeError):
    """Raised when no AI provider is configured."""


def _select_provider() -> str | None:
    """Return the preferred provider name or ``None`` if none is set."""
    if settings.openai_api_key:
        return "openai"
    if settings.gemini_api_key:
        return "gemini"
    return None


def _build_system_prompt(persona: dict) -> str:
    """Compose the system prompt from the supplied persona."""
    name = persona.get("name", "Nova")
    role = persona.get("role", "AI Technology Thinker")
    tone = persona.get("tone", "analytical")
    style = persona.get("style", "concise and insightful")
    values = persona.get("values") or []
    opinions = persona.get("opinions") or []

    values_text = ", ".join(str(v) for v in values) if values else "technical accuracy, innovation, practical thinking"
    opinions_text = (
        "\n".join(f"- {o}" for o in opinions)
        if opinions
        else "- AI should augment human reasoning"
    )

    return f"""
You are {name}, an {role}.
Writing tone: {tone}.
Writing style: {style}.
Core values: {values_text}.
Point of view:
{opinions_text}

You write LinkedIn-style technology posts.
You are NOT a generic AI writer. You are an AI technology thinker with a
clear, defensible point of view.
Guidelines:
- Technology-focused and insightful.
- Have a clear point of view.
- Avoid generic motivational content.
- Avoid excessive emojis.
- Avoid fake personal experiences.
- Avoid fabricated statistics.
- Avoid fabricated sources or unsupported claims.
- Suitable for a professional technology audience.
""".strip()


def _build_user_prompt(topic: dict) -> str:
    """Compose the user prompt from the approved topic."""
    title = topic.get("title", "Untitled topic")
    description = topic.get("description", "")
    sources = topic.get("sources") or []

    sources_text = "\n".join(f"- {s}" for s in sources) if sources else "- (none)"

    return f"""
Write a LinkedIn-style technology post about:

Title: {title}
Description: {description}

Reference material (use as sources where relevant):
{sources_text}

Return a single JSON object (no markdown fences, no commentary) exactly shaped as:
{{
  "text": "the full LinkedIn post text",
  "rationale": "why this topic is worth publishing, why it fits the persona, and what insight it provides",
  "sources": ["optional valid source urls"]
}}
""".strip()


def _is_valid_url(value: str) -> bool:
    """Accept only real http(s) URLs with a host."""
    parsed = urlparse(value)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def _parse_generation(content: str, topic: dict) -> dict:
    """Parse AI JSON output into ``{text, rationale, sources}``."""
    content = (content or "").strip()
    content = re.sub(r"^```(?:json)?\s*", "", content, flags=re.IGNORECASE).strip()
    content = re.sub(r"\s*```$", "", content).strip()

    try:
        payload = json.loads(content)
        if not isinstance(payload, dict):
            raise ValueError("generated content is not a JSON object")
    except (json.JSONDecodeError, ValueError):
        logger.error("AI provider returned invalid JSON; storing as plain text")
        payload = {"text": content, "rationale": "", "sources": []}

    text = str(payload.get("text") or "").strip()
    rationale = str(payload.get("rationale") or "").strip()
    if not text:
        raise ValueError("AI generation returned empty text")

    generated_sources = payload.get("sources") or []
    if not isinstance(generated_sources, list):
        generated_sources = []

    provided_sources = topic.get("sources") or []
    if not isinstance(provided_sources, list):
        provided_sources = []

    # Prefer upstream supplied URLs; never invent sources.
    sources: list[str] = []
    seen: set[str] = set()
    for url in [*provided_sources, *generated_sources]:
        url = str(url).strip()
        if url and _is_valid_url(url) and url not in seen:
            seen.add(url)
            sources.append(url)

    return {"text": text, "rationale": rationale, "sources": sources}


async def _generate_with_openai(system_prompt: str, user_prompt: str) -> str:
    """Generate content via the OpenAI SDK (lazy import)."""
    from openai import AsyncOpenAI

    client = AsyncOpenAI(
        api_key=settings.openai_api_key,
        timeout=settings.request_timeout_seconds,
    )
    try:
        response = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content
        if not content:
            raise ValueError("OpenAI returned an empty response")
        return content
    finally:
        await client.close()


async def _generate_with_gemini(system_prompt: str, user_prompt: str) -> str:
    """Generate content via the Gemini SDK (google-genai, lazy import)."""
    from google import genai
    from google.genai import types as genai_types

    client = genai.Client(api_key=settings.gemini_api_key)
    try:
        response = await client.aio.models.generate_content(
            model=settings.gemini_model,
            contents=user_prompt,
            config=genai_types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
                temperature=0.7,
            ),
        )
        content = response.text
        if not content:
            raise ValueError("Gemini returned an empty response")
        return content
    finally:
        try:
            await client.aio.close()
        except Exception:
            pass  # best-effort cleanup


async def generate_post(topic: dict, persona: dict) -> dict:
    """Generate a publication for a topic under a persona.

    Returns ``{"text", "rationale", "sources"}``. Never invents URLs.
    """
    provider = _select_provider()
    if provider is None:
        raise ProviderConfigurationError(
            "No AI provider configured. Set OPENAI_API_KEY or GEMINI_API_KEY."
        )

    system_prompt = _build_system_prompt(persona)
    user_prompt = _build_user_prompt(topic)

    if provider == "openai":
        try:
            logger.info(
                "Generating post with provider=openai model=%s",
                settings.openai_model,
            )
            content = await _generate_with_openai(system_prompt, user_prompt)
            return _parse_generation(content, topic)
        except Exception as openai_error:
            logger.error("OpenAI generation failed: %s", openai_error)
            if settings.gemini_api_key:
                logger.info(
                    "Falling back to provider=gemini model=%s",
                    settings.gemini_model,
                )
                content = await _generate_with_gemini(system_prompt, user_prompt)
                return _parse_generation(content, topic)
            raise

    logger.info(
        "Generating post with provider=gemini model=%s",
        settings.gemini_model,
    )
    content = await _generate_with_gemini(system_prompt, user_prompt)
    return _parse_generation(content, topic)
