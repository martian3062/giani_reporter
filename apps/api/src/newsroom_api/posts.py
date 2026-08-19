"""Turn one plain prompt into a reviewable Instagram post plan.

The plan is everything a human needs to judge before anything is generated or
published: the headline, the image prompt for each slide, the caption, the
hashtags, and the alt text. Anthropic or OpenAI writes it when a key is
configured, preferring Anthropic when both are present; otherwise a
deterministic offline builder produces the same shape so the review and
publish path stays testable without any provider.
"""

from __future__ import annotations

import re
from typing import Any

import httpx

from .config import Settings
from .editorial import contains_advice, contains_credential_framing
from .imaging import FORMAT_SPECS, format_spec
from .providers import ProviderError, _extract_json


CAPTION_MAX = 2_200
ALT_TEXT_MAX = 1_000
HASHTAG_MAX = 30

AI_DISCLOSURE = "Visual generated with AI. Reviewed by a human before posting."

POST_CHECKS: tuple[str, ...] = (
    "prompt_present",
    "caption_length",
    "hashtag_count",
    "alt_text_present",
    "ai_disclosure",
    "advice_safe",
    "neutral_anchor",
    "asset_count",
    "assets_current",
    "no_demo_assets",
    "human_reviewed",
)

CHECK_LABELS: dict[str, str] = {
    "prompt_present": "A human prompt is on record",
    "caption_length": "Caption is within Instagram's 2,200 characters",
    "hashtag_count": "Thirty hashtags or fewer, each well formed",
    "alt_text_present": "Alt text is written for screen readers",
    "ai_disclosure": "Caption discloses AI-generated visuals",
    "advice_safe": "No medical, legal, financial, or political advice",
    "neutral_anchor": "No credential or expert framing",
    "asset_count": "Slide count matches the chosen format",
    "assets_current": "Every slide matches the current revision",
    "no_demo_assets": "No demo placeholder is attached",
    "human_reviewed": "A human approved this exact revision",
}

_HASHTAG_RE = re.compile(r"^#[A-Za-z0-9_]{1,138}$")
_STOPWORDS = {
    "a", "an", "and", "the", "of", "for", "with", "about", "into", "make",
    "create", "generate", "post", "image", "picture", "photo", "pic", "that",
    "this", "some", "please", "instagram", "reel", "story", "carousel",
}


def default_checks() -> dict[str, bool]:
    return {check: False for check in POST_CHECKS}


def slide_count(post_format: str, requested: int | None = None) -> int:
    spec = format_spec(post_format)
    maximum = int(spec["max_assets"])
    if maximum == 1:
        return 1
    if requested is None:
        return 3
    return max(2, min(maximum, requested))


def keywords(prompt: str, limit: int = 8) -> list[str]:
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9'-]*", prompt)
    seen: list[str] = []
    for word in words:
        lowered = word.lower()
        if lowered in _STOPWORDS or len(lowered) < 3:
            continue
        if lowered not in {item.lower() for item in seen}:
            seen.append(word)
        if len(seen) >= limit:
            break
    return seen


def _headline(prompt: str) -> str:
    clean = re.sub(r"\s+", " ", prompt).strip().rstrip(".")
    if not clean:
        return "Untitled post"
    if len(clean) <= 70:
        return clean[0].upper() + clean[1:]
    trimmed = clean[:69].rsplit(" ", 1)[0]
    return (trimmed[0].upper() + trimmed[1:]).rstrip(",;:") + "…"


def _hashtags_from(prompt: str) -> list[str]:
    tags = ["#AI", "#AINews", "#Technology"]
    for word in keywords(prompt, limit=6):
        candidate = "#" + re.sub(r"[^A-Za-z0-9]", "", word)
        if len(candidate) > 2 and candidate not in tags:
            tags.append(candidate)
        if len(tags) >= 8:
            break
    return tags[:8]


def build_offline_plan(
    prompt: str,
    post_format: str,
    slides: int,
) -> dict[str, Any]:
    """Deterministic plan used when no drafting provider is configured."""
    spec = format_spec(post_format)
    headline = _headline(prompt)
    topic = ", ".join(keywords(prompt, limit=6)) or headline

    style = (
        "editorial photograph, natural light, shallow depth of field, "
        "muted colour grade, no on-image text, no logos, no watermark, "
        "clean negative space for a caption overlay"
    )
    image_prompts: list[str] = []
    angles = [
        "wide establishing composition",
        "close detail composition",
        "human scale composition with a person out of focus",
        "abstract graphic composition",
        "overhead flat composition",
        "low angle composition",
        "side profile composition",
        "environmental context composition",
        "macro texture composition",
        "silhouette against light composition",
    ]
    for index in range(slides):
        angle = angles[index % len(angles)]
        image_prompts.append(
            f"{prompt.strip()}. {angle}, {spec['aspect']} aspect ratio, {style}."
        )

    caption_lines = [
        headline + ".",
        "",
        f"Working notes on {topic}.",
        "Full context and sources are in the comments.",
        "",
        AI_DISCLOSURE,
    ]
    return {
        "headline": headline,
        "image_prompts": image_prompts,
        "caption": "\n".join(caption_lines),
        "hashtags": _hashtags_from(prompt),
        "alt_text": (
            f"{headline}. Generated {spec['label']} illustration created for "
            "this post."
        ),
        "ai_disclosure": AI_DISCLOSURE,
    }


def _direction_prompt(prompt: str, post_format: str, slides: int) -> str:
    spec = format_spec(post_format)
    slide_rule = (
        f"Return exactly {slides} image prompts, one per carousel slide, "
        "each a different composition of the same idea."
        if slides > 1
        else "Return exactly one image prompt."
    )
    return f"""
You are the art director and caption writer for an Instagram account.
Turn the operator's brief into one publishable post plan.

OPERATOR BRIEF:
{prompt}

FORMAT: {spec['label']} at {spec['aspect']}.
{slide_rule}

Return one JSON object with exactly these keys:
headline (string, under seventy characters),
image_prompts (array of strings),
caption (string),
hashtags (array of three to fifteen strings, each starting with #),
alt_text (string, under two hundred characters, written for screen readers).

Hard rules:
- Each image prompt must be a self-contained visual description: subject,
  composition, lighting, lens, colour, and mood. State the {spec['aspect']}
  aspect ratio.
- Ask for no text, letters, logos, or watermarks inside the image. Rendered
  text is where image models fail most visibly.
- Do not describe a real, named, identifiable living person, and do not
  imitate a real brand's logo or trade dress.
- Never invent a statistic, benchmark, funding amount, date, or quote that is
  absent from the brief. Write [VERIFY] instead of guessing.
- Do not give medical, legal, financial, or political advice.
- Do not claim any credential for the account.
- The caption must be under two thousand characters and must end with this
  exact line: {AI_DISCLOSURE}
- Output JSON only, with no markdown fence.
""".strip()


def _finish_plan(
    parsed: dict[str, Any],
    prompt: str,
    post_format: str,
    slides: int,
    *,
    provider_label: str,
) -> dict[str, Any]:
    """Validate a provider's parsed JSON and backfill from the offline plan."""
    fallback = build_offline_plan(prompt, post_format, slides)

    raw_prompts = parsed.get("image_prompts")
    image_prompts = [
        str(item).strip()
        for item in (raw_prompts if isinstance(raw_prompts, list) else [])
        if str(item).strip()
    ]
    if not image_prompts:
        raise ProviderError(f"{provider_label} returned no image prompts")
    if len(image_prompts) < slides:
        image_prompts.extend(
            fallback["image_prompts"][len(image_prompts) : slides]
        )
    image_prompts = image_prompts[:slides]

    raw_tags = parsed.get("hashtags")
    hashtags = [
        str(tag).strip()
        for tag in (raw_tags if isinstance(raw_tags, list) else [])
        if str(tag).strip().startswith("#")
    ]

    caption = str(parsed.get("caption") or fallback["caption"]).strip()
    if AI_DISCLOSURE not in caption:
        caption = f"{caption}\n\n{AI_DISCLOSURE}"

    return {
        "headline": str(parsed.get("headline") or fallback["headline"]).strip()[
            :120
        ],
        "image_prompts": image_prompts,
        "caption": caption[:CAPTION_MAX],
        "hashtags": (hashtags or fallback["hashtags"])[:HASHTAG_MAX],
        "alt_text": str(
            parsed.get("alt_text") or fallback["alt_text"]
        ).strip()[:ALT_TEXT_MAX],
        "ai_disclosure": AI_DISCLOSURE,
    }


async def create_anthropic_plan(
    settings: Settings,
    prompt: str,
    post_format: str,
    slides: int,
) -> dict[str, Any]:
    if not settings.anthropic_api_key:
        raise ProviderError("ANTHROPIC_API_KEY is not configured")
    payload = {
        "model": settings.anthropic_model,
        "max_tokens": 2000,
        "temperature": 0.4,
        "messages": [
            {
                "role": "user",
                "content": _direction_prompt(prompt, post_format, slides),
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
            timeout=max(60.0, settings.request_timeout_seconds)
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
    if not isinstance(body, dict) or not isinstance(body.get("content"), list):
        raise ProviderError("Anthropic returned an invalid response envelope")
    text = "".join(
        str(block.get("text", ""))
        for block in body["content"]
        if isinstance(block, dict) and block.get("type") == "text"
    )
    parsed = _extract_json(text)
    return _finish_plan(
        parsed, prompt, post_format, slides, provider_label="Anthropic"
    )


async def create_openai_plan(
    settings: Settings,
    prompt: str,
    post_format: str,
    slides: int,
) -> dict[str, Any]:
    if not settings.openai_api_key:
        raise ProviderError("OPENAI_API_KEY is not configured")
    payload = {
        # Some model families (the reasoning line, and evidently this
        # account's chat models too) reject any non-default temperature.
        # Omitting it entirely keeps this call portable across both.
        "model": settings.openai_text_model,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "user",
                "content": _direction_prompt(prompt, post_format, slides),
            }
        ],
    }
    headers = {"Authorization": f"Bearer {settings.openai_api_key}"}
    try:
        async with httpx.AsyncClient(
            timeout=max(60.0, settings.request_timeout_seconds)
        ) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            body = response.json()
    except httpx.HTTPStatusError as exc:
        detail = ""
        try:
            detail = str(exc.response.json())[:300]
        except ValueError:
            detail = exc.response.text[:300]
        raise ProviderError(
            f"OpenAI request failed with {exc.response.status_code}: {detail}"
        ) from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise ProviderError(
            f"OpenAI request failed: {type(exc).__name__}"
        ) from exc
    choices = body.get("choices") if isinstance(body, dict) else None
    if not isinstance(choices, list) or not choices:
        raise ProviderError("OpenAI returned no choices")
    message = (choices[0] or {}).get("message") or {}
    text = str(message.get("content") or "")
    parsed = _extract_json(text)
    return _finish_plan(
        parsed, prompt, post_format, slides, provider_label="OpenAI"
    )


_DIRECTION_PROVIDERS: dict[str, Any] = {
    "anthropic": create_anthropic_plan,
    "openai": create_openai_plan,
}


async def create_plan(
    settings: Settings,
    prompt: str,
    post_format: str,
    slides: int,
    *,
    provider: str,
) -> tuple[dict[str, Any], str]:
    """Resolve the requested or best-available direction provider.

    An explicit ``provider`` (``anthropic`` or ``openai``) raises
    ``ProviderError`` when its key is missing or the call fails — the caller
    asked for that engine specifically. ``auto`` tries Anthropic then OpenAI,
    whichever has a key, and always falls through to the offline writer
    rather than raising.
    """
    choice = (provider or "auto").strip().lower()
    if choice in _DIRECTION_PROVIDERS:
        configured = {
            "anthropic": settings.anthropic_api_key,
            "openai": settings.openai_api_key,
        }[choice]
        if not configured:
            raise ProviderError(
                f"{'ANTHROPIC_API_KEY' if choice == 'anthropic' else 'OPENAI_API_KEY'} "
                "is not configured"
            )
        plan = await _DIRECTION_PROVIDERS[choice](
            settings, prompt, post_format, slides
        )
        return plan, choice

    tiers = [
        name
        for name in ("anthropic", "openai")
        if {
            "anthropic": settings.anthropic_api_key,
            "openai": settings.openai_api_key,
        }[name]
    ]
    for name in tiers:
        try:
            plan = await _DIRECTION_PROVIDERS[name](
                settings, prompt, post_format, slides
            )
            return plan, name
        except ProviderError:
            continue
    label = "offline-fallback" if tiers else "offline"
    return build_offline_plan(prompt, post_format, slides), label


def full_caption(caption: str, hashtags: list[str]) -> str:
    """The exact string sent to Instagram: caption body then hashtag block."""
    body = caption.strip()
    tags = " ".join(tag.strip() for tag in hashtags if tag.strip())
    if not tags:
        return body
    return f"{body}\n\n{tags}".strip()


def calculate_checks(
    post: dict[str, Any],
    assets: list[dict[str, Any]],
    previous: dict[str, bool] | None = None,
) -> dict[str, bool]:
    """Recompute every automatic gate; manual gates only ever get revoked."""
    prior = {**default_checks(), **(previous or {})}
    caption = str(post.get("caption", ""))
    hashtags = list(post.get("hashtags") or [])
    post_format = str(post.get("format", "feed_square"))
    revision = int(post.get("revision", 1))
    expected = slide_count(post_format, len(assets) if assets else None)
    spec = FORMAT_SPECS.get(post_format, FORMAT_SPECS["feed_square"])
    maximum = int(spec["max_assets"])
    combined = full_caption(caption, hashtags)

    automatic = {
        "prompt_present": bool(str(post.get("prompt", "")).strip()),
        "caption_length": 0 < len(combined) <= CAPTION_MAX,
        "hashtag_count": len(hashtags) <= HASHTAG_MAX
        and all(_HASHTAG_RE.match(tag) for tag in hashtags)
        and len(hashtags) == len(set(hashtags)),
        "alt_text_present": 0
        < len(str(post.get("alt_text", "")).strip())
        <= ALT_TEXT_MAX,
        "ai_disclosure": AI_DISCLOSURE in caption,
        "advice_safe": not contains_advice(combined),
        "neutral_anchor": not contains_credential_framing(combined),
        "asset_count": bool(assets)
        and (
            len(assets) == expected
            if maximum == 1
            else 2 <= len(assets) <= maximum
        ),
        "assets_current": bool(assets)
        and all(
            int(asset.get("post_revision", 0)) == revision for asset in assets
        ),
        "no_demo_assets": bool(assets)
        and not any(bool(asset.get("is_demo")) for asset in assets),
    }

    checks = prior.copy()
    for gate, passed in automatic.items():
        checks[gate] = passed
    if not all(automatic.values()):
        checks["human_reviewed"] = False
    if int(post.get("approved_revision", 0)) != revision:
        checks["human_reviewed"] = False
    return {check: bool(checks.get(check, False)) for check in POST_CHECKS}


def approval_errors(
    post: dict[str, Any], assets: list[dict[str, Any]]
) -> list[str]:
    """Human-readable reasons a post cannot be approved yet."""
    errors: list[str] = []
    checks = calculate_checks(post, assets, post.get("checks"))
    for gate, passed in checks.items():
        if gate == "human_reviewed":
            continue
        if not passed:
            errors.append(CHECK_LABELS[gate])
    if "[verify]" in str(post.get("caption", "")).lower():
        errors.append("Remove every [VERIFY] marker from the caption")
    return errors


def publish_blockers(
    post: dict[str, Any],
    assets: list[dict[str, Any]],
    settings: Settings,
) -> list[str]:
    """Every reason this post must not reach Instagram right now."""
    blockers: list[str] = []
    status = str(post.get("status", ""))
    if status == "published":
        blockers.append(
            "This post is already live on Instagram. Create a new post "
            "instead of publishing it again."
        )
    elif status == "publishing":
        blockers.append("A publish attempt for this post is already running")
    elif status != "approved":
        blockers.append("Approve the post before publishing")
    approved_revision = int(post.get("approved_revision", 0))
    if approved_revision and approved_revision != int(post.get("revision", 1)):
        blockers.append(
            "The post changed after approval; approve the current revision"
        )
    checks = post.get("checks") or {}
    failed = [
        CHECK_LABELS[gate]
        for gate in POST_CHECKS
        if not bool(checks.get(gate, False))
    ]
    blockers.extend(failed)
    if not settings.instagram_publish_enabled:
        blockers.append(
            "Publishing is disabled. Set INSTAGRAM_PUBLISH_ENABLED=true"
        )
    if not settings.instagram_configured:
        blockers.append(
            "Set INSTAGRAM_USER_ID and INSTAGRAM_ACCESS_TOKEN "
            "(META_ACCESS_TOKEN is also read)"
        )
    if any(bool(asset.get("is_demo")) for asset in assets):
        blockers.append("A demo placeholder can never be published")
    return blockers
