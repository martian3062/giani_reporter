from __future__ import annotations

import asyncio
from typing import Any

import pytest

from newsroom_api import providers
from newsroom_api.artifacts import (
    ArtifactError,
    asset_identifier,
    resolve_asset,
)
from newsroom_api.config import Settings
from newsroom_api.providers import (
    ProviderError,
    create_anthropic_draft,
    elevenlabs_speech,
)
from newsroom_api.schemas import Episode, Story
from newsroom_api.research import _deduplicate


def test_research_deduplicates_similar_headlines() -> None:
    stories = [
        {
            "id": "one",
            "title": "Open source model cuts inference costs for developers",
            "url": "https://example.com/one",
            "score": 2.0,
        },
        {
            "id": "two",
            "title": "Open-source model cuts inference cost for developers",
            "url": "https://another.example/two",
            "score": 1.0,
        },
        {
            "id": "three",
            "title": "A separate research release improves speech timing",
            "url": "https://example.com/three",
            "score": 0.8,
        },
    ]

    unique = _deduplicate(stories)

    assert [story["id"] for story in unique] == ["one", "three"]


def test_elevenlabs_uses_output_format_query_parameter(
    monkeypatch: Any,
    tmp_path: Any,
) -> None:
    captured: dict[str, Any] = {}

    class FakeResponse:
        content = b"fake-mp3"

        def raise_for_status(self) -> None:
            return None

    class FakeClient:
        def __init__(self, **_: Any) -> None:
            pass

        async def __aenter__(self) -> "FakeClient":
            return self

        async def __aexit__(self, *_: Any) -> None:
            return None

        async def post(self, url: str, **kwargs: Any) -> FakeResponse:
            captured["url"] = url
            captured.update(kwargs)
            return FakeResponse()

    monkeypatch.setattr(providers.httpx, "AsyncClient", FakeClient)
    settings = Settings(
        api_root=tmp_path,
        data_dir=tmp_path / "data",
        assets_dir=tmp_path / "assets",
        database_path=tmp_path / "data" / "newsroom.sqlite3",
        elevenlabs_api_key="test-key",
        elevenlabs_voice_id="voice-id",
    )

    audio = asyncio.run(elevenlabs_speech(settings, "A short test."))

    assert audio == b"fake-mp3"
    assert captured["params"] == {"output_format": "mp3_44100_192"}
    assert "output_format" not in captured["json"]


def test_anthropic_rejects_malformed_response_envelope(
    monkeypatch: Any,
    tmp_path: Any,
) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> list[Any]:
            return []

    class FakeClient:
        def __init__(self, **_: Any) -> None:
            pass

        async def __aenter__(self) -> "FakeClient":
            return self

        async def __aexit__(self, *_: Any) -> None:
            return None

        async def post(self, *_args: Any, **_kwargs: Any) -> FakeResponse:
            return FakeResponse()

    monkeypatch.setattr(providers.httpx, "AsyncClient", FakeClient)
    settings = Settings(
        api_root=tmp_path,
        data_dir=tmp_path / "data",
        assets_dir=tmp_path / "assets",
        database_path=tmp_path / "data" / "newsroom.sqlite3",
        anthropic_api_key="test-key",
    )
    episode = Episode(
        id="episode",
        kind="deep_dive",
        status="planning",
        date="2026-01-01",
        angle="A human editorial angle",
        story_ids=["story"],
        script="",
        sections={},
        title="",
        description="",
        hashtags=[],
        overlays=[],
        cues=[],
        word_count=0,
        runtime_seconds=0,
        compliance={},
        updated_at="2026-01-01T00:00:00Z",
    )
    story = Story(
        id="story",
        title="A source title",
        url="https://example.invalid/story",
        source="Example",
        published_at="2026-01-01T00:00:00Z",
        summary="A supplied summary",
        why_it_matters="A supplied reason",
        score=1,
        selected=True,
        topic="AI",
        is_demo=True,
    )

    with pytest.raises(ProviderError, match="invalid response envelope"):
        asyncio.run(create_anthropic_draft(settings, episode, [story]))


def test_artifact_identifiers_are_portable_and_traversal_safe(
    tmp_path: Any,
) -> None:
    assets = tmp_path / "assets"
    file_path = assets / "voices" / "episode.txt"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("artifact", encoding="utf-8")
    settings = Settings(
        api_root=tmp_path,
        data_dir=tmp_path / "data",
        assets_dir=assets,
        database_path=tmp_path / "data" / "newsroom.sqlite3",
    )

    identifier = asset_identifier(settings, file_path)

    assert identifier == "voices/episode.txt"
    assert resolve_asset(settings, identifier) == file_path.resolve()
    with pytest.raises(ArtifactError, match="escapes"):
        resolve_asset(settings, "../outside.txt")
    assert resolve_asset(settings, str(file_path.resolve())) == file_path.resolve()
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    with pytest.raises(ArtifactError, match="escapes"):
        resolve_asset(settings, str(outside.resolve()))
    with pytest.raises(ArtifactError, match="missing"):
        resolve_asset(settings, "voices/deleted.txt")
