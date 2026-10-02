"""The prompt-to-Instagram pipeline.

    prompt
      -> creative direction (headline, image prompts, caption, hashtags, alt)
      -> image generation, one call per slide
      -> Instagram-exact JPEG normalization
      -> stored asset with a private preview URL and a public fetch token
      -> human review and approval
      -> Instagram container, status poll, publish

Only ``publish_to_instagram`` touches the outside world in a way that cannot
be undone, and it refuses to run unless the caller has already cleared every
gate in ``posts.publish_blockers``.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import json
import secrets
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal

from .artifacts import ArtifactError, resolve_asset, sha256_file
from .config import Settings
from .database import Repository
from .imaging import (
    ImageError,
    format_spec,
    generate_image,
    normalize_for_instagram,
)
from .instagram import InstagramClient, InstagramError
from .media_host import MediaHostError, publish_media_url
from .posts import full_caption
from .rendering import display_path


class PipelineError(RuntimeError):
    """Raised when a pipeline stage cannot complete safely."""


class PublishOutcomeUnknown(PipelineError):
    """The publish request may have succeeded; reconcile, never retry blindly."""


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        temporary.write_bytes(payload)
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _asset_dir(settings: Settings, post_id: str) -> Path:
    return settings.assets_dir / "posts" / post_id


def preview_path(post_id: str, asset_id: str) -> str:
    return f"/api/posts/{post_id}/assets/{asset_id}/file"


async def generate_assets(
    settings: Settings,
    repository: Repository,
    post: dict[str, Any],
    *,
    image_provider: str | None,
    timestamp: str,
) -> list[dict[str, Any]]:
    """Generate one normalized slide per image prompt and attach them."""
    post_id = str(post["id"])
    revision = int(post["revision"])
    post_format = str(post["format"])
    prompts = [str(item) for item in post.get("image_prompts") or [] if str(item).strip()]
    if not prompts:
        raise PipelineError("the post has no image prompts to render")
    if post_format == "reel":
        raise PipelineError(
            "reel posts take an uploaded video, not a generated image; "
            "use the upload endpoint"
        )

    spec = format_spec(post_format)
    maximum = int(spec["max_assets"])
    prompts = prompts[:maximum]

    directory = _asset_dir(settings, post_id)
    written: list[Path] = []
    records: list[dict[str, Any]] = []
    try:
        for position, prompt in enumerate(prompts):
            try:
                generated = await generate_image(
                    settings,
                    prompt=prompt,
                    post_format=post_format,
                    headline=str(post.get("headline", "")),
                    provider=image_provider,
                )
                encoded, width, height = normalize_for_instagram(
                    generated.data, post_format
                )
            except ImageError as exc:
                raise PipelineError(f"slide {position + 1}: {exc}") from exc

            token = secrets.token_hex(20)
            asset_id = f"asset-{uuid.uuid4().hex[:16]}"
            target = directory / f"r{revision}-{position:02d}-{token[:8]}.jpg"
            _atomic_write(target, encoded)
            written.append(target)
            records.append(
                {
                    "id": asset_id,
                    "position": position,
                    "kind": "image",
                    "provider": generated.provider,
                    "prompt_used": prompt,
                    "path": display_path(settings, target),
                    "mime": "image/jpeg",
                    "width": width,
                    "height": height,
                    "bytes": len(encoded),
                    "sha256": sha256_file(target),
                    "public_token": token,
                    "is_demo": generated.is_demo,
                    "created_at": timestamp,
                }
            )

        previous = repository.list_post_assets(post_id)
        stored = repository.replace_post_assets(
            post_id, records, expected_revision=revision
        )
        if stored is None:
            raise PipelineError(
                "the post changed while slides were being generated; "
                "the new slides were discarded"
            )
    except Exception:
        for path in written:
            if path.exists():
                path.unlink()
        raise

    _remove_orphans(settings, previous, stored)
    return stored


def register_uploaded_asset(
    settings: Settings,
    repository: Repository,
    post: dict[str, Any],
    *,
    payload: bytes,
    kind: str,
    mime: str,
    timestamp: str,
) -> list[dict[str, Any]]:
    """Attach an operator-supplied image or video as the post's only slide."""
    post_id = str(post["id"])
    revision = int(post["revision"])
    post_format = str(post["format"])

    if kind == "image":
        try:
            encoded, width, height = normalize_for_instagram(
                payload, post_format
            )
        except ImageError as exc:
            raise PipelineError(str(exc)) from exc
        extension = "jpg"
        stored_mime = "image/jpeg"
    elif kind == "video":
        if post_format not in {"reel", "story"}:
            raise PipelineError(
                "video uploads are only valid for reel or story posts"
            )
        encoded, width, height = payload, 0, 0
        extension = "mp4"
        stored_mime = mime or "video/mp4"
    else:
        raise PipelineError(f"unsupported upload kind '{kind}'")

    token = secrets.token_hex(20)
    asset_id = f"asset-{uuid.uuid4().hex[:16]}"
    target = (
        _asset_dir(settings, post_id)
        / f"r{revision}-00-{token[:8]}.{extension}"
    )
    _atomic_write(target, encoded)
    record = {
        "id": asset_id,
        "position": 0,
        "kind": kind,
        "provider": "upload",
        "prompt_used": "Operator upload",
        "path": display_path(settings, target),
        "mime": stored_mime,
        "width": width,
        "height": height,
        "bytes": len(encoded),
        "sha256": sha256_file(target),
        "public_token": token,
        "is_demo": False,
        "created_at": timestamp,
    }
    previous = repository.list_post_assets(post_id)
    stored = repository.replace_post_assets(
        post_id, [record], expected_revision=revision
    )
    if stored is None:
        if target.exists():
            target.unlink()
        raise PipelineError(
            "the post changed while the upload was being saved"
        )
    _remove_orphans(settings, previous, stored)
    return stored


def _remove_orphans(
    settings: Settings,
    previous: list[dict[str, Any]],
    current: list[dict[str, Any]],
) -> None:
    keep = {str(asset["path"]) for asset in current}
    for asset in previous:
        identifier = str(asset.get("path", ""))
        if not identifier or identifier in keep:
            continue
        try:
            path = resolve_asset(settings, identifier)
        except ArtifactError:
            continue
        if path.exists():
            path.unlink()


async def build_media_urls(
    settings: Settings,
    assets: list[dict[str, Any]],
) -> list[str]:
    """Give every slide a URL Instagram's servers can fetch."""
    urls: list[str] = []
    for asset in assets:
        try:
            path = resolve_asset(settings, str(asset["path"]))
        except ArtifactError as exc:
            raise PipelineError(f"slide file is unavailable: {exc}") from exc
        extension = "mp4" if asset.get("kind") == "video" else "jpg"
        try:
            urls.append(
                await publish_media_url(
                    settings,
                    path=path,
                    token=str(asset["public_token"]),
                    extension=extension,
                    content_type=str(asset.get("mime", "image/jpeg")),
                )
            )
        except MediaHostError as exc:
            raise PipelineError(str(exc)) from exc
    return urls


async def publish_to_instagram(
    settings: Settings,
    repository: Repository,
    post: dict[str, Any],
    assets: list[dict[str, Any]],
    publication_id: str,
    timestamp_factory: Callable[[], str],
    *,
    sleep=asyncio.sleep,
) -> dict[str, Any]:
    """Create containers, wait for processing, then publish. One shot only."""
    post_id = str(post["id"])
    post_format = str(post["format"])
    caption = full_caption(
        str(post.get("caption", "")), list(post.get("hashtags") or [])
    )
    alt_text = str(post.get("alt_text", ""))

    try:
        client = InstagramClient(settings)
        media_urls = await build_media_urls(settings, assets)

        repository.update_publication(
            publication_id,
            {"status": "creating", "ig_user_id": client.user_id},
            timestamp_factory(),
        )

        if post_format == "carousel":
            children: list[str] = []
            for url in media_urls:
                child = await client.create_image_container(
                    image_url=url, is_carousel_item=True, alt_text=alt_text
                )
                await client.wait_for_container(child, sleep=sleep)
                children.append(child)
            container_id = await client.create_carousel_container(
                children=children, caption=caption
            )
        elif post_format == "reel":
            container_id = await client.create_video_container(
                video_url=media_urls[0], caption=caption, media_type="REELS"
            )
        elif post_format == "story":
            if assets[0].get("kind") == "video":
                container_id = await client.create_video_container(
                    video_url=media_urls[0], media_type="STORIES"
                )
            else:
                container_id = await client.create_image_container(
                    image_url=media_urls[0], media_type="STORIES"
                )
        else:
            container_id = await client.create_image_container(
                image_url=media_urls[0], caption=caption, alt_text=alt_text
            )

        repository.update_publication(
            publication_id,
            {"status": "publishing", "container_id": container_id},
            timestamp_factory(),
        )
        await client.wait_for_container(container_id, sleep=sleep)
    except (InstagramError, PipelineError) as exc:
        # Nothing has been published yet: containers are not posts.
        repository.fail_publication(
            publication_id,
            post_id=post_id,
            error=str(exc),
            timestamp=timestamp_factory(),
        )
        raise PipelineError(str(exc)) from exc

    # Persist the intent before sending, so a crash during the request is
    # recovered as 'unknown_outcome' rather than as a retryable failure.
    repository.mark_publication_submitted(publication_id, timestamp_factory())
    try:
        media_id = await client.publish(container_id)
    except InstagramError as exc:
        if not exc.ambiguous:
            repository.fail_publication(
                publication_id,
                post_id=post_id,
                error=str(exc),
                timestamp=timestamp_factory(),
            )
            raise PipelineError(str(exc)) from exc
        message = (
            f"Instagram did not give a clear answer to the publish request "
            f"({exc}). The post may be live. Reconcile this attempt before "
            f"publishing again; do not simply retry."
        )
        repository.mark_publication_unknown(
            publication_id,
            post_id=post_id,
            error=message,
            timestamp=timestamp_factory(),
        )
        raise PublishOutcomeUnknown(message) from exc
    except Exception as exc:
        message = (
            f"The publish request was interrupted ({type(exc).__name__}). "
            f"The post may be live. Reconcile this attempt before publishing "
            f"again."
        )
        repository.mark_publication_unknown(
            publication_id,
            post_id=post_id,
            error=message,
            timestamp=timestamp_factory(),
        )
        raise PublishOutcomeUnknown(message) from exc

    # The post is live from here on. A failure below is a reporting problem,
    # never a reason to retry the publish.
    permalink = ""
    try:
        details = await client.media_details(media_id)
        permalink = str(details.get("permalink") or "")
    except InstagramError:
        permalink = ""

    finished = repository.finish_publication(
        publication_id,
        post_id=post_id,
        media_id=media_id,
        permalink=permalink,
        timestamp=timestamp_factory(),
    )
    if finished is None:
        raise PipelineError(
            "the post was published to Instagram but the local record could "
            f"not be updated. Instagram media id: {media_id}"
        )
    return finished


def publication_manifest_sha256(
    post: dict[str, Any],
    assets: list[dict[str, Any]],
    account_id: str,
) -> str:
    """Fingerprint exactly what one publish attempt sends, and to whom."""
    payload = {
        "account_id": account_id,
        "post_id": str(post["id"]),
        "revision": int(post["revision"]),
        "format": str(post["format"]),
        "caption": full_caption(
            str(post.get("caption", "")), list(post.get("hashtags") or [])
        ),
        "alt_text": str(post.get("alt_text", "")),
        "assets": [
            {
                "position": int(asset["position"]),
                "kind": str(asset["kind"]),
                "sha256": str(asset["sha256"]),
            }
            for asset in assets
        ],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


# --- reconciliation of an ambiguous publish ----------------------------------

NOT_PUBLISHED_CONFIRMATION = "NOT PUBLISHED"
_UNPUBLISHED_CONTAINER_STATES = {"FINISHED", "ERROR", "EXPIRED"}


@dataclass(slots=True)
class ReconcileOutcome:
    outcome: Literal["published", "not_published", "unresolved"]
    detail: str


def _parse_timestamp(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


async def reconcile_publication(
    settings: Settings,
    repository: Repository,
    post: dict[str, Any],
    publication: dict[str, Any],
    *,
    action: Literal["check", "confirm_published", "confirm_not_published"],
    timestamp_factory: Callable[[], str],
    media_id: str = "",
    confirmation: str = "",
    now: dt.datetime | None = None,
) -> ReconcileOutcome:
    """Resolve an 'unknown_outcome' attempt. Never publishes anything.

    ``check`` asks Instagram for the container's status. ``PUBLISHED`` means
    the post is live; ``FINISHED``, ``ERROR`` or ``EXPIRED`` mean it is not.
    Anything else stays unresolved. The two ``confirm_*`` actions record what
    the operator saw on the profile; releasing the slot needs a typed phrase
    because it re-enables publishing.
    """
    if publication.get("status") != "unknown_outcome":
        raise PipelineError(
            "only an attempt with an unknown outcome can be reconciled"
        )
    post_id = str(post["id"])
    publication_id = str(publication["id"])

    def release(detail: str) -> ReconcileOutcome:
        repository.fail_publication(
            publication_id,
            post_id=post_id,
            error=detail,
            timestamp=timestamp_factory(),
        )
        return ReconcileOutcome("not_published", detail)

    def record_live(media: str, permalink: str, note: str) -> ReconcileOutcome:
        finished = repository.finish_publication(
            publication_id,
            post_id=post_id,
            media_id=media,
            permalink=permalink,
            timestamp=timestamp_factory(),
            note=note,
        )
        if finished is None:
            raise PipelineError("the attempt changed while it was reconciled")
        repository.update_post(post_id, {"error": note}, timestamp_factory())
        return ReconcileOutcome("published", note or "The post is live.")

    if action == "confirm_not_published":
        if confirmation.strip() != NOT_PUBLISHED_CONFIRMATION:
            raise PipelineError(
                f'type "{NOT_PUBLISHED_CONFIRMATION}" to confirm you checked '
                "the profile and the post is not there"
            )
        return release(
            "Reconciled by the operator: the post is not on the profile. "
            "It can be published again after a new confirmation."
        )

    client = InstagramClient(settings)

    if action == "confirm_published":
        media = media_id.strip()
        if not media:
            raise PipelineError("give the Instagram media id of the live post")
        try:
            details = await client.media_details(media)
        except InstagramError as exc:
            raise PipelineError(
                f"Instagram does not confirm media {media}: {exc}"
            ) from exc
        return record_live(media, str(details.get("permalink") or ""), "")

    container_id = str(publication.get("container_id") or "")
    if not container_id:
        return ReconcileOutcome(
            "unresolved",
            "No container id was recorded, so Instagram cannot be asked. "
            "Check the profile and confirm the outcome by hand.",
        )
    try:
        state = await client.container_status(container_id)
    except InstagramError as exc:
        return ReconcileOutcome(
            "unresolved", f"Could not read the container status: {exc}"
        )

    if state == "PUBLISHED":
        caption = full_caption(
            str(post.get("caption", "")), list(post.get("hashtags") or [])
        ).strip()
        try:
            recent = await client.recent_media()
        except InstagramError:
            recent = []
        match = next(
            (
                row
                for row in recent
                if str(row.get("caption") or "").strip() == caption
            ),
            None,
        )
        if match is not None:
            return record_live(
                str(match.get("id") or ""),
                str(match.get("permalink") or ""),
                "",
            )
        return record_live(
            "",
            "",
            "Instagram reports the post as published, but its media id "
            "could not be matched. Find it on the profile.",
        )

    if state in _UNPUBLISHED_CONTAINER_STATES:
        current = now or dt.datetime.now(dt.timezone.utc)
        waited = (
            current - _parse_timestamp(str(publication["updated_at"]))
        ).total_seconds()
        remaining = settings.instagram_reconcile_settle_seconds - waited
        if remaining > 0:
            return ReconcileOutcome(
                "unresolved",
                f"Instagram reports the container as {state}. Check again "
                f"in {int(remaining) + 1} seconds, in case the publish is "
                "still being processed.",
            )
        return release(
            f"Reconciled: Instagram reports the container as {state}, so "
            "it was not published. It can be published again after a new "
            "confirmation."
        )

    return ReconcileOutcome(
        "unresolved",
        f"Instagram reports the container as {state}. Check again shortly.",
    )
