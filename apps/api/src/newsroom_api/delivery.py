"""Public media delivery preflight.

Before a dry run reports ready, and again before a publish, fetch every slide
through the public address the way Instagram's servers will, and confirm the
address exposes nothing but media. This catches the failures that otherwise
surface only as an Instagram container error: a stopped or stale tunnel, an
interstitial page instead of image bytes, an outdated file, and a tunnel that
publishes the whole API to the internet.

A pass here does not guarantee Instagram's own fetch will succeed later; it
rules out the problems that can be seen from this side.
"""

from __future__ import annotations

from typing import Any

import httpx

from .config import Settings

# Paths that must never answer 200 through the public media address.
EXPOSURE_PROBES = ("/api/health", "/docs", "/openapi.json", "/api/instagram/status")

_MAGIC_BYTES = {
    "image/jpeg": (0, b"\xff\xd8\xff"),
    "video/mp4": (4, b"ftyp"),
}
_SNIFF_BYTES = 16
_GATEWAY_HINT = (
    "Tunnel the media gateway (newsroom_api.media_gateway on port 8090) "
    "instead of the API, or put the API behind authenticated ingress."
)


async def _sniff(
    client: httpx.AsyncClient, url: str
) -> tuple[int, dict[str, str], bytes]:
    async with client.stream("GET", url) as response:
        head = b""
        if response.status_code == 200:
            async for chunk in response.aiter_bytes():
                head += chunk
                if len(head) >= _SNIFF_BYTES:
                    break
        headers = {key.lower(): value for key, value in response.headers.items()}
        return response.status_code, headers, head[:_SNIFF_BYTES]


def _media_problem(
    position: int,
    status_code: int,
    headers: dict[str, str],
    head: bytes,
    asset: dict[str, Any],
) -> str:
    label = f"Slide {position}"
    if status_code != 200:
        return (
            f"{label}: the public media URL returned HTTP {status_code}; "
            "Instagram would not be able to fetch it"
        )
    expected = str(asset.get("mime", "image/jpeg"))
    served = headers.get("content-type", "").split(";")[0].strip().lower()
    if served != expected:
        return (
            f"{label}: the public media URL serves '{served or 'no type'}' "
            f"instead of {expected}. A tunnel warning page or proxy may be "
            "in the way"
        )
    offset, magic = _MAGIC_BYTES.get(expected, (0, b""))
    if magic and head[offset : offset + len(magic)] != magic:
        return f"{label}: the public media URL does not return {expected} bytes"
    length = headers.get("content-length")
    expected_bytes = int(asset.get("bytes") or 0)
    if length and expected_bytes and length.isdigit() and int(length) != expected_bytes:
        return (
            f"{label}: the public media URL serves {length} bytes but the "
            f"reviewed file has {expected_bytes}; the address may point at "
            "another copy of the desk"
        )
    return ""


async def check_public_delivery(
    settings: Settings,
    media: list[tuple[str, dict[str, Any]]],
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> list[str]:
    """Return every reason the public media path is not safe to publish with."""
    base = settings.public_base_url.rstrip("/")
    if not base or not media:
        return []
    blockers: list[str] = []
    timeout = max(5.0, min(settings.request_timeout_seconds * 2, 20.0))
    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=False,
        transport=transport,
        headers={"User-Agent": "giani-delivery-preflight/1"},
    ) as client:
        reachable = 0
        for index, (url, asset) in enumerate(media, start=1):
            try:
                status_code, headers, head = await _sniff(client, url)
            except httpx.HTTPError as exc:
                blockers.append(
                    f"Slide {index}: the public media URL could not be "
                    f"fetched ({type(exc).__name__}). Is the tunnel running "
                    f"and is NEWSROOM_PUBLIC_BASE_URL its current address?"
                )
                continue
            reachable += 1
            problem = _media_problem(index, status_code, headers, head, asset)
            if problem:
                blockers.append(problem)

        if not reachable:
            return blockers

        try:
            invalid = await client.get(f"{base}/api/public/media/{'0' * 40}.jpg")
            if invalid.status_code == 200:
                blockers.append(
                    "The public address serves media for an invalid token. "
                    "It is not running this desk's media rules."
                )
        except httpx.HTTPError:
            pass

        for path in EXPOSURE_PROBES:
            try:
                probe = await client.get(f"{base}{path}")
            except httpx.HTTPError:
                continue
            if probe.status_code == 200:
                blockers.append(
                    f"The public address also serves {path} without "
                    f"authentication, so the whole API is exposed to the "
                    f"internet. {_GATEWAY_HINT}"
                )
                break
    return blockers
