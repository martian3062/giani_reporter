from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .artifacts import asset_identifier, resolve_asset, sha256_file
from .config import Settings
from .database import Repository


def display_path(settings: Settings, path: Path) -> str:
    return asset_identifier(settings, path)


def atomic_json_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    temporary_path.replace(path)


def run_manifest_render(
    database_path: Path,
    settings: Settings,
    job_id: str,
    timestamp_factory: Any,
) -> None:
    repository = Repository(database_path)
    output: Path | None = None
    try:
        job = repository.claim_render_job(job_id, timestamp_factory())
        if job is None:
            internal_job = repository.get_render_job_internal(job_id)
            if internal_job and internal_job["status"] == "queued":
                repository.fail_render_job_if_active(
                    job_id,
                    "Render job no longer matches the current episode revision",
                    timestamp_factory(),
                )
            return
        episode = repository.get_episode(job.episode_id)
        internal = repository.get_episode_internal(job.episode_id)
        if episode is None or internal is None:
            raise RuntimeError("episode no longer exists")
        voice_path = resolve_asset(
            settings,
            str(internal.get("voice_path", "")),
        )
        stories = repository.get_stories_by_ids(episode.story_ids)
        current_job = repository.update_render_job_if_current(
            job_id,
            {"progress": 55, "stage": "building_manifest"},
            timestamp_factory(),
        )
        if current_job is None:
            return
        output = settings.assets_dir / "renders" / job_id / "manifest.json"
        payload = {
            "schema_version": 1,
            "job_id": job_id,
            "episode_revision": job.episode_revision,
            "mode": "render-handoff",
            "is_demo": any(story.is_demo for story in stories),
            "episode": episode.model_dump(),
            "sources": [story.model_dump() for story in stories],
            "voice": {
                "provider": internal.get("voice_provider", ""),
                "output_path": (
                    f"/api/episodes/{episode.id}/voice/file"
                ),
                "sha256": sha256_file(voice_path),
            },
            "assembly": {
                "resolution": (
                    "1080x1920"
                    if episode.kind == "daily"
                    else "1920x1080"
                ),
                "captions": "burned-in",
                "broll_cues": episode.cues,
                "note": (
                    "This manifest is a nonblocking local handoff. It does not "
                    "pretend that HeyGen or CapCut rendered a finished video."
                ),
            },
            "created_at": timestamp_factory(),
        }
        atomic_json_write(output, payload)
        completed = repository.update_render_job_if_current(
            job_id,
            {
                "status": "complete",
                "progress": 100,
                "stage": "manifest_ready",
                "output_path": display_path(settings, output),
                "error": "",
            },
            timestamp_factory(),
        )
        if completed is None and output.exists():
            output.unlink()
    except Exception as exc:  # job failures must be persisted for polling
        repository.fail_render_job_if_active(
            job_id,
            f"{type(exc).__name__}: {exc}",
            timestamp_factory(),
        )
