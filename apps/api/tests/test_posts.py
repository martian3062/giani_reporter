"""Post Studio: prompt -> image -> human review -> Instagram."""

from __future__ import annotations

import asyncio
import io
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from newsroom_api import instagram as instagram_module
from newsroom_api import post_pipeline
from newsroom_api.config import Settings
from newsroom_api.imaging import (
    FORMAT_SPECS,
    GeneratedImage,
    normalize_for_instagram,
)
from newsroom_api.main import create_app
from newsroom_api.media_host import media_host_readiness
from newsroom_api.providers import ProviderError
from newsroom_api.posts import (
    AI_DISCLOSURE,
    calculate_checks,
    create_plan,
    full_caption,
)


def make_post(client: TestClient, **overrides: Any) -> dict[str, Any]:
    payload = {
        "prompt": "A quiet server room at dawn, blue light on the racks",
        "format": "feed_square",
        **overrides,
    }
    response = client.post("/api/posts", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------


def test_prompt_generates_a_reviewable_post_with_offline_providers(
    client: TestClient,
) -> None:
    post = make_post(client)
    # TestClient runs background tasks before the response is handed back.
    assert post["status"] in {"generating", "review"}

    post = client.get(f"/api/posts/{post['id']}").json()
    assert post["status"] == "review", post["error"]
    assert post["headline"]
    assert AI_DISCLOSURE in post["caption"]
    assert post["alt_text"]
    assert 3 <= len(post["hashtags"]) <= 30
    assert len(post["assets"]) == 1

    asset = post["assets"][0]
    assert asset["provider"] == "offline"
    assert asset["is_demo"] is True
    assert (asset["width"], asset["height"]) == FORMAT_SPECS["feed_square"]["size"]
    assert asset["mime"] == "image/jpeg"
    assert asset["post_revision"] == post["revision"]

    preview = client.get(asset["preview_path"])
    assert preview.status_code == 200
    assert preview.headers["content-type"] == "image/jpeg"


def test_carousel_generates_one_slide_per_prompt(client: TestClient) -> None:
    post = make_post(client, format="carousel", slides=3)
    post = client.get(f"/api/posts/{post['id']}").json()
    assert post["status"] == "review", post["error"]
    assert len(post["image_prompts"]) == 3
    assert len(post["assets"]) == 3
    assert [asset["position"] for asset in post["assets"]] == [0, 1, 2]
    for asset in post["assets"]:
        assert (asset["width"], asset["height"]) == FORMAT_SPECS["carousel"]["size"]


def test_reel_refuses_image_generation_and_records_the_reason(
    client: TestClient,
) -> None:
    post = make_post(client, format="reel")
    post = client.get(f"/api/posts/{post['id']}").json()
    assert post["status"] == "planning"
    assert "video" in post["error"]
    assert post["assets"] == []


def test_regeneration_replaces_slides_and_deletes_the_old_files(
    client: TestClient, settings: Settings
) -> None:
    post = client.get(f"/api/posts/{make_post(client)['id']}").json()
    first = post["assets"][0]
    first_path = settings.assets_dir / "posts" / post["id"]
    before = {item.name for item in first_path.iterdir()}

    response = client.post(
        f"/api/posts/{post['id']}/generate", json={"redraft": False}
    )
    assert response.status_code == 202

    post = client.get(f"/api/posts/{post['id']}").json()
    assert post["status"] == "review"
    assert len(post["assets"]) == 1
    assert post["assets"][0]["id"] != first["id"]
    after = {item.name for item in first_path.iterdir()}
    assert before.isdisjoint(after), "the superseded slide file was left behind"


# ---------------------------------------------------------------------------
# Direction provider tier selection
# ---------------------------------------------------------------------------


def test_auto_falls_offline_with_no_key_configured(settings: Settings) -> None:
    plan, provider = asyncio.run(
        create_plan(settings, "a prompt", "feed_square", 1, provider="auto")
    )
    assert provider == "offline"
    assert plan["image_prompts"]


def test_auto_prefers_openai_when_only_openai_is_configured(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings.openai_api_key = "sk-test"

    async def fake_openai(_settings, prompt, post_format, slides):
        return {
            "headline": "OpenAI headline",
            "image_prompts": ["an openai prompt"] * slides,
            "caption": f"Body.\n\n{AI_DISCLOSURE}",
            "hashtags": ["#AI"],
            "alt_text": "alt",
            "ai_disclosure": AI_DISCLOSURE,
        }

    monkeypatch.setattr(
        "newsroom_api.posts._DIRECTION_PROVIDERS",
        {"openai": fake_openai, "anthropic": None},
    )
    plan, provider = asyncio.run(
        create_plan(settings, "a prompt", "feed_square", 1, provider="auto")
    )
    assert provider == "openai"
    assert plan["headline"] == "OpenAI headline"


def test_auto_prefers_anthropic_over_openai_when_both_are_configured(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings.anthropic_api_key = "sk-ant-test"
    settings.openai_api_key = "sk-test"
    calls: list[str] = []

    async def fake_anthropic(_settings, prompt, post_format, slides):
        calls.append("anthropic")
        return {
            "headline": "H",
            "image_prompts": ["p"] * slides,
            "caption": AI_DISCLOSURE,
            "hashtags": ["#AI"],
            "alt_text": "alt",
            "ai_disclosure": AI_DISCLOSURE,
        }

    async def fake_openai(_settings, prompt, post_format, slides):
        calls.append("openai")
        raise AssertionError("openai should not run when anthropic succeeds")

    monkeypatch.setattr(
        "newsroom_api.posts._DIRECTION_PROVIDERS",
        {"anthropic": fake_anthropic, "openai": fake_openai},
    )
    _, provider = asyncio.run(
        create_plan(settings, "a prompt", "feed_square", 1, provider="auto")
    )
    assert provider == "anthropic"
    assert calls == ["anthropic"]


def test_auto_falls_through_to_openai_when_anthropic_fails(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings.anthropic_api_key = "sk-ant-test"
    settings.openai_api_key = "sk-test"

    async def failing_anthropic(*_args):
        raise ProviderError("Anthropic is overloaded")

    async def fake_openai(_settings, prompt, post_format, slides):
        return {
            "headline": "Recovered",
            "image_prompts": ["p"] * slides,
            "caption": AI_DISCLOSURE,
            "hashtags": ["#AI"],
            "alt_text": "alt",
            "ai_disclosure": AI_DISCLOSURE,
        }

    monkeypatch.setattr(
        "newsroom_api.posts._DIRECTION_PROVIDERS",
        {"anthropic": failing_anthropic, "openai": fake_openai},
    )
    plan, provider = asyncio.run(
        create_plan(settings, "a prompt", "feed_square", 1, provider="auto")
    )
    assert provider == "openai"
    assert plan["headline"] == "Recovered"


def test_explicit_openai_without_a_key_raises_instead_of_falling_back(
    settings: Settings,
) -> None:
    with pytest.raises(ProviderError, match="OPENAI_API_KEY"):
        asyncio.run(
            create_plan(settings, "a prompt", "feed_square", 1, provider="openai")
        )


def test_explicit_provider_failure_never_falls_back_to_offline(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings.openai_api_key = "sk-test"

    async def failing_openai(*_args):
        raise ProviderError("rate limited")

    monkeypatch.setattr(
        "newsroom_api.posts._DIRECTION_PROVIDERS",
        {"anthropic": None, "openai": failing_openai},
    )
    with pytest.raises(ProviderError, match="rate limited"):
        asyncio.run(
            create_plan(settings, "a prompt", "feed_square", 1, provider="openai")
        )


def test_post_creation_accepts_openai_as_a_direction_provider(
    client: TestClient,
) -> None:
    post = make_post(client, direction_provider="openai", generate=False)
    assert post["direction_provider"] == "openai"


# ---------------------------------------------------------------------------
# Editing and review gates
# ---------------------------------------------------------------------------


def test_caption_edit_keeps_slides_but_revokes_approval(
    client: TestClient,
) -> None:
    post = client.get(f"/api/posts/{make_post(client)['id']}").json()
    asset_id = post["assets"][0]["id"]

    response = client.patch(
        f"/api/posts/{post['id']}",
        json={"caption": f"A tightened caption.\n\n{AI_DISCLOSURE}"},
    )
    assert response.status_code == 200
    edited = response.json()

    assert edited["revision"] == post["revision"] + 1
    assert edited["status"] == "review"
    assert [asset["id"] for asset in edited["assets"]] == [asset_id]
    assert edited["assets"][0]["post_revision"] == edited["revision"]
    assert edited["checks"]["assets_current"] is True
    assert edited["checks"]["human_reviewed"] is False


def test_prompt_edit_invalidates_the_existing_slides(
    client: TestClient,
) -> None:
    post = client.get(f"/api/posts/{make_post(client)['id']}").json()
    response = client.patch(
        f"/api/posts/{post['id']}", json={"prompt": "A completely new scene"}
    )
    assert response.status_code == 200
    edited = response.json()

    assert edited["status"] == "planning"
    assert edited["assets"][0]["post_revision"] < edited["revision"]
    assert edited["checks"]["assets_current"] is False


def test_a_demo_placeholder_can_never_be_approved(client: TestClient) -> None:
    post = client.get(f"/api/posts/{make_post(client)['id']}").json()
    assert post["assets"][0]["is_demo"] is True

    response = client.post(f"/api/posts/{post['id']}/approve")
    assert response.status_code == 409
    errors = response.json()["detail"]["errors"]
    assert any("demo placeholder" in error for error in errors)


def test_checks_reject_a_caption_that_drops_the_ai_disclosure() -> None:
    post = {
        "id": "post-1",
        "prompt": "a prompt",
        "format": "feed_square",
        "caption": "No disclosure here",
        "hashtags": ["#AI"],
        "alt_text": "alt",
        "revision": 1,
        "approved_revision": 1,
    }
    assets = [{"post_revision": 1, "is_demo": False}]
    checks = calculate_checks(post, assets)
    assert checks["ai_disclosure"] is False
    assert checks["human_reviewed"] is False


@pytest.mark.parametrize(
    ("caption", "failing_check"),
    [
        (f"You should buy Acme shares now.\n\n{AI_DISCLOSURE}", "advice_safe"),
        (f"I am Doctor Mira, an expert.\n\n{AI_DISCLOSURE}", "neutral_anchor"),
    ],
)
def test_checks_catch_advice_and_credential_framing(
    caption: str, failing_check: str
) -> None:
    post = {
        "id": "post-1",
        "prompt": "a prompt",
        "format": "feed_square",
        "caption": caption,
        "hashtags": ["#AI"],
        "alt_text": "alt",
        "revision": 1,
        "approved_revision": 1,
    }
    checks = calculate_checks(post, [{"post_revision": 1, "is_demo": False}])
    assert checks[failing_check] is False


def test_hashtag_rules_are_enforced() -> None:
    base = {
        "id": "post-1",
        "prompt": "a prompt",
        "format": "feed_square",
        "caption": AI_DISCLOSURE,
        "alt_text": "alt",
        "revision": 1,
        "approved_revision": 1,
    }
    assets = [{"post_revision": 1, "is_demo": False}]
    assert calculate_checks({**base, "hashtags": ["#AI", "#AI"]}, assets)[
        "hashtag_count"
    ] is False
    assert calculate_checks({**base, "hashtags": ["AI"]}, assets)[
        "hashtag_count"
    ] is False
    assert calculate_checks({**base, "hashtags": ["#AI Desk"]}, assets)[
        "hashtag_count"
    ] is False
    assert calculate_checks({**base, "hashtags": ["#AI", "#Desk"]}, assets)[
        "hashtag_count"
    ] is True


def test_full_caption_appends_the_hashtag_block() -> None:
    assert full_caption("Body.", ["#AI", "#Desk"]) == "Body.\n\n#AI #Desk"
    assert full_caption("Body.", []) == "Body."


# ---------------------------------------------------------------------------
# Uploads
# ---------------------------------------------------------------------------


def png_bytes(width: int = 1600, height: int = 900) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (20, 40, 90)).save(buffer, format="PNG")
    return buffer.getvalue()


def use_real_image_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stand in for a configured image API so slides are not demo placeholders."""

    async def fake_generate(_settings: Any, **kwargs: Any) -> Any:
        return GeneratedImage(
            data=png_bytes(1400, 1400),
            provider="test-provider",
            mime="image/png",
            is_demo=False,
        )

    monkeypatch.setattr(post_pipeline, "generate_image", fake_generate)


def test_uploaded_photo_becomes_a_real_publishable_slide(
    client: TestClient,
) -> None:
    post = make_post(client, generate=False)
    response = client.post(
        f"/api/posts/{post['id']}/upload",
        files={"file": ("shot.png", png_bytes(), "image/png")},
        data={"kind": "image"},
    )
    assert response.status_code == 200, response.text
    uploaded = response.json()

    assert uploaded["status"] == "review"
    assert len(uploaded["assets"]) == 1
    asset = uploaded["assets"][0]
    assert asset["provider"] == "upload"
    assert asset["is_demo"] is False
    assert (asset["width"], asset["height"]) == FORMAT_SPECS["feed_square"]["size"]
    assert uploaded["checks"]["no_demo_assets"] is True


def test_upload_rejects_a_file_that_is_not_an_image(client: TestClient) -> None:
    post = make_post(client, generate=False)
    response = client.post(
        f"/api/posts/{post['id']}/upload",
        files={"file": ("notes.txt", b"this is not an image", "text/plain")},
        data={"kind": "image"},
    )
    assert response.status_code == 422
    assert "readable image" in response.json()["detail"]


def test_video_upload_is_refused_for_a_feed_post(client: TestClient) -> None:
    post = make_post(client, generate=False)
    response = client.post(
        f"/api/posts/{post['id']}/upload",
        files={"file": ("clip.mp4", b"\x00\x00\x00\x18ftypmp42", "video/mp4")},
        data={"kind": "video"},
    )
    assert response.status_code == 422
    assert "reel or story" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("post_format", sorted(FORMAT_SPECS))
def test_every_format_normalizes_to_its_exact_instagram_box(
    post_format: str,
) -> None:
    encoded, width, height = normalize_for_instagram(
        png_bytes(1234, 567), post_format
    )
    assert (width, height) == FORMAT_SPECS[post_format]["size"]
    with Image.open(io.BytesIO(encoded)) as image:
        assert image.format == "JPEG"
        assert image.size == FORMAT_SPECS[post_format]["size"]


def test_normalization_center_crops_rather_than_stretching() -> None:
    source = Image.new("RGB", (2000, 500), (0, 0, 0))
    for x in range(900, 1100):
        for y in range(200, 300):
            source.putpixel((x, y), (255, 0, 0))
    buffer = io.BytesIO()
    source.save(buffer, format="PNG")

    encoded, _, _ = normalize_for_instagram(buffer.getvalue(), "feed_square")
    with Image.open(io.BytesIO(encoded)) as image:
        red, _, _ = image.convert("RGB").getpixel((540, 540))
    assert red > 180, "the centre of the source should survive a centre crop"


# ---------------------------------------------------------------------------
# Publish gates
# ---------------------------------------------------------------------------


def approved_post(client: TestClient) -> dict[str, Any]:
    post = make_post(client, generate=False)
    client.post(
        f"/api/posts/{post['id']}/upload",
        files={"file": ("shot.png", png_bytes(), "image/png")},
        data={"kind": "image"},
    )
    client.patch(
        f"/api/posts/{post['id']}",
        json={
            "headline": "Server rooms at dawn",
            "caption": f"Server rooms at dawn.\n\n{AI_DISCLOSURE}",
            "hashtags": ["#AI", "#Infrastructure", "#Datacenter"],
            "alt_text": "A dark server room lit by blue indicator lights.",
        },
    )
    response = client.post(f"/api/posts/{post['id']}/approve")
    assert response.status_code == 200, response.text
    return response.json()


def test_publish_is_blocked_until_every_gate_clears(client: TestClient) -> None:
    post = approved_post(client)
    preview = client.get(f"/api/posts/{post['id']}/publish-preview").json()

    assert preview["ready"] is False
    blockers = " | ".join(preview["blockers"])
    assert "INSTAGRAM_PUBLISH_ENABLED" in blockers
    assert "INSTAGRAM_USER_ID" in blockers
    assert "NEWSROOM_PUBLIC_BASE_URL" in blockers

    response = client.post(
        f"/api/posts/{post['id']}/publish",
        json={"confirm": True, "expected_revision": post["revision"]},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["blockers"]


def test_publish_refuses_a_revision_the_reviewer_did_not_see(
    client: TestClient,
) -> None:
    post = approved_post(client)
    response = client.post(
        f"/api/posts/{post['id']}/publish",
        json={"confirm": True, "expected_revision": post["revision"] + 1},
    )
    assert response.status_code == 409
    assert "changed since it was reviewed" in response.json()["detail"]


def test_editing_after_approval_revokes_the_approval(client: TestClient) -> None:
    post = approved_post(client)
    assert post["status"] == "approved"
    assert post["approved_revision"] == post["revision"]

    edited = client.patch(
        f"/api/posts/{post['id']}",
        json={"caption": f"Reworded.\n\n{AI_DISCLOSURE}"},
    ).json()
    assert edited["status"] == "review"
    assert edited["approved_revision"] < edited["revision"]
    assert edited["checks"]["human_reviewed"] is False


def publishing_settings(settings: Settings) -> Settings:
    settings.instagram_publish_enabled = True
    settings.instagram_user_id = "1784000000000000"
    settings.instagram_access_token = "test-token"
    settings.public_base_url = "https://desk.example.com"
    settings.instagram_poll_interval_seconds = 0
    return settings


class FakeInstagram:
    """Records the exact Graph API calls a publish would make."""

    def __init__(self, settings: Settings, *, fail_on: str = "") -> None:
        self.settings = settings
        self.fail_on = fail_on
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.published: list[str] = []

    @property
    def user_id(self) -> str:
        return self.settings.instagram_user_id

    async def create_image_container(self, **kwargs: Any) -> str:
        self.calls.append(("image_container", kwargs))
        if self.fail_on == "container":
            raise instagram_module.InstagramError(
                "HTTP 400: The image_url is not reachable"
            )
        return f"container-{len(self.calls)}"

    async def create_carousel_container(self, **kwargs: Any) -> str:
        self.calls.append(("carousel_container", kwargs))
        return "container-carousel"

    async def create_video_container(self, **kwargs: Any) -> str:
        self.calls.append(("video_container", kwargs))
        return "container-video"

    async def wait_for_container(self, container_id: str, **_: Any) -> None:
        self.calls.append(("wait", {"container_id": container_id}))

    async def publish(self, container_id: str) -> str:
        self.calls.append(("publish", {"container_id": container_id}))
        if self.fail_on == "publish":
            raise instagram_module.InstagramError("HTTP 400: quota exceeded")
        media_id = f"media-{len(self.published) + 1}"
        self.published.append(media_id)
        return media_id

    async def media_details(self, media_id: str) -> dict[str, Any]:
        return {"id": media_id, "permalink": f"https://instagr.am/p/{media_id}"}


@pytest.fixture
def publishing_client(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> Any:
    publishing_settings(settings)
    created: dict[str, FakeInstagram] = {}

    def factory(passed_settings: Settings) -> FakeInstagram:
        fake = FakeInstagram(passed_settings, fail_on=created.get("fail_on", ""))  # type: ignore[arg-type]
        created["client"] = fake
        return fake

    monkeypatch.setattr(post_pipeline, "InstagramClient", factory)
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client, created, settings


def test_a_configured_desk_publishes_once_and_records_the_permalink(
    publishing_client: Any,
) -> None:
    client, created, _ = publishing_client
    post = approved_post(client)

    response = client.post(
        f"/api/posts/{post['id']}/publish",
        json={"confirm": True, "expected_revision": post["revision"]},
    )
    assert response.status_code == 200, response.text
    published = response.json()

    assert published["status"] == "published"
    publication = published["publications"][0]
    assert publication["status"] == "published"
    assert publication["media_id"] == "media-1"
    assert publication["permalink"] == "https://instagr.am/p/media-1"

    fake = created["client"]
    assert [name for name, _ in fake.calls] == [
        "image_container",
        "wait",
        "publish",
    ]
    container_args = fake.calls[0][1]
    assert container_args["image_url"].startswith(
        "https://desk.example.com/api/public/media/"
    )
    assert AI_DISCLOSURE in container_args["caption"]
    assert container_args["caption"].endswith("#AI #Infrastructure #Datacenter")
    assert container_args["alt_text"]


def test_a_published_post_is_frozen(publishing_client: Any) -> None:
    client, _, _ = publishing_client
    post = approved_post(client)
    client.post(
        f"/api/posts/{post['id']}/publish",
        json={"confirm": True, "expected_revision": post["revision"]},
    )

    edit = client.patch(
        f"/api/posts/{post['id']}", json={"caption": "Rewritten after the fact"}
    )
    assert edit.status_code == 409
    assert "live on Instagram" in edit.json()["detail"]

    regenerate = client.post(f"/api/posts/{post['id']}/generate")
    assert regenerate.status_code == 409

    upload = client.post(
        f"/api/posts/{post['id']}/upload",
        files={"file": ("shot.png", png_bytes(), "image/png")},
        data={"kind": "image"},
    )
    assert upload.status_code == 409


def test_a_second_publish_of_the_same_revision_is_refused(
    publishing_client: Any,
) -> None:
    client, created, _ = publishing_client
    post = approved_post(client)
    body = {"confirm": True, "expected_revision": post["revision"]}

    assert client.post(f"/api/posts/{post['id']}/publish", json=body).status_code == 200
    repeat = client.post(f"/api/posts/{post['id']}/publish", json=body)

    assert repeat.status_code == 409
    assert "already live on Instagram" in " ".join(
        repeat.json()["detail"]["blockers"]
    )
    assert len(created["client"].published) == 1


def test_the_database_refuses_a_second_publish_record_for_one_revision(
    publishing_client: Any,
) -> None:
    """The status check can be raced; the unique index cannot."""
    client, _, _ = publishing_client
    post = approved_post(client)
    repository = client.app.state.repository

    first = repository.create_publication(
        {
            "id": "pub-first",
            "post_id": post["id"],
            "status": "pending",
            "post_revision": post["revision"],
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        }
    )
    assert first is not None

    second = repository.create_publication(
        {
            "id": "pub-second",
            "post_id": post["id"],
            "status": "pending",
            "post_revision": post["revision"],
            "created_at": "2026-01-01T00:00:01Z",
            "updated_at": "2026-01-01T00:00:01Z",
        }
    )
    assert second is None, "a second live attempt for one revision must be refused"

    repository.fail_publication(
        first["id"],
        post_id=post["id"],
        error="network reset",
        timestamp="2026-01-01T00:00:02Z",
    )
    retry = repository.create_publication(
        {
            "id": "pub-retry",
            "post_id": post["id"],
            "status": "pending",
            "post_revision": post["revision"],
            "created_at": "2026-01-01T00:00:03Z",
            "updated_at": "2026-01-01T00:00:03Z",
        }
    )
    assert retry is not None, "a failed attempt must be retryable"


def test_a_failed_publish_returns_the_post_to_approved_and_allows_a_retry(
    publishing_client: Any,
) -> None:
    client, created, _ = publishing_client
    created["fail_on"] = "container"
    post = approved_post(client)
    body = {"confirm": True, "expected_revision": post["revision"]}

    failed = client.post(f"/api/posts/{post['id']}/publish", json=body)
    assert failed.status_code == 502
    assert "not reachable" in failed.json()["detail"]

    state = client.get(f"/api/posts/{post['id']}").json()
    assert state["status"] == "approved"
    assert state["publications"][0]["status"] == "failed"

    created["fail_on"] = ""
    retried = client.post(f"/api/posts/{post['id']}/publish", json=body)
    assert retried.status_code == 200
    assert retried.json()["status"] == "published"


def test_publishing_a_carousel_creates_children_then_the_parent(
    publishing_client: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, created, _ = publishing_client
    use_real_image_provider(monkeypatch)

    post = make_post(client, format="carousel", slides=3)
    state = client.get(f"/api/posts/{post['id']}").json()
    assert state["status"] == "review", state["error"]
    assert len(state["assets"]) == 3
    assert all(asset["is_demo"] is False for asset in state["assets"])

    client.patch(
        f"/api/posts/{post['id']}",
        json={
            "caption": f"Three views of one idea.\n\n{AI_DISCLOSURE}",
            "hashtags": ["#AI", "#Design"],
            "alt_text": "Three related illustrations.",
        },
    )
    approved = client.post(f"/api/posts/{post['id']}/approve").json()
    response = client.post(
        f"/api/posts/{post['id']}/publish",
        json={"confirm": True, "expected_revision": approved["revision"]},
    )
    assert response.status_code == 200, response.text

    fake = created["client"]
    assert [name for name, _ in fake.calls] == [
        "image_container",
        "wait",
        "image_container",
        "wait",
        "image_container",
        "wait",
        "carousel_container",
        "wait",
        "publish",
    ]
    for name, kwargs in fake.calls:
        if name == "image_container":
            assert kwargs["is_carousel_item"] is True
            assert "caption" not in kwargs
    parent = next(kw for name, kw in fake.calls if name == "carousel_container")
    assert len(parent["children"]) == 3
    assert AI_DISCLOSURE in parent["caption"]


def test_a_generated_non_demo_post_publishes_end_to_end(
    publishing_client: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, created, _ = publishing_client
    use_real_image_provider(monkeypatch)

    post = make_post(client, format="feed_portrait")
    state = client.get(f"/api/posts/{post['id']}").json()
    assert state["status"] == "review", state["error"]
    assert state["checks"]["no_demo_assets"] is True

    approved = client.post(f"/api/posts/{post['id']}/approve").json()
    assert approved["status"] == "approved"
    assert approved["checks"]["human_reviewed"] is True

    preview = client.get(f"/api/posts/{post['id']}/publish-preview").json()
    assert preview["ready"] is True, preview["blockers"]
    assert len(preview["media_urls"]) == 1

    published = client.post(
        f"/api/posts/{post['id']}/publish",
        json={"confirm": True, "expected_revision": approved["revision"]},
    ).json()
    assert published["status"] == "published"
    assert published["publications"][0]["permalink"]


def test_public_media_token_serves_the_file_and_rejects_a_bad_token(
    client: TestClient,
) -> None:
    post = make_post(client, generate=False)
    client.post(
        f"/api/posts/{post['id']}/upload",
        files={"file": ("shot.png", png_bytes(), "image/png")},
        data={"kind": "image"},
    )
    # The token is not exposed by the API; read it from the repository.
    repository = client.app.state.repository
    asset = repository.list_post_assets(post["id"])[0]

    served = client.get(f"/api/public/media/{asset['public_token']}.jpg")
    assert served.status_code == 200
    assert served.headers["content-type"] == "image/jpeg"

    assert client.get("/api/public/media/short.jpg").status_code == 404
    assert client.get(f"/api/public/media/{'0' * 40}.jpg").status_code == 404
    assert (
        client.get(f"/api/public/media/{asset['public_token']}.exe").status_code
        == 404
    )


# ---------------------------------------------------------------------------
# Readiness reporting
# ---------------------------------------------------------------------------


def test_media_host_readiness_requires_https(settings: Settings) -> None:
    settings.public_base_url = "http://localhost:8000"
    assert media_host_readiness(settings)["ready"] is False
    settings.public_base_url = "https://desk.example.com"
    assert media_host_readiness(settings)["ready"] is True


def test_capabilities_reports_what_is_missing(client: TestClient) -> None:
    body = client.get("/api/capabilities").json()
    assert body["images"]["resolved_provider"] == "offline"
    assert body["instagram"]["configured"] is False
    assert body["instagram"]["meta_app"]["configured"] is False
    assert body["media_host"]["ready"] is False
    assert {item["id"] for item in body["post_formats"]} == set(FORMAT_SPECS)


def test_meta_env_aliases(monkeypatch: pytest.MonkeyPatch, api_root: Path) -> None:
    monkeypatch.setenv("META_APP_ID", "12345")
    monkeypatch.setenv("META_APP_SECRET", "secret")
    monkeypatch.setenv("META_ACCESS_TOKEN", "meta-token")
    monkeypatch.setenv("META_USER_ID", "1784140000000001")
    monkeypatch.setenv("NEWSROOM_SITE", "desk.example.com")
    monkeypatch.delenv("NEWSROOM_PUBLIC_BASE_URL", raising=False)
    monkeypatch.delenv("INSTAGRAM_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("INSTAGRAM_USER_ID", raising=False)

    loaded = Settings.from_env()
    loaded.api_root = api_root
    loaded.data_dir = api_root / "data"
    loaded.assets_dir = api_root / "assets"
    loaded.database_path = api_root / "data" / "test.sqlite3"

    assert loaded.meta_app_id == "12345"
    assert loaded.meta_app_secret == "secret"
    assert loaded.instagram_access_token == "meta-token"
    assert loaded.instagram_user_id == "1784140000000001"
    assert loaded.public_base_url == "https://desk.example.com"
    assert loaded.meta_app_configured is True
    assert loaded.instagram_configured is True


def test_appsecret_proof_is_deterministic() -> None:
    proof = instagram_module.appsecret_proof("user-token", "app-secret")
    assert proof == instagram_module.appsecret_proof("user-token", "app-secret")
    assert proof != instagram_module.appsecret_proof("other-token", "app-secret")
