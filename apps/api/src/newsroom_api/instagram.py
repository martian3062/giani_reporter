"""Instagram Content Publishing API client.

The publish flow Instagram requires is always three steps:

1. ``POST /{ig-user-id}/media`` creates a *container* pointing at a public URL.
2. ``GET  /{container-id}?fields=status_code`` polls until ``FINISHED``.
3. ``POST /{ig-user-id}/media_publish`` turns the container into a live post.

Carousels add a fan-out: each child is its own container created with
``is_carousel_item=true``, then a parent ``CAROUSEL`` container lists them.

Nothing in this module decides *whether* to publish. It is called only after a
human approval gate in ``main.py``.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
from typing import Any

import httpx

from .config import Settings


class InstagramError(RuntimeError):
    """Raised when Instagram rejects a request or a container never finishes."""


TERMINAL_ERROR_STATES = {"ERROR", "EXPIRED"}


def appsecret_proof(access_token: str, app_secret: str) -> str:
    """Meta server-side proof required when an app secret is configured."""
    return hmac.new(
        app_secret.encode("utf-8"),
        access_token.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _describe_error(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return f"HTTP {response.status_code}: {response.text[:300]}"
    error = body.get("error") if isinstance(body, dict) else None
    if isinstance(error, dict):
        parts = [
            str(error.get("message") or "").strip(),
            f"type={error.get('type')}" if error.get("type") else "",
            f"code={error.get('code')}" if error.get("code") else "",
            f"subcode={error.get('error_subcode')}"
            if error.get("error_subcode")
            else "",
        ]
        detail = " ".join(part for part in parts if part)
        return f"HTTP {response.status_code}: {detail}"
    return f"HTTP {response.status_code}: {str(body)[:300]}"


class InstagramClient:
    def __init__(self, settings: Settings):
        if not settings.instagram_configured:
            raise InstagramError(
                "INSTAGRAM_USER_ID and INSTAGRAM_ACCESS_TOKEN are required"
            )
        self._settings = settings
        self._base = settings.instagram_api_base
        self._user_id = settings.instagram_user_id.strip()
        self._token = settings.instagram_access_token.strip()
        self._timeout = max(60.0, settings.request_timeout_seconds)

    @property
    def user_id(self) -> str:
        return self._user_id

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{self._base}/{path.lstrip('/')}"
        query = {**(params or {}), "access_token": self._token}
        secret = self._settings.meta_app_secret.strip()
        if secret:
            query["appsecret_proof"] = appsecret_proof(self._token, secret)
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.request(method, url, params=query)
                if response.status_code >= 400:
                    raise InstagramError(_describe_error(response))
                body = response.json()
        except InstagramError:
            raise
        except (httpx.HTTPError, ValueError) as exc:
            raise InstagramError(
                f"Instagram request failed: {type(exc).__name__}"
            ) from exc
        if not isinstance(body, dict):
            raise InstagramError("Instagram returned an invalid response")
        return body

    # --- account ----------------------------------------------------------

    async def account(self) -> dict[str, Any]:
        return await self._request(
            "GET",
            self._user_id,
            params={"fields": "id,username,account_type"},
        )

    async def publishing_limit(self) -> dict[str, Any]:
        body = await self._request(
            "GET",
            f"{self._user_id}/content_publishing_limit",
            params={"fields": "config,quota_usage"},
        )
        rows = body.get("data")
        if isinstance(rows, list) and rows and isinstance(rows[0], dict):
            return rows[0]
        return {}

    # --- containers -------------------------------------------------------

    async def create_image_container(
        self,
        *,
        image_url: str,
        caption: str = "",
        alt_text: str = "",
        is_carousel_item: bool = False,
        media_type: str = "",
    ) -> str:
        params: dict[str, Any] = {"image_url": image_url}
        if media_type:
            params["media_type"] = media_type
        if caption and not is_carousel_item:
            params["caption"] = caption
        if alt_text:
            params["alt_text"] = alt_text[:1000]
        if is_carousel_item:
            params["is_carousel_item"] = "true"
        body = await self._request(
            "POST", f"{self._user_id}/media", params=params
        )
        return self._container_id(body)

    async def create_video_container(
        self,
        *,
        video_url: str,
        caption: str = "",
        media_type: str = "REELS",
        cover_url: str = "",
        share_to_feed: bool = True,
    ) -> str:
        params: dict[str, Any] = {
            "video_url": video_url,
            "media_type": media_type,
        }
        if caption and media_type != "STORIES":
            params["caption"] = caption
        if cover_url:
            params["cover_url"] = cover_url
        if media_type == "REELS":
            params["share_to_feed"] = "true" if share_to_feed else "false"
        body = await self._request(
            "POST", f"{self._user_id}/media", params=params
        )
        return self._container_id(body)

    async def create_carousel_container(
        self, *, children: list[str], caption: str = ""
    ) -> str:
        if not 2 <= len(children) <= 10:
            raise InstagramError(
                "an Instagram carousel needs between two and ten items"
            )
        params: dict[str, Any] = {
            "media_type": "CAROUSEL",
            "children": ",".join(children),
        }
        if caption:
            params["caption"] = caption
        body = await self._request(
            "POST", f"{self._user_id}/media", params=params
        )
        return self._container_id(body)

    @staticmethod
    def _container_id(body: dict[str, Any]) -> str:
        container_id = body.get("id")
        if not isinstance(container_id, str) or not container_id:
            raise InstagramError("Instagram returned no container id")
        return container_id

    # --- status and publish ----------------------------------------------

    async def wait_for_container(
        self, container_id: str, *, sleep=asyncio.sleep
    ) -> None:
        """Block until the container is FINISHED, or explain why it is not."""
        attempts = max(1, self._settings.instagram_poll_attempts)
        interval = max(0.0, self._settings.instagram_poll_interval_seconds)
        last_status = "UNKNOWN"
        for attempt in range(attempts):
            body = await self._request(
                "GET",
                container_id,
                params={"fields": "status_code,status"},
            )
            last_status = str(body.get("status_code") or "UNKNOWN")
            if last_status == "FINISHED":
                return
            if last_status == "PUBLISHED":
                return
            if last_status in TERMINAL_ERROR_STATES:
                raise InstagramError(
                    f"Instagram could not process the media ({last_status}): "
                    f"{body.get('status') or 'no detail supplied'}"
                )
            if attempt < attempts - 1:
                await sleep(interval)
        raise InstagramError(
            f"Instagram media was still '{last_status}' after "
            f"{attempts} status checks"
        )

    async def publish(self, container_id: str) -> str:
        body = await self._request(
            "POST",
            f"{self._user_id}/media_publish",
            params={"creation_id": container_id},
        )
        media_id = body.get("id")
        if not isinstance(media_id, str) or not media_id:
            raise InstagramError("Instagram returned no published media id")
        return media_id

    async def media_details(self, media_id: str) -> dict[str, Any]:
        return await self._request(
            "GET",
            media_id,
            params={"fields": "id,permalink,media_type,timestamp"},
        )


async def _graph_get(
    settings: Settings,
    url: str,
    *,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    token = settings.instagram_access_token.strip()
    if not token:
        raise InstagramError("INSTAGRAM_ACCESS_TOKEN is not set")
    query: dict[str, Any] = {**(params or {}), "access_token": token}
    secret = settings.meta_app_secret.strip()
    if secret:
        query["appsecret_proof"] = appsecret_proof(token, secret)
    timeout = max(60.0, settings.request_timeout_seconds)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url, params=query)
            if response.status_code >= 400:
                raise InstagramError(_describe_error(response))
            body = response.json()
    except InstagramError:
        raise
    except (httpx.HTTPError, ValueError) as exc:
        raise InstagramError(
            f"Instagram request failed: {type(exc).__name__}"
        ) from exc
    if not isinstance(body, dict):
        raise InstagramError("Instagram returned an invalid response")
    return body


async def exchange_long_lived_token(settings: Settings) -> dict[str, Any]:
    """Exchange a short-lived token for a 60-day token (Instagram Login route)."""
    secret = settings.meta_app_secret.strip()
    if not secret:
        raise InstagramError(
            "Set META_APP_SECRET (or FACEBOOK_APP_SECRET) to exchange tokens"
        )
    token = settings.instagram_access_token.strip()
    if not token:
        raise InstagramError("INSTAGRAM_ACCESS_TOKEN is not set")
    if settings.instagram_login_mode != "instagram":
        raise InstagramError(
            "Token exchange uses graph.instagram.com; set "
            "INSTAGRAM_LOGIN_MODE=instagram"
        )
    url = "https://graph.instagram.com/access_token"
    body = await _graph_get(
        settings,
        url,
        params={
            "grant_type": "ig_exchange_token",
            "client_secret": secret,
        },
    )
    return body


async def refresh_long_lived_token(settings: Settings) -> dict[str, Any]:
    """Refresh a long-lived Instagram Login token before it expires."""
    token = settings.instagram_access_token.strip()
    if not token:
        raise InstagramError("INSTAGRAM_ACCESS_TOKEN is not set")
    if settings.instagram_login_mode != "instagram":
        raise InstagramError(
            "Token refresh uses graph.instagram.com; set "
            "INSTAGRAM_LOGIN_MODE=instagram"
        )
    url = "https://graph.instagram.com/refresh_access_token"
    return await _graph_get(
        settings,
        url,
        params={"grant_type": "ig_refresh_token"},
    )


async def debug_token(settings: Settings) -> dict[str, Any]:
    """Inspect the configured token without publishing anything."""
    app_id = settings.meta_app_id.strip()
    secret = settings.meta_app_secret.strip()
    token = settings.instagram_access_token.strip()
    if not app_id or not token:
        return {}
    app_token = f"{app_id}|{secret}" if secret else app_id
    url = f"https://graph.facebook.com/debug_token"
    params: dict[str, Any] = {
        "input_token": token,
        "access_token": app_token,
    }
    timeout = max(60.0, settings.request_timeout_seconds)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url, params=params)
            if response.status_code >= 400:
                raise InstagramError(_describe_error(response))
            body = response.json()
    except InstagramError:
        raise
    except (httpx.HTTPError, ValueError) as exc:
        raise InstagramError(
            f"Instagram request failed: {type(exc).__name__}"
        ) from exc
    data = body.get("data") if isinstance(body, dict) else None
    return data if isinstance(data, dict) else {}


async def diagnose(settings: Settings) -> dict[str, Any]:
    """Report Instagram readiness without publishing anything."""
    report: dict[str, Any] = {
        "configured": settings.instagram_configured,
        "publish_enabled": settings.instagram_publish_enabled,
        "login_mode": settings.instagram_login_mode,
        "api_base": settings.instagram_api_base,
        "meta_app": {
            "configured": settings.meta_app_configured,
            "app_id_set": bool(settings.meta_app_id.strip()),
            "app_secret_set": bool(settings.meta_app_secret.strip()),
        },
        "account": None,
        "quota": None,
        "token": None,
        "error": "",
    }
    if not settings.instagram_configured:
        report["error"] = (
            "Set INSTAGRAM_USER_ID and INSTAGRAM_ACCESS_TOKEN "
            "(META_ACCESS_TOKEN is also read) in the API environment."
        )
        return report
    try:
        client = InstagramClient(settings)
        report["account"] = await client.account()
        report["quota"] = await client.publishing_limit()
        if settings.meta_app_id.strip():
            report["token"] = await debug_token(settings)
    except InstagramError as exc:
        report["error"] = str(exc)
    return report
