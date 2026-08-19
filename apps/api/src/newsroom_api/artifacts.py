from __future__ import annotations

import hashlib
from pathlib import Path

from .config import Settings


class ArtifactError(ValueError):
    """Raised when a stored artifact identifier is unsafe or unavailable."""


def asset_identifier(settings: Settings, path: Path) -> str:
    """Return a portable identifier rooted beneath NEWSROOM_ASSETS_DIR."""
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(settings.assets_dir.resolve())
    except ValueError as exc:
        raise ArtifactError("artifact is outside NEWSROOM_ASSETS_DIR") from exc
    return relative.as_posix()


def resolve_asset(
    settings: Settings,
    identifier: str,
    *,
    require_file: bool = True,
) -> Path:
    """Resolve a stored identifier without permitting absolute/path traversal."""
    cleaned = identifier.strip()
    if not cleaned:
        raise ArtifactError("artifact identifier is empty")
    supplied = Path(cleaned)
    root = settings.assets_dir.resolve()
    if supplied.is_absolute() or supplied.drive:
        candidates = [supplied.resolve()]
    else:
        candidates = [(root / supplied).resolve()]
        legacy_candidate = (settings.api_root.resolve() / supplied).resolve()
        if legacy_candidate not in candidates:
            candidates.append(legacy_candidate)

    safe_candidates: list[Path] = []
    for candidate in candidates:
        try:
            candidate.relative_to(root)
        except ValueError:
            continue
        safe_candidates.append(candidate)
        if not require_file or candidate.is_file():
            if require_file:
                try:
                    with candidate.open("rb") as handle:
                        handle.read(1)
                except OSError as exc:
                    raise ArtifactError(
                        "artifact file is not readable"
                    ) from exc
            return candidate
    if not safe_candidates:
        raise ArtifactError("artifact path escapes NEWSROOM_ASSETS_DIR")
    raise ArtifactError("artifact file is missing")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
