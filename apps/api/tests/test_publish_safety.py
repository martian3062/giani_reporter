"""Phase 0 publishing safety: ambiguous outcomes, reconciliation, delivery.

A local database cannot commit Instagram's side of a publish. These tests pin
down what happens when the publish request's outcome is unclear, after a
restart, and when the public media path is wrong or over-exposed.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from newsroom_api import delivery
from newsroom_api import instagram as instagram_module
from newsroom_api import post_pipeline
from newsroom_api.config import Settings
from newsroom_api.main import create_app
from newsroom_api.media_gateway import create_media_gateway
from newsroom_api.post_pipeline import publication_manifest_sha256
from newsroom_api.posts import full_caption
from test_posts import (
    ACCOUNT_ID,
    FakeInstagram,
    approved_post,
    publishing_settings,
)


class ReconcilingInstagram(FakeInstagram):
    """A fake that can time out on publish and answer reconciliation reads."""

    container_states: dict[str, str] = {}
    live_media: list[dict[str, Any]] = []

    async def publish(self, container_id: str) -> str:
        if self.fail_on == "publish_timeout":
            self.calls.append(("publish", {"container_id": container_id}))
            raise instagram_module.InstagramError(
                "Instagram request failed: ReadTimeout", ambiguous=True
            )
        return await super().publish(container_id)

    async def container_status(self, container_id: str) -> str:
        return self.container_states.get(container_id, "IN_PROGRESS")

    async def recent_media(self, limit: int = 25) -> list[dict[str, Any]]:
        return list(self.live_media)

    async def media_details(self, media_id: str) -> dict[str, Any]:
        if not media_id.startswith("media-"):
            raise instagram_module.InstagramError(
                "HTTP 400: Unsupported get request"
            )
        return await super().media_details(media_id)


@pytest.fixture
def desk(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> Any:
    publishing_settings(settings)
    settings.instagram_reconcile_settle_seconds = 0
    state: dict[str, Any] = {"fail_on": ""}
    ReconcilingInstagram.container_states = {}
    ReconcilingInstagram.live_media = []

    def factory(passed: Settings) -> ReconcilingInstagram:
        fake = ReconcilingInstagram(passed, fail_on=state["fail_on"])  # type: ignore[arg-type]
        state["client"] = fake
        return fake

    async def delivery_ok(*_: Any, **__: Any) -> list[str]:
        return []

    monkeypatch.setattr(post_pipeline, "InstagramClient", factory)
    monkeypatch.setattr(delivery, "check_public_delivery", delivery_ok)
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client, state, settings


def publish(client: TestClient, post: dict[str, Any], **overrides: Any) -> Any:
    body = {
        "confirm": True,
        "expected_revision": post["revision"],
        "expected_account_id": ACCOUNT_ID,
        **overrides,
    }
    return client.post(f"/api/posts/{post['id']}/publish", json=body)


def timed_out_post(client: TestClient, state: dict[str, Any]) -> dict[str, Any]:
    """An approved post whose publish request timed out after being sent."""
    state["fail_on"] = "publish_timeout"
    post = approved_post(client)
    response = publish(client, post)
    assert response.status_code == 502, response.text
    assert response.json()["detail"]["outcome"] == "unknown"
    state["fail_on"] = ""
    return client.get(f"/api/posts/{post['id']}").json()


def reconcile(client: TestClient, post: dict[str, Any], **body: Any) -> Any:
    publication = post["publications"][0]
    return client.post(
        f"/api/posts/{post['id']}/publications/{publication['id']}/reconcile",
        json=body,
    )


# ---------------------------------------------------------------------------
# Ambiguous outcomes
# ---------------------------------------------------------------------------


def test_a_timed_out_publish_holds_the_slot_and_refuses_a_retry(desk: Any) -> None:
    client, state, _ = desk
    post = timed_out_post(client, state)

    assert post["status"] == "publishing"
    assert post["publications"][0]["status"] == "unknown_outcome"
    assert "may be live" in post["error"]

    retry = publish(client, post)
    assert retry.status_code == 409
    blockers = " ".join(retry.json()["detail"]["blockers"])
    assert "Reconcile" in blockers
    assert state["client"].published == []

    edit = client.patch(f"/api/posts/{post['id']}", json={"caption": "Changed"})
    assert edit.status_code == 409


def test_a_clear_rejection_of_the_publish_call_releases_the_slot(desk: Any) -> None:
    client, state, _ = desk
    state["fail_on"] = "publish"
    post = approved_post(client)

    failed = publish(client, post)
    assert failed.status_code == 502
    after = client.get(f"/api/posts/{post['id']}").json()
    assert after["status"] == "approved"
    assert after["publications"][0]["status"] == "failed"

    state["fail_on"] = ""
    assert publish(client, post).status_code == 200


def test_a_restart_after_submission_keeps_the_attempt_unresolved(desk: Any) -> None:
    client, _, _ = desk
    repository = client.app.state.repository
    sent = approved_post(client)
    not_sent = approved_post(client)

    for post, status in ((sent, "submitted"), (not_sent, "publishing")):
        record = repository.create_publication(
            {
                "id": f"pub-{post['id']}",
                "post_id": post["id"],
                "status": "pending",
                "post_revision": post["revision"],
                "created_at": "2026-10-03T00:00:00Z",
                "updated_at": "2026-10-03T00:00:00Z",
            }
        )
        assert record is not None
        repository.update_publication(
            record["id"], {"status": "publishing"}, "2026-10-03T00:00:01Z"
        )
        if status == "submitted":
            repository.mark_publication_submitted(
                record["id"], "2026-10-03T00:00:02Z"
            )

    repository.recover_interrupted_publications("2026-10-03T00:01:00Z")

    sent_after = client.get(f"/api/posts/{sent['id']}").json()
    assert sent_after["status"] == "publishing"
    assert sent_after["publications"][0]["status"] == "unknown_outcome"

    not_sent_after = client.get(f"/api/posts/{not_sent['id']}").json()
    assert not_sent_after["status"] == "approved"
    assert not_sent_after["publications"][0]["status"] == "failed"


def test_unresolved_attempts_count_against_the_daily_cap(desk: Any) -> None:
    client, state, _ = desk
    timed_out_post(client, state)
    status = client.get("/api/instagram/status").json()
    assert status["published_today"] == 1


# ---------------------------------------------------------------------------
# Reconciliation
# ---------------------------------------------------------------------------


def test_reconcile_check_records_a_post_that_went_live(desk: Any) -> None:
    client, state, _ = desk
    post = timed_out_post(client, state)
    container = post["publications"][0]["container_id"]
    ReconcilingInstagram.container_states[container] = "PUBLISHED"
    ReconcilingInstagram.live_media = [
        {"id": "other", "caption": "Something else", "permalink": "x"},
        {
            "id": "media-77",
            "caption": full_caption(post["caption"], post["hashtags"]),
            "permalink": "https://instagr.am/p/media-77",
        },
    ]

    response = reconcile(client, post, action="check")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["outcome"] == "published"
    assert body["post"]["status"] == "published"
    assert body["post"]["error"] == ""
    publication = body["post"]["publications"][0]
    assert publication["status"] == "published"
    assert publication["media_id"] == "media-77"
    assert publication["permalink"] == "https://instagr.am/p/media-77"


def test_reconcile_check_records_a_live_post_it_cannot_match(desk: Any) -> None:
    client, state, _ = desk
    post = timed_out_post(client, state)
    container = post["publications"][0]["container_id"]
    ReconcilingInstagram.container_states[container] = "PUBLISHED"

    body = reconcile(client, post, action="check").json()
    assert body["outcome"] == "published"
    assert body["post"]["publications"][0]["media_id"] == ""
    assert "could not be matched" in body["post"]["error"]


def test_reconcile_check_releases_a_container_that_never_published(
    desk: Any,
) -> None:
    client, state, _ = desk
    post = timed_out_post(client, state)
    container = post["publications"][0]["container_id"]
    ReconcilingInstagram.container_states[container] = "FINISHED"

    body = reconcile(client, post, action="check").json()
    assert body["outcome"] == "not_published"
    assert body["post"]["status"] == "approved"
    assert body["post"]["publications"][0]["status"] == "failed"

    retried = publish(client, post)
    assert retried.status_code == 200, retried.text
    assert retried.json()["status"] == "published"


def test_reconcile_waits_out_the_settle_window(desk: Any) -> None:
    client, state, settings = desk
    settings.instagram_reconcile_settle_seconds = 3600
    post = timed_out_post(client, state)
    container = post["publications"][0]["container_id"]
    ReconcilingInstagram.container_states[container] = "FINISHED"

    body = reconcile(client, post, action="check").json()
    assert body["outcome"] == "unresolved"
    assert "Check again in" in body["detail"]
    assert body["post"]["publications"][0]["status"] == "unknown_outcome"


def test_reconcile_check_leaves_an_in_progress_container_unresolved(
    desk: Any,
) -> None:
    client, state, _ = desk
    post = timed_out_post(client, state)

    body = reconcile(client, post, action="check").json()
    assert body["outcome"] == "unresolved"
    assert body["post"]["status"] == "publishing"


def test_releasing_by_hand_needs_the_typed_phrase(desk: Any) -> None:
    client, state, _ = desk
    post = timed_out_post(client, state)

    refused = reconcile(client, post, action="confirm_not_published")
    assert refused.status_code == 409
    assert "NOT PUBLISHED" in refused.json()["detail"]

    released = reconcile(
        client,
        post,
        action="confirm_not_published",
        confirmation="NOT PUBLISHED",
    ).json()
    assert released["outcome"] == "not_published"
    assert released["post"]["status"] == "approved"


def test_confirming_by_hand_verifies_the_media_id(desk: Any) -> None:
    client, state, _ = desk
    post = timed_out_post(client, state)

    unknown = reconcile(
        client, post, action="confirm_published", media_id="not-a-real-id"
    )
    assert unknown.status_code == 409

    confirmed = reconcile(
        client, post, action="confirm_published", media_id="media-9"
    ).json()
    assert confirmed["outcome"] == "published"
    assert confirmed["post"]["publications"][0]["media_id"] == "media-9"


def test_only_an_unknown_outcome_can_be_reconciled(desk: Any) -> None:
    client, _, _ = desk
    post = approved_post(client)
    published = publish(client, post).json()

    response = reconcile(client, published, action="check")
    assert response.status_code == 409


# ---------------------------------------------------------------------------
# Destination binding and manifest
# ---------------------------------------------------------------------------


def test_publish_refuses_a_changed_destination_account(desk: Any) -> None:
    client, state, _ = desk
    post = approved_post(client)

    preview = client.get(f"/api/posts/{post['id']}/publish-preview").json()
    assert preview["destination_account_id"] == ACCOUNT_ID

    response = publish(client, post, expected_account_id="9999")
    assert response.status_code == 409
    assert "destination Instagram account changed" in response.json()["detail"]
    assert "client" not in state


def test_a_publication_records_its_destination_and_manifest(desk: Any) -> None:
    client, _, _ = desk
    post = approved_post(client)
    repository = client.app.state.repository
    assets = repository.list_post_assets(post["id"])
    expected = publication_manifest_sha256(
        repository.get_post(post["id"]), assets, ACCOUNT_ID
    )

    published = publish(client, post).json()
    publication = published["publications"][0]
    assert publication["ig_user_id"] == ACCOUNT_ID
    assert publication["manifest_sha256"] == expected
    assert len(expected) == 64


# ---------------------------------------------------------------------------
# Media-only gateway
# ---------------------------------------------------------------------------


def test_the_gateway_serves_reviewed_media_and_nothing_else(
    client: TestClient, settings: Settings
) -> None:
    post = approved_post(client)
    asset = client.app.state.repository.list_post_assets(post["id"])[0]
    gateway = TestClient(create_media_gateway(settings))
    url = f"/api/public/media/{asset['public_token']}.jpg"

    served = gateway.get(url)
    assert served.status_code == 200
    assert served.headers["content-type"] == "image/jpeg"
    assert served.headers["x-content-type-options"] == "nosniff"
    assert served.content[:3] == b"\xff\xd8\xff"
    assert gateway.head(url).status_code == 200

    for path in (
        "/api/health",
        "/docs",
        "/openapi.json",
        "/redoc",
        "/api/instagram/status",
        f"/api/posts/{post['id']}",
        f"/api/public/media/{'0' * 40}.jpg",
        f"/api/public/media/{asset['public_token']}.mp4",
        "/api/public/media/..%2F..%2Fdata%2Ftest.sqlite3",
    ):
        assert gateway.get(path).status_code == 404, path
    assert gateway.post(url).status_code == 405


# ---------------------------------------------------------------------------
# Delivery preflight
# ---------------------------------------------------------------------------

JPEG = b"\xff\xd8\xff\xe0" + b"0" * 60
MEDIA_URL = "https://media.example.com/api/public/media/" + "a" * 40 + ".jpg"
ASSET = {"mime": "image/jpeg", "bytes": len(JPEG)}


def delivery_settings(settings: Settings) -> Settings:
    settings.public_base_url = "https://media.example.com"
    return settings


def run_delivery(
    settings: Settings, handler: Any, media: list[tuple[str, dict[str, Any]]] | None = None
) -> list[str]:
    import asyncio

    return asyncio.run(
        delivery.check_public_delivery(
            delivery_settings(settings),
            media if media is not None else [(MEDIA_URL, ASSET)],
            transport=httpx.MockTransport(handler),
        )
    )


def gateway_like(request: httpx.Request) -> httpx.Response:
    if str(request.url) == MEDIA_URL:
        return httpx.Response(
            200, content=JPEG, headers={"content-type": "image/jpeg"}
        )
    return httpx.Response(404)


def test_delivery_passes_through_a_media_only_address(settings: Settings) -> None:
    assert run_delivery(settings, gateway_like) == []


def test_delivery_blocks_an_address_that_exposes_the_api(settings: Settings) -> None:
    def whole_api(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/health":
            return httpx.Response(200, json={"status": "ok"})
        return gateway_like(request)

    blockers = run_delivery(settings, whole_api)
    assert len(blockers) == 1
    assert "/api/health" in blockers[0]
    assert "media gateway" in blockers[0]


def test_delivery_accepts_an_authenticated_api_address(settings: Settings) -> None:
    def behind_basic_auth(request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/api/public/media/"):
            return gateway_like(request)
        return httpx.Response(401)

    assert run_delivery(settings, behind_basic_auth) == []


def test_delivery_blocks_a_warning_page_instead_of_image_bytes(
    settings: Settings,
) -> None:
    def interstitial(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, text="<html>Visit site</html>", headers={"content-type": "text/html"}
        )

    blockers = run_delivery(settings, interstitial)
    assert any("serves 'text/html'" in blocker for blocker in blockers)


def test_delivery_blocks_an_unreachable_tunnel(settings: Settings) -> None:
    def offline(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("tunnel is down", request=request)

    blockers = run_delivery(settings, offline)
    assert len(blockers) == 1
    assert "could not be fetched" in blockers[0]


def test_delivery_blocks_a_stale_copy_of_the_file(settings: Settings) -> None:
    def stale(request: httpx.Request) -> httpx.Response:
        if str(request.url) == MEDIA_URL:
            return httpx.Response(
                200,
                content=JPEG + b"extra",
                headers={"content-type": "image/jpeg"},
            )
        return httpx.Response(404)

    blockers = run_delivery(settings, stale)
    assert any("the reviewed file has" in blocker for blocker in blockers)


def test_delivery_blocks_an_address_that_ignores_tokens(settings: Settings) -> None:
    def serves_anything(request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/api/public/media/"):
            return httpx.Response(
                200, content=JPEG, headers={"content-type": "image/jpeg"}
            )
        return httpx.Response(404)

    blockers = run_delivery(settings, serves_anything)
    assert any("invalid token" in blocker for blocker in blockers)


def test_the_preview_reports_delivery_blockers(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    publishing_settings(settings)

    async def exposed(*_: Any, **__: Any) -> list[str]:
        return ["The public address also serves /api/health"]

    monkeypatch.setattr(delivery, "check_public_delivery", exposed)
    with TestClient(create_app(settings)) as client:
        post = approved_post(client)
        preview = client.get(f"/api/posts/{post['id']}/publish-preview").json()
        assert preview["ready"] is False
        assert preview["blockers"] == ["The public address also serves /api/health"]

        response = client.post(
            f"/api/posts/{post['id']}/publish",
            json={
                "confirm": True,
                "expected_revision": post["revision"],
                "expected_account_id": ACCOUNT_ID,
            },
        )
        assert response.status_code == 409


# ---------------------------------------------------------------------------
# Error classification in the real client
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("respond", "ambiguous"),
    [
        (lambda request: httpx.Response(400, json={"error": {"message": "bad"}}), False),
        (lambda request: httpx.Response(500, text="oops"), True),
        (lambda request: httpx.Response(200, json={}), True),
        (lambda request: (_ for _ in ()).throw(httpx.ReadTimeout("slow", request=request)), True),
        (lambda request: (_ for _ in ()).throw(httpx.ConnectError("down", request=request)), False),
    ],
    ids=["http-400", "http-500", "no-media-id", "read-timeout", "connect-error"],
)
def test_publish_errors_are_classified_by_whether_they_may_have_landed(
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    respond: Any,
    ambiguous: bool,
) -> None:
    import asyncio

    publishing_settings(settings)
    real_client = httpx.AsyncClient

    def with_mock_transport(**kwargs: Any) -> httpx.AsyncClient:
        return real_client(transport=httpx.MockTransport(respond), **kwargs)

    monkeypatch.setattr(instagram_module.httpx, "AsyncClient", with_mock_transport)
    client = instagram_module.InstagramClient(settings)

    with pytest.raises(instagram_module.InstagramError) as raised:
        asyncio.run(client.publish("container-1"))
    assert raised.value.ambiguous is ambiguous


def test_the_settle_window_parses_api_timestamps() -> None:
    parsed = post_pipeline._parse_timestamp("2026-10-03T10:00:00.000000Z")
    assert parsed == dt.datetime(2026, 10, 3, 10, tzinfo=dt.timezone.utc)


@pytest.mark.parametrize(
    ("now_utc", "expected"),
    [
        # 01:58 IST on 3 October is still 2 October in UTC.
        ("2026-10-02T20:28:00+00:00", "2026-10-02T18:30:00.000000Z"),
        # 12:00 IST on 3 October.
        ("2026-10-03T06:30:00+00:00", "2026-10-02T18:30:00.000000Z"),
        # 00:10 IST on 4 October starts a new day.
        ("2026-10-03T18:40:00+00:00", "2026-10-03T18:30:00.000000Z"),
    ],
)
def test_the_daily_cap_counts_from_ist_midnight(now_utc: str, expected: str) -> None:
    from newsroom_api.main import ist_day_start_utc

    assert ist_day_start_utc(dt.datetime.fromisoformat(now_utc)) == expected
