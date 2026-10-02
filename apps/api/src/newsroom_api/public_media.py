"""Serve post media to Instagram's fetcher by capability token.

Shared by the full API (``/api/public/media/...``) and the media-only gateway
so both apply exactly the same rules. A file is served only when every one of
these holds:

* the filename is a forty character token plus the extension of its kind;
* the token belongs to a real (non-placeholder) asset;
* the asset belongs to the post's current revision;
* the post is approved, publishing or published, i.e. a human reviewed it.

Every refusal is the same bare 404 so the route reveals nothing about which
rule failed.
"""

from __future__ import annotations

import sqlite3

from fastapi import HTTPException, status
from fastapi.responses import FileResponse

from .artifacts import ArtifactError, resolve_asset
from .config import Settings
from .database import Repository

SERVABLE_POST_STATUSES = {"approved", "publishing", "published"}


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail="not found"
    )


def serve_public_media(
    settings: Settings, repository: Repository, filename: str
) -> FileResponse:
    token, _, extension = filename.partition(".")
    if extension not in {"jpg", "mp4"} or len(token) != 40:
        raise _not_found()
    try:
        asset = repository.get_post_asset_by_token(token)
        post = (
            repository.get_post(str(asset["post_id"])) if asset else None
        )
    except sqlite3.Error:
        raise _not_found() from None
    if asset is None or post is None:
        raise _not_found()
    expected_extension = "mp4" if asset.get("kind") == "video" else "jpg"
    if (
        extension != expected_extension
        or bool(asset.get("is_demo"))
        or int(asset.get("post_revision", 0)) != int(post.get("revision", -1))
        or str(post.get("status")) not in SERVABLE_POST_STATUSES
    ):
        raise _not_found()
    try:
        path = resolve_asset(settings, str(asset["path"]))
    except ArtifactError:
        raise _not_found() from None
    if not path.is_file():
        raise _not_found()
    return FileResponse(
        path,
        media_type=str(asset["mime"]),
        headers={"Cache-Control": "public, max-age=300"},
    )
