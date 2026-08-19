from __future__ import annotations

import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from newsroom_api.config import Settings
from newsroom_api.main import create_app


@pytest.fixture
def api_root() -> Iterator[Path]:
    tests_dir = Path(__file__).resolve().parent
    root = Path(tempfile.mkdtemp(prefix=".runtime-", dir=tests_dir))
    try:
        yield root
    finally:
        resolved_root = root.resolve()
        if resolved_root.parent == tests_dir.resolve() and resolved_root.name.startswith(
            ".runtime-"
        ):
            shutil.rmtree(resolved_root)


@pytest.fixture
def settings(api_root: Path) -> Settings:
    return Settings(
        api_root=api_root,
        data_dir=api_root / "data",
        assets_dir=api_root / "assets",
        database_path=api_root / "data" / "test.sqlite3",
        live_research=False,
        request_timeout_seconds=0.2,
        anthropic_api_key=None,
        elevenlabs_api_key=None,
        elevenlabs_voice_id=None,
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client


def selected_story_ids(client: TestClient, count: int = 3) -> list[str]:
    stories = client.get("/api/stories", params={"selected": True}).json()
    return [story["id"] for story in stories[:count]]


@pytest.fixture
def daily_episode(client: TestClient) -> dict:
    response = client.post(
        "/api/episodes",
        json={
            "kind": "daily",
            "angle": "Human editorial judgment remains part of the workflow",
            "story_ids": selected_story_ids(client),
        },
    )
    assert response.status_code == 201
    return response.json()
