"""Give a rendered asset a public HTTPS URL.

Instagram's Content Publishing API never accepts uploaded bytes. It fetches
``image_url`` / ``video_url`` from its own servers, so anything published has
to be reachable from the public internet first. Two hosting modes cover that:

``local``
    Serve the file straight from this API at ``NEWSROOM_PUBLIC_BASE_URL``
    behind an unguessable per-asset token. Needs a tunnel (Cloudflare Tunnel,
    ngrok) or a real deployment. Nothing else to configure.

``s3``
    PUT the file into any S3-compatible bucket (Cloudflare R2, Backblaze B2,
    MinIO, AWS S3) and hand Instagram the bucket's public URL. Signing is
    SigV4, implemented here so the service keeps its dependency surface small.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
from pathlib import Path
from urllib.parse import quote, urlsplit

import httpx

from .config import Settings


class MediaHostError(RuntimeError):
    """Raised when an asset cannot be given a public URL."""


def _sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sign(key: bytes, message: str) -> bytes:
    return hmac.new(key, message.encode("utf-8"), hashlib.sha256).digest()


def _sigv4_headers(
    settings: Settings,
    *,
    method: str,
    url: str,
    payload: bytes,
    content_type: str,
    now: dt.datetime,
) -> dict[str, str]:
    parts = urlsplit(url)
    host = parts.netloc
    canonical_uri = quote(parts.path, safe="/~")
    canonical_query = parts.query
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")
    payload_hash = _sha256_hex(payload)

    headers = {
        "content-type": content_type,
        "host": host,
        "x-amz-content-sha256": payload_hash,
        "x-amz-date": amz_date,
    }
    signed_headers = ";".join(sorted(headers))
    canonical_headers = "".join(
        f"{name}:{headers[name].strip()}\n" for name in sorted(headers)
    )
    canonical_request = "\n".join(
        [
            method,
            canonical_uri,
            canonical_query,
            canonical_headers,
            signed_headers,
            payload_hash,
        ]
    )

    region = settings.s3_region or "auto"
    scope = f"{date_stamp}/{region}/s3/aws4_request"
    string_to_sign = "\n".join(
        [
            "AWS4-HMAC-SHA256",
            amz_date,
            scope,
            _sha256_hex(canonical_request.encode("utf-8")),
        ]
    )

    signing_key = _sign(
        f"AWS4{settings.s3_secret_access_key}".encode("utf-8"), date_stamp
    )
    signing_key = _sign(signing_key, region)
    signing_key = _sign(signing_key, "s3")
    signing_key = _sign(signing_key, "aws4_request")
    signature = hmac.new(
        signing_key, string_to_sign.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    authorization = (
        "AWS4-HMAC-SHA256 "
        f"Credential={settings.s3_access_key_id}/{scope}, "
        f"SignedHeaders={signed_headers}, "
        f"Signature={signature}"
    )
    return {**headers, "authorization": authorization}


async def _upload_to_s3(
    settings: Settings, path: Path, key: str, content_type: str
) -> str:
    if not settings.s3_configured:
        raise MediaHostError(
            "S3 media hosting needs S3_ENDPOINT_URL, S3_BUCKET, "
            "S3_ACCESS_KEY_ID, S3_SECRET_ACCESS_KEY, and S3_PUBLIC_BASE_URL"
        )
    payload = path.read_bytes()
    object_key = f"{settings.s3_key_prefix.strip('/')}/{key}".strip("/")
    url = f"{settings.s3_endpoint_url}/{settings.s3_bucket}/{object_key}"
    headers = _sigv4_headers(
        settings,
        method="PUT",
        url=url,
        payload=payload,
        content_type=content_type,
        now=dt.datetime.now(dt.timezone.utc),
    )
    try:
        async with httpx.AsyncClient(
            timeout=max(60.0, settings.request_timeout_seconds)
        ) as client:
            response = await client.put(url, headers=headers, content=payload)
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise MediaHostError(
            f"object storage upload failed with {exc.response.status_code}: "
            f"{exc.response.text[:200]}"
        ) from exc
    except httpx.HTTPError as exc:
        raise MediaHostError(
            f"object storage upload failed: {type(exc).__name__}"
        ) from exc
    return f"{settings.s3_public_base_url}/{object_key}"


def local_public_url(settings: Settings, token: str, extension: str) -> str:
    if not settings.public_base_url:
        raise MediaHostError(
            "NEWSROOM_PUBLIC_BASE_URL is not set. Instagram fetches media from "
            "its own servers, so the API needs a public HTTPS address "
            "(Cloudflare Tunnel, ngrok, or a real deployment)."
        )
    return f"{settings.public_base_url}/api/public/media/{token}.{extension}"


async def publish_media_url(
    settings: Settings,
    *,
    path: Path,
    token: str,
    extension: str,
    content_type: str,
) -> str:
    """Return a public URL Instagram can fetch, uploading first if needed."""
    if settings.media_host == "s3":
        return await _upload_to_s3(
            settings, path, f"{token}.{extension}", content_type
        )
    if settings.media_host != "local":
        raise MediaHostError(
            f"unknown NEWSROOM_MEDIA_HOST '{settings.media_host}'; "
            "use 'local' or 's3'"
        )
    return local_public_url(settings, token, extension)


def media_host_readiness(settings: Settings) -> dict[str, object]:
    """Describe whether media hosting is publish-ready, for the Settings page."""
    if settings.media_host == "s3":
        ready = settings.s3_configured
        return {
            "mode": "s3",
            "ready": ready,
            "detail": (
                f"Uploads to {settings.s3_bucket} and serves from "
                f"{settings.s3_public_base_url}"
                if ready
                else "Set S3_ENDPOINT_URL, S3_BUCKET, S3_ACCESS_KEY_ID, "
                "S3_SECRET_ACCESS_KEY, and S3_PUBLIC_BASE_URL"
            ),
        }
    base = settings.public_base_url
    ready = bool(base)
    detail = "Set NEWSROOM_PUBLIC_BASE_URL to a public HTTPS address"
    if ready:
        detail = f"Instagram will fetch media from {base}"
        if not base.startswith("https://"):
            detail += ". Instagram requires HTTPS; this address is not HTTPS."
            ready = False
    return {"mode": "local", "ready": ready, "detail": detail}
