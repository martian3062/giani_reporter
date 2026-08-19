from __future__ import annotations

import json
import re
from typing import Any

import httpx

from .config import Settings
from .editorial import (
    REQUIRED_SECTIONS,
    build_offline_draft,
    count_words,
    join_sections,
    make_cues,
    runtime_seconds,
)
from .schemas import Episode, Story


class ProviderError(RuntimeError):
    """Raised when an optional external provider cannot produce a safe result."""


def _anthropic_prompt(episode: Episode, stories: list[Story]) -> str:
    format_rules = (
        "210 to 225 words with hook, story_1, story_2, story_3, take, "
        "and sign_off sections"
        if episode.kind == "daily"
        else "900 to 1100 words with hook, what_happened, background, "
        "mechanism, who_wins_who_loses, take, and sign_off sections"
    )
    source_material = [
        {
            "title": story.title,
            "source": story.source,
            "url": story.url,
            "published_at": story.published_at,
            "summary": story.summary,
            "why_it_matters": story.why_it_matters,
            "is_demo": story.is_demo,
        }
        for story in stories
    ]
    return f"""
Write a spoken AI news episode using only the supplied source material.
The human editorial angle is: {episode.angle}
The required format is: {format_rules}.

Return one JSON object with these keys:
sections (object), title, description, hashtags (five strings),
overlays (four objects with timestamp_seconds and text).

Hard rules:
- Never add a fact, number, date, benchmark, quote, or funding amount that
  is absent from the source material.
- If a factual detail is missing, write [VERIFY] instead of guessing.
- Every spoken sentence has at most eighteen words.
- Spell numbers and acronyms as spoken.
- Do not use em dashes, parentheses, or semicolons.
- Do not use hype adjectives.
- Do not give medical, legal, financial, or political advice.
- The take must argue the supplied human angle.
- The description must include every supplied source URL.
- Output JSON only, without a markdown fence.

SOURCE MATERIAL:
{json.dumps(source_material, ensure_ascii=False)}
""".strip()


def _extract_json(text: str) -> dict[str, Any]:
    value = text.strip()
    value = re.sub(r"^```(?:json)?\s*", "", value)
    value = re.sub(r"\s*```$", "", value)
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ProviderError("Anthropic returned invalid JSON") from exc
    if not isinstance(parsed, dict):
        raise ProviderError("Anthropic returned a non-object response")
    return parsed


async def create_anthropic_draft(
    settings: Settings,
    episode: Episode,
    stories: list[Story],
) -> dict[str, Any]:
    if not settings.anthropic_api_key:
        raise ProviderError("ANTHROPIC_API_KEY is not configured")
    payload = {
        "model": settings.anthropic_model,
        "max_tokens": 5000 if episode.kind == "deep_dive" else 1800,
        "temperature": 0,
        "messages": [
            {
                "role": "user",
                "content": _anthropic_prompt(episode, stories),
            }
        ],
    }
    headers = {
        "x-api-key": settings.anthropic_api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    try:
        async with httpx.AsyncClient(
            timeout=settings.request_timeout_seconds
        ) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            body = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise ProviderError(
            f"Anthropic request failed: {type(exc).__name__}"
        ) from exc
    if not isinstance(body, dict):
        raise ProviderError("Anthropic returned an invalid response envelope")
    content = body.get("content")
    if not isinstance(content, list):
        raise ProviderError("Anthropic returned invalid content")
    text_parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            raise ProviderError("Anthropic returned an invalid content block")
        if block.get("type") != "text":
            continue
        block_text = block.get("text")
        if not isinstance(block_text, str):
            raise ProviderError("Anthropic returned non-text content")
        text_parts.append(block_text)
    text = "".join(text_parts)
    parsed = _extract_json(text)
    sections = parsed.get("sections")
    if not isinstance(sections, dict):
        raise ProviderError("Anthropic response is missing sections")
    missing = [
        key
        for key in REQUIRED_SECTIONS[episode.kind]
        if not str(sections.get(key, "")).strip()
    ]
    if missing:
        raise ProviderError(
            "Anthropic response omitted sections: " + ", ".join(missing)
        )
    clean_sections = {
        str(key): str(value).strip() for key, value in sections.items()
    }
    script = join_sections(episode.kind, clean_sections)
    offline_metadata = build_offline_draft(episode, stories)
    result = {
        **offline_metadata,
        "script": script,
        "sections": clean_sections,
        "title": str(parsed.get("title") or offline_metadata["title"]).strip(),
        "description": str(
            parsed.get("description") or offline_metadata["description"]
        ).strip(),
        "hashtags": parsed.get("hashtags") or offline_metadata["hashtags"],
        "overlays": parsed.get("overlays") or offline_metadata["overlays"],
        "word_count": count_words(script),
        "runtime_seconds": runtime_seconds(script),
    }
    result["cues"] = make_cues(result["runtime_seconds"])
    return result


async def elevenlabs_speech(
    settings: Settings,
    script: str,
) -> bytes:
    if not settings.elevenlabs_api_key or not settings.elevenlabs_voice_id:
        raise ProviderError(
            "ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID are required"
        )
    url = (
        "https://api.elevenlabs.io/v1/text-to-speech/"
        f"{settings.elevenlabs_voice_id}"
    )
    headers = {
        "xi-api-key": settings.elevenlabs_api_key,
        "accept": "audio/mpeg",
        "content-type": "application/json",
    }
    payload = {
        "text": script,
        "model_id": settings.elevenlabs_model_id,
        "voice_settings": {
            "stability": 0.55,
            "similarity_boost": 0.8,
            "style": 0.1,
            "use_speaker_boost": True,
        },
    }
    try:
        async with httpx.AsyncClient(
            timeout=max(30.0, settings.request_timeout_seconds)
        ) as client:
            response = await client.post(
                url,
                headers=headers,
                params={"output_format": "mp3_44100_192"},
                json=payload,
            )
            response.raise_for_status()
            if not response.content:
                raise ProviderError("ElevenLabs returned an empty audio file")
            return response.content
    except httpx.HTTPError as exc:
        raise ProviderError(
            f"ElevenLabs request failed: {type(exc).__name__}"
        ) from exc
