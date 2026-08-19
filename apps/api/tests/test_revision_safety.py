from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

import newsroom_api.main as main_module
import newsroom_api.rendering as rendering_module
from newsroom_api.database import Repository
from newsroom_api.editorial import COMPLIANCE_GATES
from newsroom_api.main import utc_timestamp


def _draft_and_approve(client: TestClient, episode_id: str) -> dict[str, Any]:
    drafted = client.post(
        f"/api/episodes/{episode_id}/draft",
        json={"provider": "offline"},
    )
    assert drafted.status_code == 200
    approved = client.post(f"/api/episodes/{episode_id}/approve")
    assert approved.status_code == 200
    return approved.json()


def test_stale_voice_result_is_rejected_and_removed(
    client: TestClient,
    daily_episode: dict[str, Any],
    monkeypatch: Any,
) -> None:
    episode_id = daily_episode["id"]
    approved = _draft_and_approve(client, episode_id)
    repository = client.app.state.repository
    settings = client.app.state.settings
    settings.elevenlabs_api_key = "test-key"
    settings.elevenlabs_voice_id = "test-voice"

    async def edit_while_provider_runs(*_args: Any, **_kwargs: Any) -> bytes:
        changed = repository.update_episode_content(
            episode_id,
            {
                "angle": "An edit landed while the provider was running",
                "status": "draft",
            },
            utc_timestamp(),
            expected_revision=approved["revision"],
        )
        assert changed is not None
        return b"stale voice bytes"

    monkeypatch.setattr(
        main_module,
        "elevenlabs_speech",
        edit_while_provider_runs,
    )

    response = client.post(f"/api/episodes/{episode_id}/voice")

    assert response.status_code == 409
    assert "stale artifact was discarded" in response.json()["detail"]
    internal = repository.get_episode_internal(episode_id)
    assert internal is not None
    assert internal["revision"] == approved["revision"] + 1
    assert internal["voice_revision"] == 0
    assert internal["voice_path"] == ""
    voice_dir = settings.assets_dir / "voice"
    assert not voice_dir.exists() or list(voice_dir.iterdir()) == []


def test_edit_during_render_cannot_resurrect_invalidated_job(
    client: TestClient,
    daily_episode: dict[str, Any],
    monkeypatch: Any,
) -> None:
    episode_id = daily_episode["id"]
    approved = _draft_and_approve(client, episode_id)
    assert client.post(f"/api/episodes/{episode_id}/voice").status_code == 200
    repository = client.app.state.repository
    original_write = rendering_module.atomic_json_write

    def edit_before_final_render_update(
        path: Path, payload: dict[str, Any]
    ) -> None:
        original_write(path, payload)
        changed = repository.update_episode_content(
            episode_id,
            {
                "angle": "An edit landed before the render completion update",
                "status": "draft",
            },
            utc_timestamp(),
            expected_revision=approved["revision"],
        )
        assert changed is not None

    monkeypatch.setattr(
        rendering_module,
        "atomic_json_write",
        edit_before_final_render_update,
    )

    queued = client.post(f"/api/episodes/{episode_id}/render")

    assert queued.status_code == 202
    job_id = queued.json()["id"]
    job = client.get(f"/api/render-jobs/{job_id}").json()
    assert job["status"] == "failed"
    assert job["stage"] == "invalidated"
    assert job["episode_revision"] == approved["revision"]
    manifest = (
        client.app.state.settings.assets_dir
        / "renders"
        / job_id
        / "manifest.json"
    )
    assert not manifest.exists()


def test_edit_during_publish_fails_cas_and_removes_candidate(
    client: TestClient,
    daily_episode: dict[str, Any],
    monkeypatch: Any,
) -> None:
    episode_id = daily_episode["id"]
    approved = _draft_and_approve(client, episode_id)
    for gate in COMPLIANCE_GATES:
        response = client.put(
            f"/api/episodes/{episode_id}/compliance/{gate}",
            json={"passed": True},
        )
        assert response.status_code == 200
    assert client.post(f"/api/episodes/{episode_id}/voice").status_code == 200
    render = client.post(f"/api/episodes/{episode_id}/render")
    assert render.status_code == 202
    assert (
        client.get(f"/api/render-jobs/{render.json()['id']}").json()["status"]
        == "complete"
    )
    repository = client.app.state.repository
    original_write = main_module.atomic_json_write

    def edit_while_package_is_written(
        path: Path, payload: dict[str, Any]
    ) -> None:
        original_write(path, payload)
        changed = repository.update_episode_content(
            episode_id,
            {
                "angle": "An edit landed while packaging",
                "status": "draft",
            },
            utc_timestamp(),
            expected_revision=approved["revision"],
        )
        assert changed is not None

    monkeypatch.setattr(
        main_module,
        "atomic_json_write",
        edit_while_package_is_written,
    )

    response = client.post(f"/api/episodes/{episode_id}/publish-package")

    assert response.status_code == 409
    assert "changed while" in response.json()["detail"]
    package_dir = client.app.state.settings.assets_dir / "publish-packages"
    assert not package_dir.exists() or list(package_dir.iterdir()) == []
    assert client.get(f"/api/episodes/{episode_id}").json()["status"] == "draft"


def test_initialize_migrates_legacy_artifact_revisions(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "legacy.sqlite3"
    connection = sqlite3.connect(database_path)
    connection.executescript(
        """
        CREATE TABLE episodes (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            status TEXT NOT NULL,
            date TEXT NOT NULL,
            angle TEXT NOT NULL,
            story_ids TEXT NOT NULL,
            script TEXT NOT NULL DEFAULT '',
            sections TEXT NOT NULL DEFAULT '{}',
            title TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            hashtags TEXT NOT NULL DEFAULT '[]',
            overlays TEXT NOT NULL DEFAULT '[]',
            cues TEXT NOT NULL DEFAULT '[]',
            word_count INTEGER NOT NULL DEFAULT 0,
            runtime_seconds INTEGER NOT NULL DEFAULT 0,
            compliance TEXT NOT NULL DEFAULT '{}',
            voice_path TEXT NOT NULL DEFAULT '',
            voice_provider TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE render_jobs (
            id TEXT PRIMARY KEY,
            episode_id TEXT NOT NULL,
            status TEXT NOT NULL,
            progress INTEGER NOT NULL DEFAULT 0,
            stage TEXT NOT NULL,
            output_path TEXT NOT NULL DEFAULT '',
            error TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        INSERT INTO episodes (
            id, kind, status, date, angle, story_ids, script, sections,
            title, description, hashtags, overlays, cues, word_count,
            runtime_seconds, compliance, voice_path, voice_provider,
            created_at, updated_at
        ) VALUES (
            'legacy-episode', 'daily', 'approved', '2026-01-01',
            'Legacy angle', '[]', 'Legacy script', '{}', '', '', '[]',
            '[]', '[]', 2, 1, '{}', 'assets/voice/legacy.mp3',
            'elevenlabs', '2026-01-01T00:00:00Z',
            '2026-01-01T00:00:00Z'
        );
        INSERT INTO render_jobs (
            id, episode_id, status, progress, stage, output_path, error,
            created_at, updated_at
        ) VALUES (
            'legacy-render', 'legacy-episode', 'complete', 100,
            'manifest_ready', 'assets/renders/legacy.json', '',
            '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z'
        );
        """
    )
    connection.commit()
    connection.close()

    repository = Repository(database_path)
    repository.initialize()

    episode = repository.get_episode_internal("legacy-episode")
    job = repository.get_render_job_internal("legacy-render")
    assert episode is not None
    assert job is not None
    assert episode["revision"] == 1
    assert episode["voice_revision"] == 1
    assert job["episode_revision"] == 1
