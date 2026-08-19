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
import secrets
import uuid
from pathlib import Path
from typing import Any, Callable

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
        media_id = await client.publish(container_id)
    except (InstagramError, PipelineError) as exc:
        repository.fail_publication(
            publication_id,
            post_id=post_id,
            error=str(exc),
            timestamp=timestamp_factory(),
        )
        raise PipelineError(str(exc)) from exc

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
