from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import newsroom_api.main as main_module
from newsroom_api.artifacts import resolve_asset
from newsroom_api.config import Settings
from newsroom_api.editorial import COMPLIANCE_GATES
from newsroom_api.main import create_app

from conftest import selected_story_ids


def test_health_overview_and_localhost_cors(client: TestClient) -> None:
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert health.json()["database"] == "ok"

    overview = client.get("/api/overview")
    assert overview.status_code == 200
    body = overview.json()
    assert body["workspace"]["human_angle_required"] is True
    assert body["stories_total"] == 3
    assert body["stories_selected"] == 3
    assert body["demo_stories"] == 3
    assert body["compliance_gates"] == list(COMPLIANCE_GATES)

    preflight = client.options(
        "/api/stories",
        headers={
            "Origin": "http://localhost:4242",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert preflight.status_code == 200
    assert (
        preflight.headers["access-control-allow-origin"]
        == "http://localhost:4242"
    )


def test_health_returns_503_when_database_is_unavailable(
    client: TestClient,
    monkeypatch,
) -> None:
    def broken_connect():
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(
        client.app.state.repository,
        "connect",
        broken_connect,
    )

    response = client.get("/api/health")

    assert response.status_code == 503
    assert response.json()["status"] == "degraded"
    assert response.json()["database"] == "error"


def test_demo_research_fallback_is_explicit_and_idempotent(
    client: TestClient,
) -> None:
    first = client.post("/api/research/refresh", json={"live": False})
    second = client.post("/api/research/refresh", json={"live": False})
    assert first.status_code == second.status_code == 200
    assert first.json()["mode"] == "demo"
    assert first.json()["fetched"] == 0
    assert all(story["is_demo"] for story in first.json()["stories"])
    assert all("[DEMO]" in story["title"] for story in first.json()["stories"])
    assert len(client.get("/api/stories").json()) == 3


def test_story_selection_and_not_found(client: TestClient) -> None:
    story_id = selected_story_ids(client, 1)[0]
    deselected = client.post(
        f"/api/stories/{story_id}/select", json={"selected": False}
    )
    assert deselected.status_code == 200
    assert deselected.json()["selected"] is False

    selected = client.post(f"/api/stories/{story_id}/select")
    assert selected.status_code == 200
    assert selected.json()["selected"] is True
    assert client.post("/api/stories/missing/select").status_code == 404


def test_episode_creation_requires_angle_and_exact_story_count(
    client: TestClient,
) -> None:
    story_ids = selected_story_ids(client)
    no_angle = client.post(
        "/api/episodes",
        json={"kind": "daily", "angle": " ", "story_ids": story_ids},
    )
    assert no_angle.status_code == 422

    too_few = client.post(
        "/api/episodes",
        json={
            "kind": "daily",
            "angle": "A real human angle",
            "story_ids": story_ids[:2],
        },
    )
    assert too_few.status_code == 422
    assert "exactly 3 stories" in too_few.json()["detail"]

    too_many_deep = client.post(
        "/api/episodes",
        json={
            "kind": "deep_dive",
            "angle": "A real human angle",
            "story_ids": story_ids[:2],
        },
    )
    assert too_many_deep.status_code == 422
    assert "exactly 1 story" in too_many_deep.json()["detail"]

    unknown = client.post(
        "/api/episodes",
        json={
            "kind": "deep_dive",
            "angle": "A real human angle",
            "story_ids": ["not-a-story"],
        },
    )
    assert unknown.status_code == 422
    assert unknown.json()["detail"]["missing"] == ["not-a-story"]


def test_daily_offline_draft_has_frontend_fields_and_is_approvable(
    client: TestClient, daily_episode: dict
) -> None:
    episode_id = daily_episode["id"]
    drafted = client.post(
        f"/api/episodes/{episode_id}/draft",
        json={"provider": "offline"},
    )
    assert drafted.status_code == 200
    assert drafted.headers["x-draft-provider"] == "offline"
    episode = drafted.json()
    assert episode["status"] == "draft"
    assert 210 <= episode["word_count"] <= 225
    assert 60 <= episode["runtime_seconds"] <= 90
    assert set(episode["sections"]) == {
        "hook",
        "story_1",
        "story_2",
        "story_3",
        "take",
        "sign_off",
    }
    assert len(episode["hashtags"]) == 5
    assert len(episode["overlays"]) == 4
    assert all(1 <= len(item["text"].strip()) <= 42 for item in episode["overlays"])
    assert episode["cues"]
    assert not any(episode["compliance"].values())
    assert all(url in episode["description"] for url in (
        "https://example.invalid/newsroom/demo-source-check",
        "https://example.invalid/newsroom/demo-editorial-angle",
        "https://example.invalid/newsroom/demo-render-handoff",
    ))

    approved = client.post(f"/api/episodes/{episode_id}/approve")
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"


@pytest.mark.parametrize(
    "angle",
    [
        "Brief angle",
        "One",
        "A deliberately longer editorial angle that still stays within the accepted input contract",
    ],
)
def test_daily_offline_draft_always_meets_word_budget(
    client: TestClient,
    angle: str,
) -> None:
    story_ids = selected_story_ids(client)
    created = client.post(
        "/api/episodes",
        json={"kind": "daily", "angle": angle, "story_ids": story_ids},
    )
    assert created.status_code == 201

    drafted = client.post(
        f"/api/episodes/{created.json()['id']}/draft",
        json={"provider": "offline"},
    )

    assert drafted.status_code == 200
    assert 210 <= drafted.json()["word_count"] <= 225
    assert client.post(
        f"/api/episodes/{created.json()['id']}/approve"
    ).status_code == 200


def test_approval_blocks_verify_tags_and_voice_rule_violations(
    client: TestClient, daily_episode: dict
) -> None:
    episode_id = daily_episode["id"]
    drafted = client.post(
        f"/api/episodes/{episode_id}/draft",
        json={"provider": "offline"},
    ).json()
    bad_sections = dict(drafted["sections"])
    bad_sections["take"] += " [VERIFY] You should buy this;"
    patched = client.patch(
        f"/api/episodes/{episode_id}",
        json={"sections": bad_sections},
    )
    assert patched.status_code == 200

    approval = client.post(f"/api/episodes/{episode_id}/approve")
    assert approval.status_code == 409
    errors = approval.json()["detail"]["errors"]
    assert any("[VERIFY]" in error for error in errors)
    assert any("punctuation" in error for error in errors)
    assert any("advice" in error for error in errors)


@pytest.mark.parametrize(
    ("unsafe_suffix", "expected_error"),
    [
        (" Buy Acme shares.", "advisory or imperative"),
        (" API.", "spell every acronym"),
        (
            " I am Doctor Mira, an expert.",
            "credential or expert framing",
        ),
    ],
)
def test_approval_blocks_advice_acronyms_and_credential_framing(
    client: TestClient,
    daily_episode: dict,
    unsafe_suffix: str,
    expected_error: str,
) -> None:
    episode_id = daily_episode["id"]
    drafted = client.post(
        f"/api/episodes/{episode_id}/draft",
        json={"provider": "offline"},
    ).json()
    unsafe_sections = dict(drafted["sections"])
    unsafe_sections["take"] += unsafe_suffix
    patched = client.patch(
        f"/api/episodes/{episode_id}",
        json={"sections": unsafe_sections},
    )
    assert patched.status_code == 200

    approval = client.post(f"/api/episodes/{episode_id}/approve")

    assert approval.status_code == 409
    assert expected_error in json.dumps(approval.json()["detail"])
    if "credential" in expected_error:
        assert patched.json()["compliance"]["neutral_anchor"] is False


def test_deep_dive_requires_one_story_and_offline_draft_is_valid(
    client: TestClient,
) -> None:
    story_id = selected_story_ids(client, 1)[0]
    created = client.post(
        "/api/episodes",
        json={
            "kind": "deep_dive",
            "angle": "Source discipline matters more as scripts get longer",
            "story_ids": [story_id],
        },
    )
    assert created.status_code == 201
    episode_id = created.json()["id"]
    drafted = client.post(
        f"/api/episodes/{episode_id}/draft",
        json={"provider": "offline"},
    )
    assert drafted.status_code == 200
    body = drafted.json()
    assert 900 <= body["word_count"] <= 1100
    assert 300 <= body["runtime_seconds"] <= 480
    assert "I could be wrong about this" in body["script"]
    assert client.post(f"/api/episodes/{episode_id}/approve").status_code == 200


def test_patch_recalculates_script_metrics_and_demotes_approved_episode(
    client: TestClient, daily_episode: dict
) -> None:
    episode_id = daily_episode["id"]
    drafted = client.post(
        f"/api/episodes/{episode_id}/draft",
        json={"provider": "offline"},
    ).json()
    assert client.post(f"/api/episodes/{episode_id}/approve").status_code == 200

    script_only = client.patch(
        f"/api/episodes/{episode_id}",
        json={"script": drafted["script"]},
    )
    assert script_only.status_code == 422

    revised_sections = dict(drafted["sections"])
    revised_sections["take"] += " One short human edit."
    patched = client.patch(
        f"/api/episodes/{episode_id}",
        json={
            "angle": "A revised human angle",
            "sections": revised_sections,
        },
    )
    assert patched.status_code == 200
    body = patched.json()
    assert body["status"] == "draft"
    assert body["word_count"] == drafted["word_count"] + 4
    assert body["angle"] == "A revised human angle"
    assert body["compliance"]["format_varied"] is False

    null_patch = client.patch(
        f"/api/episodes/{episode_id}",
        json={"script": None},
    )
    assert null_patch.status_code == 422
    assert client.get(f"/api/episodes/{episode_id}").status_code == 200


def test_voice_render_compliance_and_publish_package(
    client: TestClient, daily_episode: dict
) -> None:
    episode_id = daily_episode["id"]
    client.post(
        f"/api/episodes/{episode_id}/draft",
        json={"provider": "offline"},
    )
    client.post(f"/api/episodes/{episode_id}/approve")

    blocked = client.post(
        f"/api/episodes/{episode_id}/publish-package"
    )
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["blocking"]

    report = client.get(
        f"/api/episodes/{episode_id}/compliance"
    ).json()
    for gate in report["blocking"]:
        updated = client.put(
            f"/api/episodes/{episode_id}/compliance/{gate}",
            json={"passed": True},
        )
        assert updated.status_code == 200
    complete_report = client.get(
        f"/api/episodes/{episode_id}/compliance"
    ).json()
    assert complete_report["all_passed"] is True

    render_without_voice = client.post(
        f"/api/episodes/{episode_id}/render"
    )
    assert render_without_voice.status_code == 409
    assert "voice artifact" in render_without_voice.json()["detail"]

    package_without_render = client.post(
        f"/api/episodes/{episode_id}/publish-package"
    )
    assert package_without_render.status_code == 409
    assert "completed render" in package_without_render.json()["detail"]

    voice = client.post(f"/api/episodes/{episode_id}/voice")
    assert voice.status_code == 200
    assert voice.json()["provider"] == "demo"
    assert voice.json()["is_demo"] is True
    assert voice.json()["output_path"].startswith("/api/")
    voice_download = client.get(voice.json()["output_path"])
    assert voice_download.status_code == 200
    assert "NOT AUDIO" in voice_download.text

    render = client.post(f"/api/episodes/{episode_id}/render")
    assert render.status_code == 202
    job = client.get(f"/api/render-jobs/{render.json()['id']}")
    assert job.status_code == 200
    assert job.json()["status"] == "complete"
    assert job.json()["progress"] == 100
    assert job.json()["output_path"].startswith("/api/")
    manifest_download = client.get(job.json()["output_path"])
    assert manifest_download.status_code == 200
    manifest = manifest_download.json()
    assert manifest["mode"] == "render-handoff"
    assert manifest["is_demo"] is True
    assert manifest["voice"]["output_path"].startswith("/api/")
    assert len(manifest["voice"]["sha256"]) == 64

    package = client.post(
        f"/api/episodes/{episode_id}/publish-package"
    )
    assert package.status_code == 200
    assert package.json()["is_demo"] is True
    assert "DEMO ONLY" in package.json()["warning"]
    assert package.json()["output_path"].startswith("/api/")
    package_download = client.get(package.json()["output_path"])
    assert package_download.status_code == 200
    assert package_download.json()["episode"]["id"] == episode_id
    assert (
        client.get(f"/api/episodes/{episode_id}").json()["status"]
        == "packaged"
    )


def test_missing_artifact_files_block_render_and_packaging(
    client: TestClient,
    daily_episode: dict,
) -> None:
    episode_id = daily_episode["id"]
    client.post(
        f"/api/episodes/{episode_id}/draft",
        json={"provider": "offline"},
    )
    assert client.post(f"/api/episodes/{episode_id}/approve").status_code == 200
    assert client.post(f"/api/episodes/{episode_id}/voice").status_code == 200
    repository = client.app.state.repository
    settings = client.app.state.settings
    internal = repository.get_episode_internal(episode_id)
    assert internal is not None
    voice_path = resolve_asset(settings, internal["voice_path"])
    voice_path.unlink()

    missing_voice = client.post(f"/api/episodes/{episode_id}/render")

    assert missing_voice.status_code == 409
    assert "unavailable" in missing_voice.json()["detail"]
    assert client.get(
        f"/api/episodes/{episode_id}/voice/file"
    ).status_code == 404

    assert client.post(f"/api/episodes/{episode_id}/voice").status_code == 200
    render = client.post(f"/api/episodes/{episode_id}/render")
    assert render.status_code == 202
    job_id = render.json()["id"]
    job_internal = repository.get_render_job_internal(job_id)
    assert job_internal is not None
    render_path = resolve_asset(settings, job_internal["output_path"])
    render_path.unlink()
    report = client.get(
        f"/api/episodes/{episode_id}/compliance"
    ).json()
    for gate in report["blocking"]:
        assert client.put(
            f"/api/episodes/{episode_id}/compliance/{gate}",
            json={"passed": True},
        ).status_code == 200

    missing_render = client.post(
        f"/api/episodes/{episode_id}/publish-package"
    )

    assert missing_render.status_code == 409
    assert "render artifact is unavailable" in missing_render.json()["detail"]
    assert client.get(
        f"/api/render-jobs/{job_id}/artifact"
    ).status_code == 404


def test_voice_and_render_require_editorial_approval(
    client: TestClient, daily_episode: dict
) -> None:
    episode_id = daily_episode["id"]
    client.post(
        f"/api/episodes/{episode_id}/draft",
        json={"provider": "offline"},
    )

    voice = client.post(f"/api/episodes/{episode_id}/voice")
    render = client.post(f"/api/episodes/{episode_id}/render")

    assert voice.status_code == 409
    assert "approve" in voice.json()["detail"]
    assert render.status_code == 409
    assert "approve" in render.json()["detail"]


def test_editorial_change_invalidates_voice_and_render(
    client: TestClient, daily_episode: dict
) -> None:
    episode_id = daily_episode["id"]
    client.post(
        f"/api/episodes/{episode_id}/draft",
        json={"provider": "offline"},
    )
    assert client.post(f"/api/episodes/{episode_id}/approve").status_code == 200
    assert client.post(f"/api/episodes/{episode_id}/voice").status_code == 200
    render = client.post(f"/api/episodes/{episode_id}/render")
    assert render.status_code == 202
    job_id = render.json()["id"]
    assert client.get(f"/api/render-jobs/{job_id}").json()["status"] == "complete"

    changed = client.patch(
        f"/api/episodes/{episode_id}",
        json={"angle": "A newer human angle invalidates production artifacts"},
    )

    assert changed.status_code == 200
    assert changed.json()["status"] == "draft"
    invalidated = client.get(f"/api/render-jobs/{job_id}").json()
    assert invalidated["status"] == "failed"
    assert invalidated["stage"] == "invalidated"
    assert client.post(f"/api/episodes/{episode_id}/approve").status_code == 200
    rerender = client.post(f"/api/episodes/{episode_id}/render")
    assert rerender.status_code == 409
    assert "voice artifact" in rerender.json()["detail"]


def test_latest_render_job_order_is_deterministic(
    client: TestClient, daily_episode: dict
) -> None:
    episode_id = daily_episode["id"]
    client.post(
        f"/api/episodes/{episode_id}/draft",
        json={"provider": "offline"},
    )
    client.post(f"/api/episodes/{episode_id}/approve")
    client.post(f"/api/episodes/{episode_id}/voice")

    first = client.post(f"/api/episodes/{episode_id}/render").json()
    second = client.post(f"/api/episodes/{episode_id}/render").json()
    latest = client.app.state.repository.latest_render_job(episode_id)

    assert first["id"] != second["id"]
    assert latest is not None
    assert latest.id == second["id"]


def test_optional_anthropic_requires_configuration(
    client: TestClient, daily_episode: dict
) -> None:
    response = client.post(
        f"/api/episodes/{daily_episode['id']}/draft",
        json={"provider": "anthropic"},
    )
    assert response.status_code == 503
    assert "ANTHROPIC_API_KEY" in response.json()["detail"]


def test_invalid_anthropic_payload_does_not_corrupt_episode(
    client: TestClient,
    daily_episode: dict,
    monkeypatch,
) -> None:
    episode_id = daily_episode["id"]
    client.app.state.settings.anthropic_api_key = "test-key"

    async def invalid_provider(*_args, **_kwargs):
        return {
            "script": "This payload must never be committed.",
            "sections": {
                "hook": "Hook.",
                "story_1": "Story one.",
                "story_2": "Story two.",
                "story_3": "Story three.",
                "take": "Take.",
                "sign_off": "Sign off.",
            },
            "title": "Invalid provider payload",
            "description": "Invalid",
            "hashtags": "not-a-list",
            "overlays": [],
            "cues": [],
            "word_count": 7,
            "runtime_seconds": 3,
        }

    monkeypatch.setattr(
        main_module,
        "create_anthropic_draft",
        invalid_provider,
    )

    response = client.post(
        f"/api/episodes/{episode_id}/draft",
        json={"provider": "anthropic"},
    )

    assert response.status_code == 502
    stored = client.get(f"/api/episodes/{episode_id}")
    assert stored.status_code == 200
    assert stored.json()["script"] == ""
    assert "invalid episode payload" in response.json()["detail"]


def test_approval_requires_exact_publish_metadata(
    client: TestClient,
    daily_episode: dict,
) -> None:
    episode_id = daily_episode["id"]
    drafted = client.post(
        f"/api/episodes/{episode_id}/draft",
        json={"provider": "offline"},
    ).json()
    malformed_cues = list(drafted["cues"])
    malformed_cues[0] = {**malformed_cues[0], "broll_id": 99}

    patched = client.patch(
        f"/api/episodes/{episode_id}",
        json={
            "hashtags": ["#OnlyOne"],
            "overlays": [],
            "cues": malformed_cues,
        },
    )
    assert patched.status_code == 200

    approval = client.post(f"/api/episodes/{episode_id}/approve")

    assert approval.status_code == 409
    errors = approval.json()["detail"]["errors"]
    assert "provide exactly five unique hashtags" in errors
    assert any("four ordered timed overlays" in error for error in errors)
    assert any("B-roll cues" in error for error in errors)


def test_seed_remains_idempotent_across_app_restarts(
    settings: Settings,
) -> None:
    first = create_app(settings)
    with TestClient(first) as first_client:
        assert len(first_client.get("/api/stories").json()) == 3
    second = create_app(settings)
    with TestClient(second) as second_client:
        stories = second_client.get("/api/stories").json()
        assert len(stories) == 3
        assert len({story["id"] for story in stories}) == 3


def test_unknown_resources_and_invalid_compliance_gate(
    client: TestClient, daily_episode: dict
) -> None:
    assert client.get("/api/episodes/missing").status_code == 404
    assert client.get("/api/render-jobs/missing").status_code == 404
    invalid_gate = client.put(
        f"/api/episodes/{daily_episode['id']}/compliance/not-a-gate",
        json={"passed": True},
    )
    assert invalid_gate.status_code == 404
    assert "available" in invalid_gate.json()["detail"]
