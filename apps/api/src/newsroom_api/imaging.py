"""Prompt to Instagram-ready image bytes.

Two responsibilities live here and nothing else:

1. ``generate_image`` calls whichever image provider is configured and returns
   raw bytes plus the provider that produced them.
2. ``normalize_for_instagram`` turns those bytes into a JPEG whose pixel size
   and aspect ratio Instagram will accept without re-cropping.

Every provider is optional. When no key is configured the offline provider
draws a visibly stamped placeholder so the rest of the pipeline can be
rehearsed. Placeholders carry ``is_demo`` and are refused at the publish gate.
"""

from __future__ import annotations

import base64
import io
import textwrap
from dataclasses import dataclass
from typing import Any

import httpx

from .config import Settings


class ImageError(RuntimeError):
    """Raised when an image cannot be generated or normalized safely."""


# Instagram accepts feed images between 4:5 (0.8) and 1.91:1. Stories and
# reels are 9:16. These targets are the sizes Instagram itself serves, so the
# platform never has to re-encode what we upload.
FORMAT_SPECS: dict[str, dict[str, Any]] = {
    "feed_square": {
        "size": (1080, 1080),
        "aspect": "1:1",
        "label": "Feed square 1:1",
        "max_assets": 1,
    },
    "feed_portrait": {
        "size": (1080, 1350),
        "aspect": "4:5",
        "label": "Feed portrait 4:5",
        "max_assets": 1,
    },
    "feed_landscape": {
        "size": (1080, 566),
        "aspect": "1.91:1",
        "label": "Feed landscape 1.91:1",
        "max_assets": 1,
    },
    "carousel": {
        "size": (1080, 1350),
        "aspect": "4:5",
        "label": "Carousel 4:5",
        "max_assets": 10,
    },
    "story": {
        "size": (1080, 1920),
        "aspect": "9:16",
        "label": "Story 9:16",
        "max_assets": 1,
    },
    "reel": {
        "size": (1080, 1920),
        "aspect": "9:16",
        "label": "Reel 9:16",
        "max_assets": 1,
    },
}

# Provider-side aspect hints. Providers only accept a fixed menu, so we ask for
# the closest ratio and let Pillow do the exact crop afterwards.
_IMAGEN_ASPECTS = {"1:1": "1:1", "4:5": "3:4", "1.91:1": "16:9", "9:16": "9:16"}
_OPENAI_SIZES = {
    "1:1": "1024x1024",
    "4:5": "1024x1536",
    "1.91:1": "1536x1024",
    "9:16": "1024x1536",
}
_STABILITY_ASPECTS = {
    "1:1": "1:1",
    "4:5": "4:5",
    "1.91:1": "16:9",
    "9:16": "9:16",
}

MAX_UPLOAD_BYTES = 8 * 1024 * 1024


@dataclass(slots=True)
class GeneratedImage:
    data: bytes
    provider: str
    mime: str
    is_demo: bool


def format_spec(post_format: str) -> dict[str, Any]:
    spec = FORMAT_SPECS.get(post_format)
    if spec is None:
        raise ImageError(f"unsupported post format '{post_format}'")
    return spec


def _pillow():
    try:
        from PIL import Image, ImageDraw, ImageFont  # noqa: PLC0415

        return Image, ImageDraw, ImageFont
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise ImageError(
            "Pillow is required for image normalization. "
            "Run 'uv sync' in apps/api to install it."
        ) from exc


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------


async def _gemini_image(
    settings: Settings,
    prompt: str,
    aspect: str,
    reference: bytes | None,
    reference_mime: str,
) -> GeneratedImage:
    if not settings.google_api_key:
        raise ImageError("GOOGLE_API_KEY is not configured")
    parts: list[dict[str, Any]] = []
    if reference:
        parts.append(
            {
                "inline_data": {
                    "mime_type": reference_mime or "image/png",
                    "data": base64.b64encode(reference).decode("ascii"),
                }
            }
        )
    parts.append({"text": prompt})
    payload = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {
            "responseModalities": ["IMAGE"],
            "imageConfig": {"aspectRatio": aspect},
        },
    }
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.gemini_image_model}:generateContent"
    )
    body = await _post_json(
        settings,
        url,
        payload,
        headers={"x-goog-api-key": settings.google_api_key},
        provider="Gemini",
    )
    candidates = body.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise ImageError(_refusal_message("Gemini", body))
    for candidate in candidates:
        content = (candidate or {}).get("content") or {}
        for part in content.get("parts") or []:
            inline = part.get("inlineData") or part.get("inline_data")
            if not isinstance(inline, dict):
                continue
            data = inline.get("data")
            if not isinstance(data, str):
                continue
            try:
                raw = base64.b64decode(data, validate=True)
            except (ValueError, TypeError) as exc:
                raise ImageError("Gemini returned undecodable image data") from exc
            return GeneratedImage(
                data=raw,
                provider="gemini",
                mime=str(inline.get("mimeType") or "image/png"),
                is_demo=False,
            )
    raise ImageError(_refusal_message("Gemini", body))


async def _imagen_image(
    settings: Settings, prompt: str, aspect: str
) -> GeneratedImage:
    if not settings.google_api_key:
        raise ImageError("GOOGLE_API_KEY is not configured")
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.imagen_model}:predict"
    )
    payload = {
        "instances": [{"prompt": prompt}],
        "parameters": {
            "sampleCount": 1,
            "aspectRatio": _IMAGEN_ASPECTS.get(aspect, "1:1"),
            "personGeneration": "allow_adult",
        },
    }
    body = await _post_json(
        settings,
        url,
        payload,
        headers={"x-goog-api-key": settings.google_api_key},
        provider="Imagen",
    )
    predictions = body.get("predictions")
    if not isinstance(predictions, list) or not predictions:
        raise ImageError(_refusal_message("Imagen", body))
    encoded = (predictions[0] or {}).get("bytesBase64Encoded")
    if not isinstance(encoded, str):
        raise ImageError("Imagen returned no image bytes")
    return GeneratedImage(
        data=base64.b64decode(encoded),
        provider="imagen",
        mime=str((predictions[0] or {}).get("mimeType") or "image/png"),
        is_demo=False,
    )


async def _openai_image(
    settings: Settings, prompt: str, aspect: str
) -> GeneratedImage:
    if not settings.openai_api_key:
        raise ImageError("OPENAI_API_KEY is not configured")
    payload = {
        "model": settings.openai_image_model,
        "prompt": prompt,
        "n": 1,
        "size": _OPENAI_SIZES.get(aspect, "1024x1024"),
    }
    body = await _post_json(
        settings,
        "https://api.openai.com/v1/images/generations",
        payload,
        headers={"Authorization": f"Bearer {settings.openai_api_key}"},
        provider="OpenAI",
    )
    data = body.get("data")
    if not isinstance(data, list) or not data:
        raise ImageError(_refusal_message("OpenAI", body))
    encoded = (data[0] or {}).get("b64_json")
    if not isinstance(encoded, str):
        raise ImageError("OpenAI returned no inline image bytes")
    return GeneratedImage(
        data=base64.b64decode(encoded),
        provider="openai",
        mime="image/png",
        is_demo=False,
    )


async def _stability_image(
    settings: Settings, prompt: str, aspect: str
) -> GeneratedImage:
    if not settings.stability_api_key:
        raise ImageError("STABILITY_API_KEY is not configured")
    try:
        async with httpx.AsyncClient(
            timeout=settings.image_timeout_seconds
        ) as client:
            response = await client.post(
                "https://api.stability.ai/v2beta/stable-image/generate/core",
                headers={
                    "Authorization": f"Bearer {settings.stability_api_key}",
                    "Accept": "image/*",
                },
                files={"none": ("", "")},
                data={
                    "prompt": prompt,
                    "aspect_ratio": _STABILITY_ASPECTS.get(aspect, "1:1"),
                    "output_format": "png",
                },
            )
            response.raise_for_status()
            if not response.content:
                raise ImageError("Stability returned an empty image")
            return GeneratedImage(
                data=response.content,
                provider="stability",
                mime=response.headers.get("content-type", "image/png"),
                is_demo=False,
            )
    except httpx.HTTPStatusError as exc:
        raise ImageError(
            f"Stability request failed with {exc.response.status_code}"
        ) from exc
    except httpx.HTTPError as exc:
        raise ImageError(
            f"Stability request failed: {type(exc).__name__}"
        ) from exc


async def _replicate_image(
    settings: Settings, prompt: str, aspect: str
) -> GeneratedImage:
    if not settings.replicate_api_token:
        raise ImageError("REPLICATE_API_TOKEN is not configured")
    model = settings.replicate_model.strip("/")
    url = f"https://api.replicate.com/v1/models/{model}/predictions"
    payload = {
        "input": {
            "prompt": prompt,
            "aspect_ratio": aspect if aspect != "1.91:1" else "16:9",
            "output_format": "png",
        }
    }
    body = await _post_json(
        settings,
        url,
        payload,
        headers={
            "Authorization": f"Bearer {settings.replicate_api_token}",
            "Prefer": "wait",
        },
        provider="Replicate",
    )
    output = body.get("output")
    image_url = ""
    if isinstance(output, str):
        image_url = output
    elif isinstance(output, list) and output and isinstance(output[0], str):
        image_url = output[0]
    if not image_url:
        raise ImageError(_refusal_message("Replicate", body))
    try:
        async with httpx.AsyncClient(
            timeout=settings.image_timeout_seconds
        ) as client:
            download = await client.get(image_url)
            download.raise_for_status()
            return GeneratedImage(
                data=download.content,
                provider="replicate",
                mime=download.headers.get("content-type", "image/png"),
                is_demo=False,
            )
    except httpx.HTTPError as exc:
        raise ImageError(
            f"Replicate output download failed: {type(exc).__name__}"
        ) from exc


def _offline_image(
    prompt: str, headline: str, size: tuple[int, int]
) -> GeneratedImage:
    """Draw a visibly non-publishable placeholder.

    This never pretends to be a generated photograph. It renders the prompt at
    a legible size so the operator can verify layout, ratio, and the review
    path, and it is blocked at the publish gate by ``is_demo``.
    """
    Image, ImageDraw, ImageFont = _pillow()
    width, height = size
    canvas = Image.new("RGB", size, (12, 16, 26))
    draw = ImageDraw.Draw(canvas)

    def font_at(pixels: int):
        try:
            return ImageFont.load_default(size=pixels)
        except TypeError:  # Pillow older than 10.1 has a fixed bitmap font
            return ImageFont.load_default()

    scale = width / 1080
    label_font = font_at(round(26 * scale))
    title_font = font_at(round(52 * scale))
    body_font = font_at(round(24 * scale))

    bar = max(10, round(height / 80))
    draw.rectangle([(0, 0), (width, bar)], fill=(255, 92, 51))
    draw.rectangle([(0, height - bar), (width, height)], fill=(255, 92, 51))

    margin = round(width / 11)
    wrap_at = max(20, round((width - margin * 2) / (24 * scale * 0.55)))
    title_lines = textwrap.wrap(headline or "Untitled post", width=32)[:3]
    prompt_lines = textwrap.wrap(prompt, width=wrap_at)[:12]

    line_heights = [
        round(38 * scale),
        round(34 * scale),
        round(30 * scale),
        len(title_lines) * round(62 * scale),
        round(30 * scale),
        round(44 * scale),
        len(prompt_lines) * round(34 * scale),
    ]
    cursor = max(bar * 3, (height - sum(line_heights)) // 2)

    draw.text(
        (margin, cursor), "DEMO PLACEHOLDER", font=label_font, fill=(255, 92, 51)
    )
    cursor += round(38 * scale)
    draw.text(
        (margin, cursor),
        "No image model was configured.",
        font=body_font,
        fill=(160, 170, 190),
    )
    cursor += round(34 * scale)
    draw.text(
        (margin, cursor),
        "This file can never be published.",
        font=body_font,
        fill=(160, 170, 190),
    )
    cursor += round(60 * scale)

    for line in title_lines:
        draw.text((margin, cursor), line, font=title_font, fill=(240, 244, 252))
        cursor += round(62 * scale)

    cursor += round(30 * scale)
    draw.text((margin, cursor), "PROMPT", font=label_font, fill=(120, 132, 156))
    cursor += round(44 * scale)
    for line in prompt_lines:
        draw.text((margin, cursor), line, font=body_font, fill=(190, 200, 218))
        cursor += round(34 * scale)

    buffer = io.BytesIO()
    canvas.save(buffer, format="PNG")
    return GeneratedImage(
        data=buffer.getvalue(),
        provider="offline",
        mime="image/png",
        is_demo=True,
    )


async def _post_json(
    settings: Settings,
    url: str,
    payload: dict[str, Any],
    *,
    headers: dict[str, str],
    provider: str,
) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(
            timeout=settings.image_timeout_seconds
        ) as client:
            response = await client.post(
                url,
                headers={"content-type": "application/json", **headers},
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
        raise ImageError(
            f"{provider} request failed with "
            f"{exc.response.status_code}: {detail}"
        ) from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise ImageError(
            f"{provider} request failed: {type(exc).__name__}"
        ) from exc
    if not isinstance(body, dict):
        raise ImageError(f"{provider} returned an invalid response envelope")
    return body


def _refusal_message(provider: str, body: dict[str, Any]) -> str:
    """Surface a provider safety refusal as an actionable message."""
    for key in ("promptFeedback", "error", "detail"):
        value = body.get(key)
        if value:
            return f"{provider} returned no image: {str(value)[:300]}"
    candidates = body.get("candidates")
    if isinstance(candidates, list) and candidates:
        reason = (candidates[0] or {}).get("finishReason")
        if reason and reason != "STOP":
            return f"{provider} stopped early ({reason}); try a milder prompt"
    return f"{provider} returned no image for this prompt"


async def generate_image(
    settings: Settings,
    *,
    prompt: str,
    post_format: str,
    headline: str = "",
    provider: str | None = None,
    reference: bytes | None = None,
    reference_mime: str = "image/png",
) -> GeneratedImage:
    """Generate one image with the requested or best-configured provider."""
    spec = format_spec(post_format)
    aspect = str(spec["aspect"])
    choice = settings.resolve_image_provider(provider)

    if choice == "offline":
        return _offline_image(prompt, headline, tuple(spec["size"]))
    if choice == "gemini":
        return await _gemini_image(
            settings, prompt, aspect, reference, reference_mime
        )
    if choice == "imagen":
        return await _imagen_image(settings, prompt, aspect)
    if choice == "openai":
        return await _openai_image(settings, prompt, aspect)
    if choice == "stability":
        return await _stability_image(settings, prompt, aspect)
    if choice == "replicate":
        return await _replicate_image(settings, prompt, aspect)
    raise ImageError(
        f"unknown image provider '{choice}'. Configured providers: "
        + ", ".join(settings.configured_image_providers())
    )


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------


def normalize_for_instagram(
    data: bytes, post_format: str
) -> tuple[bytes, int, int]:
    """Cover-crop to the exact target box and encode a publishable JPEG."""
    Image, _, _ = _pillow()
    spec = format_spec(post_format)
    target_width, target_height = spec["size"]

    try:
        source = Image.open(io.BytesIO(data))
        source.load()
    except Exception as exc:  # Pillow raises a wide range of decode errors
        raise ImageError(f"generated file is not a readable image: {exc}") from exc

    if source.mode not in ("RGB", "L"):
        source = source.convert("RGB")
    elif source.mode == "L":
        source = source.convert("RGB")

    source_ratio = source.width / source.height
    target_ratio = target_width / target_height
    if source_ratio > target_ratio:
        crop_width = round(source.height * target_ratio)
        left = (source.width - crop_width) // 2
        source = source.crop((left, 0, left + crop_width, source.height))
    elif source_ratio < target_ratio:
        crop_height = round(source.width / target_ratio)
        top = (source.height - crop_height) // 2
        source = source.crop((0, top, source.width, top + crop_height))

    resized = source.resize(
        (target_width, target_height), Image.LANCZOS
    )

    for quality in (92, 86, 78, 70, 62):
        buffer = io.BytesIO()
        resized.save(
            buffer, format="JPEG", quality=quality, optimize=True, subsampling=1
        )
        encoded = buffer.getvalue()
        if len(encoded) <= MAX_UPLOAD_BYTES:
            return encoded, target_width, target_height
    raise ImageError(
        "image could not be compressed below the eight megabyte upload limit"
    )
