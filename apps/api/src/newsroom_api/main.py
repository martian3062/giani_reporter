from __future__ import annotations

import datetime as dt
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

from fastapi import (
    BackgroundTasks,
    Body,
    FastAPI,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import ValidationError

from .artifacts import ArtifactError, resolve_asset, sha256_file
from .config import Settings
from .database import DEMO_STORIES, Repository
from .editorial import (
    COMPLIANCE_GATES,
    approval_errors,
    build_offline_draft,
    calculate_compliance,
    count_words,
    default_compliance,
    join_sections,
    production_metadata_errors,
    runtime_seconds,
)
from .imaging import FORMAT_SPECS
from .instagram import (
    InstagramError,
    diagnose as diagnose_instagram,
    exchange_long_lived_token,
    refresh_long_lived_token,
)
from .media_host import media_host_readiness
from .post_pipeline import (
    PipelineError,
    generate_assets,
    preview_path,
    publish_to_instagram,
    register_uploaded_asset,
)
from .posts import (
    CHECK_LABELS,
    POST_CHECKS,
    calculate_checks,
    create_plan,
    default_checks,
    full_caption,
)
from .posts import approval_errors as post_approval_errors
from .posts import publish_blockers as post_publish_blockers
from .posts import slide_count
from .providers import (
    ProviderError,
    create_anthropic_draft,
    elevenlabs_speech,
)
from .rendering import (
    atomic_json_write,
    display_path,
    run_manifest_render,
)
from .research import fetch_live_shortlist
from .schemas import (
    ComplianceReport,
    ComplianceUpdate,
    DraftRequest,
    Episode,
    EpisodeCreate,
    EpisodePatch,
    Post,
    PostAsset,
    PostChecksReport,
    PostCreate,
    PostGenerateRequest,
    PostPatch,
    Publication,
    PublishPackage,
    PublishPreview,
    PublishRequest,
    RefreshResponse,
    RenderJob,
    ResearchRefreshRequest,
    Story,
    StorySelection,
    VoiceArtifact,
)


MAX_UPLOAD_BYTES = 25 * 1024 * 1024


def utc_timestamp() -> str:
    return (
        dt.datetime.now(dt.timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def today_ist() -> str:
    ist = dt.timezone(dt.timedelta(hours=5, minutes=30))
    return dt.datetime.now(ist).date().isoformat()


def _not_found(resource: str, resource_id: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"{resource} '{resource_id}' was not found",
    )


def _episode_or_404(repository: Repository, episode_id: str) -> Episode:
    episode = repository.get_episode(episode_id)
    if episode is None:
        raise _not_found("episode", episode_id)
    return episode


def _public_render_job(job: RenderJob) -> RenderJob:
    return job.model_copy(
        update={
            "output_path": (
                f"/api/render-jobs/{job.id}/artifact"
                if job.output_path
                else ""
            )
        }
    )


def _atomic_artifact_write(path: Path, content: bytes | str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    try:
        if isinstance(content, bytes):
            temporary_path.write_bytes(content)
        else:
            temporary_path.write_text(content, encoding="utf-8")
        temporary_path.replace(path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def _validate_episode_story_ids(
    repository: Repository,
    kind: str,
    story_ids: list[str],
) -> list[Story]:
    expected = 3 if kind == "daily" else 1
    if len(story_ids) != expected:
        label = "story" if expected == 1 else "stories"
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"{kind} episodes require exactly {expected} {label}",
        )
    if len(story_ids) != len(set(story_ids)):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="story_ids must be unique",
        )
    stories = repository.get_stories_by_ids(story_ids)
    if len(stories) != len(story_ids):
        found = {story.id for story in stories}
        missing = [story_id for story_id in story_ids if story_id not in found]
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"message": "unknown story_ids", "missing": missing},
        )
    return stories


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or Settings.from_env()
    repository = Repository(app_settings.database_path)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        app_settings.prepare_directories()
        repository.initialize()
        repository.recover_interrupted_render_jobs(utc_timestamp())
        repository.recover_interrupted_publications(utc_timestamp())
        repository.seed_demo_stories(utc_timestamp())
        yield

    api = FastAPI(
        title="Giani AI Newsroom API",
        version="0.1.0",
        description=(
            "Human-in-the-loop Phase A newsroom workflow with safe demo "
            "fallbacks."
        ),
        lifespan=lifespan,
    )
    api.state.settings = app_settings
    api.state.repository = repository
    api.add_middleware(
        CORSMiddleware,
        allow_origins=list(app_settings.cors_origins),
        allow_origin_regex=(
            r"^https?://(localhost|127\.0\.0\.1|\[::1\])(?::\d+)?$"
        ),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @api.get("/api/health")
    def health(response: Response) -> dict[str, Any]:
        try:
            with repository.connect() as connection:
                connection.execute("SELECT 1").fetchone()
            database_status = "ok"
        except Exception:
            database_status = "error"
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": "ok" if database_status == "ok" else "degraded",
            "service": "giani-newsroom-api",
            "version": api.version,
            "database": database_status,
            "timestamp": utc_timestamp(),
        }

    @api.get("/api/overview")
    def overview() -> dict[str, Any]:
        counts = repository.overview_counts()
        episodes = repository.list_episodes(limit=1)
        return {
            "workspace": {
                "name": "AI News Anchor Phase A",
                "demo_seeded": True,
                "human_angle_required": True,
            },
            **counts,
            **repository.post_counts(),
            "latest_episode": (
                episodes[0].model_dump() if episodes else None
            ),
            "compliance_gates": list(COMPLIANCE_GATES),
            "post_checks": list(POST_CHECKS),
            "today": today_ist(),
        }

    @api.get("/api/capabilities")
    async def capabilities() -> dict[str, Any]:
        """What this deployment can actually do right now, and what is missing."""
        return {
            "drafting": {
                "anthropic": bool(app_settings.anthropic_api_key),
                "offline_fallback": True,
            },
            "voice": {
                "elevenlabs": bool(
                    app_settings.elevenlabs_api_key
                    and app_settings.elevenlabs_voice_id
                ),
            },
            "images": {
                "resolved_provider": app_settings.resolve_image_provider(),
                "configured": list(
                    app_settings.configured_image_providers()
                ),
                "gemini": bool(app_settings.google_api_key),
                "openai": bool(app_settings.openai_api_key),
                "stability": bool(app_settings.stability_api_key),
                "replicate": bool(app_settings.replicate_api_token),
            },
            "media_host": media_host_readiness(app_settings),
            "instagram": await diagnose_instagram(app_settings),
            "post_formats": [
                {
                    "id": key,
                    "label": spec["label"],
                    "aspect": spec["aspect"],
                    "width": spec["size"][0],
                    "height": spec["size"][1],
                    "max_assets": spec["max_assets"],
                }
                for key, spec in FORMAT_SPECS.items()
            ],
            "post_checks": [
                {"id": key, "label": CHECK_LABELS[key]} for key in POST_CHECKS
            ],
            "daily_publish_limit": app_settings.instagram_daily_post_limit,
        }

    @api.get("/api/stories", response_model=list[Story])
    def list_stories(
        selected: bool | None = Query(default=None),
        topic: str | None = Query(default=None, max_length=80),
        limit: int = Query(default=100, ge=1, le=500),
    ) -> list[Story]:
        return repository.list_stories(
            selected=selected, topic=topic, limit=limit
        )

    @api.post("/api/research/refresh", response_model=RefreshResponse)
    async def refresh_research(
        payload: ResearchRefreshRequest | None = Body(default=None),
    ) -> RefreshResponse:
        live = (
            app_settings.live_research
            if payload is None or payload.live is None
            else payload.live
        )
        errors: list[str] = []
        fetched = 0
        stored = 0
        if live:
            live_stories, errors, fetched = await fetch_live_shortlist(
                app_settings.request_timeout_seconds
            )
            if live_stories:
                stored = repository.upsert_stories(
                    live_stories, utc_timestamp()
                )
                stories = repository.get_stories_by_ids(
                    [story["id"] for story in live_stories]
                )
                mode: Literal["live", "partial", "demo"] = (
                    "partial" if errors else "live"
                )
                return RefreshResponse(
                    mode=mode,
                    fetched=fetched,
                    stored=stored,
                    errors=errors,
                    stories=stories,
                )

        repository.seed_demo_stories(utc_timestamp())
        demo_ids = [story["id"] for story in DEMO_STORIES]
        demo_stories = repository.get_stories_by_ids(demo_ids)
        if live and not errors:
            errors = ["No recent verified stories were returned by live sources."]
        return RefreshResponse(
            mode="demo",
            fetched=fetched,
            stored=0,
            errors=errors,
            stories=demo_stories,
        )

    @api.post("/api/stories/{story_id}/select", response_model=Story)
    def select_story(
        story_id: str,
        payload: StorySelection | None = Body(default=None),
    ) -> Story:
        selected = True if payload is None else payload.selected
        story = repository.select_story(
            story_id, selected, utc_timestamp()
        )
        if story is None:
            raise _not_found("story", story_id)
        return story

    @api.post(
        "/api/episodes",
        response_model=Episode,
        status_code=status.HTTP_201_CREATED,
    )
    def create_episode(payload: EpisodeCreate) -> Episode:
        story_ids = payload.story_ids
        if story_ids is None:
            story_ids = [
                story.id
                for story in repository.list_stories(
                    selected=True, limit=20
                )
            ]
        _validate_episode_story_ids(repository, payload.kind, story_ids)
        timestamp = utc_timestamp()
        return repository.create_episode(
            {
                "id": f"episode-{uuid.uuid4().hex[:16]}",
                "kind": payload.kind,
                "status": "planning",
                "date": (
                    payload.date.isoformat() if payload.date else today_ist()
                ),
                "angle": payload.angle,
                "story_ids": story_ids,
                "compliance": default_compliance(),
                "created_at": timestamp,
                "updated_at": timestamp,
            }
        )

    @api.get("/api/episodes", response_model=list[Episode])
    def list_episodes(
        kind: Literal["daily", "deep_dive"] | None = Query(default=None),
        status_filter: Literal[
            "planning", "draft", "approved", "packaged"
        ]
        | None = Query(default=None, alias="status"),
        limit: int = Query(default=100, ge=1, le=500),
    ) -> list[Episode]:
        return repository.list_episodes(
            kind=kind, status=status_filter, limit=limit
        )

    @api.get("/api/episodes/{episode_id}", response_model=Episode)
    def get_episode(episode_id: str) -> Episode:
        return _episode_or_404(repository, episode_id)

    @api.patch("/api/episodes/{episode_id}", response_model=Episode)
    def patch_episode(
        episode_id: str, payload: EpisodePatch
    ) -> Episode:
        episode = _episode_or_404(repository, episode_id)
        values = payload.model_dump(exclude_unset=True)
        if "date" in values:
            values["date"] = values["date"].isoformat()
        if "story_ids" in values:
            _validate_episode_story_ids(
                repository, episode.kind, values["story_ids"]
            )
        if "script" in values and "sections" not in values:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=(
                    "script is derived from sections; submit the edited "
                    "sections map instead"
                ),
            )
        if "sections" in values:
            canonical_script = join_sections(
                episode.kind, values["sections"]
            )
            if (
                "script" in values
                and values["script"].strip() != canonical_script.strip()
            ):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="script must match the canonical sections",
                )
            values["script"] = canonical_script
        if "script" in values:
            values["word_count"] = count_words(values["script"])
            values["runtime_seconds"] = runtime_seconds(values["script"])
        if episode.status in {"approved", "packaged"}:
            values["status"] = "draft"
        elif episode.status == "planning" and "script" in values:
            values["status"] = "draft"

        updated = repository.update_episode_content(
            episode_id,
            values,
            utc_timestamp(),
            expected_revision=episode.revision,
        )
        if updated is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="episode changed while this edit was being saved",
            )
        stories = repository.get_stories_by_ids(updated.story_ids)
        prior_compliance = updated.compliance.copy()
        if {
            "story_ids",
            "angle",
            "script",
            "sections",
            "description",
            "cues",
        } & values.keys():
            for manual_gate in (
                "format_varied",
                "figures_sourced",
                "synthetic_disclosure",
                "one_upload_today",
            ):
                prior_compliance[manual_gate] = False
        compliance = calculate_compliance(
            updated, stories, prior_compliance
        )
        final = repository.update_episode_state_if_current(
            episode_id,
            values={"compliance": compliance},
            expected_revision=updated.revision,
            expected_compliance=updated.compliance,
            timestamp=utc_timestamp(),
        )
        if final is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="episode changed while compliance was being recalculated",
            )
        return final

    @api.post("/api/episodes/{episode_id}/draft", response_model=Episode)
    async def draft_episode(
        episode_id: str,
        response: Response,
        payload: DraftRequest | None = Body(default=None),
    ) -> Episode:
        request = payload or DraftRequest()
        episode = _episode_or_404(repository, episode_id)
        stories = _validate_episode_story_ids(
            repository, episode.kind, episode.story_ids
        )
        provider_used = "offline"
        if request.provider == "anthropic" and not app_settings.anthropic_api_key:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="ANTHROPIC_API_KEY is not configured",
            )
        use_anthropic = request.provider == "anthropic" or (
            request.provider == "auto" and app_settings.anthropic_api_key
        )
        if use_anthropic:
            try:
                draft = await create_anthropic_draft(
                    app_settings, episode, stories
                )
                provider_used = "anthropic"
            except ProviderError as exc:
                if request.provider == "anthropic":
                    raise HTTPException(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        detail=str(exc),
                    ) from exc
                draft = build_offline_draft(episode, stories)
                provider_used = "offline-fallback"
        else:
            draft = build_offline_draft(episode, stories)

        response.headers["X-Draft-Provider"] = provider_used
        values = {**draft, "status": "draft"}
        candidate_payload = {
            **episode.model_dump(),
            **values,
            "updated_at": utc_timestamp(),
        }
        try:
            validated = Episode.model_validate(candidate_payload)
            if validated.script.strip() != join_sections(
                validated.kind,
                validated.sections,
            ).strip():
                raise ValueError(
                    "provider script does not match provider sections"
                )
            metadata_errors = production_metadata_errors(validated)
            if metadata_errors:
                raise ValueError("; ".join(metadata_errors))
        except (ValidationError, ValueError) as exc:
            if request.provider == "anthropic":
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Anthropic returned an invalid episode payload",
                ) from exc
            draft = build_offline_draft(episode, stories)
            provider_used = "offline-fallback-invalid-payload"
            response.headers["X-Draft-Provider"] = provider_used
            values = {**draft, "status": "draft"}
            validated = Episode.model_validate(
                {
                    **episode.model_dump(),
                    **values,
                    "updated_at": utc_timestamp(),
                }
            )
            if validated.script.strip() != join_sections(
                validated.kind,
                validated.sections,
            ).strip():
                raise RuntimeError(
                    "offline draft script does not match its sections"
                )
        values = {
            key: getattr(validated, key)
            for key in (
                "status",
                "script",
                "sections",
                "title",
                "description",
                "hashtags",
                "overlays",
                "cues",
                "word_count",
                "runtime_seconds",
            )
        }
        updated = repository.update_episode_content(
            episode_id,
            values,
            utc_timestamp(),
            expected_revision=episode.revision,
        )
        if updated is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="episode changed while the draft was being generated",
            )
        compliance = calculate_compliance(
            updated, stories, default_compliance()
        )
        final = repository.update_episode_state_if_current(
            episode_id,
            values={"compliance": compliance},
            expected_revision=updated.revision,
            expected_compliance=updated.compliance,
            timestamp=utc_timestamp(),
        )
        if final is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="episode changed while compliance was being recalculated",
            )
        return final

    @api.post("/api/episodes/{episode_id}/approve", response_model=Episode)
    def approve_episode(episode_id: str) -> Episode:
        episode = _episode_or_404(repository, episode_id)
        stories = repository.get_stories_by_ids(episode.story_ids)
        errors = approval_errors(episode, stories)
        if errors:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": "episode failed approval validation",
                    "errors": errors,
                },
            )
        compliance = calculate_compliance(
            episode, stories, episode.compliance
        )
        approved = repository.update_episode_state_if_current(
            episode_id,
            values={"status": "approved", "compliance": compliance},
            expected_revision=episode.revision,
            expected_compliance=episode.compliance,
            timestamp=utc_timestamp(),
        )
        if approved is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="episode changed while approval was being saved",
            )
        return approved

    @api.get(
        "/api/episodes/{episode_id}/compliance",
        response_model=ComplianceReport,
    )
    def episode_compliance(episode_id: str) -> ComplianceReport:
        episode = _episode_or_404(repository, episode_id)
        gates = {
            gate: bool(episode.compliance.get(gate, False))
            for gate in COMPLIANCE_GATES
        }
        blocking = [gate for gate, passed in gates.items() if not passed]
        return ComplianceReport(
            episode_id=episode_id,
            gates=gates,
            all_passed=not blocking,
            blocking=blocking,
        )

    @api.put(
        "/api/episodes/{episode_id}/compliance/{gate}",
        response_model=ComplianceReport,
    )
    def update_compliance_gate(
        episode_id: str,
        gate: str,
        payload: ComplianceUpdate,
    ) -> ComplianceReport:
        episode = _episode_or_404(repository, episode_id)
        if gate not in COMPLIANCE_GATES:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "message": f"unknown compliance gate '{gate}'",
                    "available": list(COMPLIANCE_GATES),
                },
            )
        compliance = {
            **default_compliance(),
            **episode.compliance,
            gate: payload.passed,
        }
        next_status = (
            "approved"
            if episode.status == "packaged" and not payload.passed
            else episode.status
        )
        updated = repository.update_episode_state_if_current(
            episode_id,
            values={"status": next_status, "compliance": compliance},
            expected_revision=episode.revision,
            expected_compliance=episode.compliance,
            timestamp=utc_timestamp(),
        )
        if updated is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="episode changed while the compliance gate was saved",
            )
        blocking = [
            item for item, passed in compliance.items() if not passed
        ]
        return ComplianceReport(
            episode_id=episode_id,
            gates=compliance,
            all_passed=not blocking,
            blocking=blocking,
        )

    @api.post(
        "/api/episodes/{episode_id}/voice",
        response_model=VoiceArtifact,
    )
    async def create_voice(episode_id: str) -> VoiceArtifact:
        episode = _episode_or_404(repository, episode_id)
        expected_revision = episode.revision
        starting_internal = repository.get_episode_internal(episode_id)
        if starting_internal is None:
            raise _not_found("episode", episode_id)
        previous_voice_path = str(
            starting_internal.get("voice_path", "")
        )
        if episode.status != "approved":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="approve the episode before creating voice",
            )
        if not episode.script.strip():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="draft the episode before creating voice",
            )
        error = ""
        configured = bool(
            app_settings.elevenlabs_api_key
            and app_settings.elevenlabs_voice_id
        )
        if configured:
            try:
                audio = await elevenlabs_speech(
                    app_settings, episode.script
                )
                content: bytes | str = audio
                extension = "mp3"
                provider = "elevenlabs"
                is_demo = False
            except ProviderError as exc:
                error = str(exc)
                configured = False
        if not configured:
            content = (
                "DEMO VOICE ARTIFACT - NOT AUDIO\n"
                "Configure ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID for MP3.\n\n"
                + episode.script
            )
            extension = "demo.txt"
            provider = "demo"
            is_demo = True
        output = (
            app_settings.assets_dir
            / "voice"
            / (
                f"{episode.id}-r{expected_revision}-"
                f"{uuid.uuid4().hex[:8]}.{extension}"
            )
        )
        _atomic_artifact_write(output, content)
        path_value = display_path(app_settings, output)
        committed = repository.commit_voice_if_current(
            episode_id,
            expected_revision=expected_revision,
            expected_previous_voice_path=previous_voice_path,
            voice_path=path_value,
            voice_provider=provider,
            timestamp=utc_timestamp(),
        )
        if committed is None:
            if output.exists():
                output.unlink()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "episode changed while voice was being generated; "
                    "the stale artifact was discarded"
                ),
            )
        if previous_voice_path and previous_voice_path != path_value:
            try:
                previous_path = resolve_asset(
                    app_settings,
                    previous_voice_path,
                )
            except ArtifactError:
                previous_path = None
            if previous_path is not None and previous_path.exists():
                previous_path.unlink()
        return VoiceArtifact(
            episode_id=episode_id,
            provider=provider,
            output_path=f"/api/episodes/{episode_id}/voice/file",
            is_demo=is_demo,
            error=error,
        )

    @api.get("/api/episodes/{episode_id}/voice/file")
    def download_voice(episode_id: str) -> FileResponse:
        _episode_or_404(repository, episode_id)
        internal = repository.get_episode_internal(episode_id)
        try:
            path = resolve_asset(
                app_settings,
                str((internal or {}).get("voice_path", "")),
            )
        except ArtifactError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"voice artifact is unavailable: {exc}",
            ) from exc
        return FileResponse(
            path,
            filename=path.name,
            media_type=(
                "audio/mpeg" if path.suffix.lower() == ".mp3" else "text/plain"
            ),
        )

    @api.post(
        "/api/episodes/{episode_id}/render",
        response_model=RenderJob,
        status_code=status.HTTP_202_ACCEPTED,
    )
    def create_render_job(
        episode_id: str, background_tasks: BackgroundTasks
    ) -> RenderJob:
        episode = _episode_or_404(repository, episode_id)
        if episode.status != "approved":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="approve the episode before rendering",
            )
        if not episode.script.strip():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="draft the episode before creating a render job",
            )
        internal = repository.get_episode_internal(episode_id)
        if (
            not internal
            or not str(internal.get("voice_path", "")).strip()
            or int(internal.get("revision", 0)) != episode.revision
            or int(internal.get("voice_revision", 0)) != episode.revision
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="create the voice artifact before rendering",
            )
        try:
            resolve_asset(app_settings, str(internal["voice_path"]))
        except ArtifactError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"voice artifact is unavailable: {exc}",
            ) from exc
        timestamp = utc_timestamp()
        job = repository.create_render_job(
            {
                "id": f"render-{uuid.uuid4().hex[:16]}",
                "episode_id": episode_id,
                "status": "queued",
                "progress": 0,
                "stage": "queued",
                "output_path": "",
                "error": "",
                "episode_revision": episode.revision,
                "created_at": timestamp,
                "updated_at": timestamp,
            },
            expected_voice_path=str(internal["voice_path"]),
        )
        if job is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "episode or voice changed while the render job "
                    "was being created"
                ),
            )
        background_tasks.add_task(
            run_manifest_render,
            app_settings.database_path,
            app_settings,
            job.id,
            utc_timestamp,
        )
        return _public_render_job(job)

    @api.get("/api/render-jobs/{job_id}", response_model=RenderJob)
    def get_render_job(job_id: str) -> RenderJob:
        job = repository.get_render_job(job_id)
        if job is None:
            raise _not_found("render job", job_id)
        return _public_render_job(job)

    @api.get("/api/render-jobs/{job_id}/artifact")
    def download_render_artifact(job_id: str) -> FileResponse:
        job = repository.get_render_job(job_id)
        if job is None:
            raise _not_found("render job", job_id)
        if job.status != "complete" or not job.output_path:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="render artifact is not complete",
            )
        try:
            path = resolve_asset(app_settings, job.output_path)
        except ArtifactError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"render artifact is unavailable: {exc}",
            ) from exc
        return FileResponse(
            path,
            filename=path.name,
            media_type="application/json",
        )

    @api.get("/api/render-jobs", response_model=list[RenderJob])
    def list_render_jobs(
        episode_id: str | None = Query(default=None),
        limit: int = Query(default=100, ge=1, le=500),
    ) -> list[RenderJob]:
        return [
            _public_render_job(job)
            for job in repository.list_render_jobs(
                episode_id=episode_id,
                limit=limit,
            )
        ]

    @api.post(
        "/api/episodes/{episode_id}/publish-package",
        response_model=PublishPackage,
    )
    def create_publish_package(episode_id: str) -> PublishPackage:
        episode = _episode_or_404(repository, episode_id)
        if episode.status != "approved":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="episode must be approved before packaging",
            )
        gates = {
            gate: bool(episode.compliance.get(gate, False))
            for gate in COMPLIANCE_GATES
        }
        blocking = [gate for gate, passed in gates.items() if not passed]
        if blocking:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": "episode has incomplete compliance gates",
                    "blocking": blocking,
                },
            )
        stories = repository.get_stories_by_ids(episode.story_ids)
        internal = repository.get_episode_internal(episode_id)
        if internal is None:
            raise _not_found("episode", episode_id)
        expected_revision = int(internal["revision"])
        latest_render = repository.latest_render_job(episode_id)
        if (
            latest_render is None
            or latest_render.status != "complete"
            or latest_render.progress != 100
            or not latest_render.output_path
            or latest_render.episode_revision != expected_revision
            or int(internal["voice_revision"]) != expected_revision
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="a completed render handoff is required before packaging",
            )
        try:
            render_path = resolve_asset(
                app_settings,
                latest_render.output_path,
            )
        except ArtifactError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"render artifact is unavailable: {exc}",
            ) from exc
        is_demo = any(story.is_demo for story in stories)
        warning = (
            "DEMO ONLY. This package contains placeholder stories and must not "
            "be presented as current news."
            if is_demo
            else ""
        )
        output = (
            app_settings.assets_dir
            / "publish-packages"
            / f"{episode_id}-r{expected_revision}.json"
        )
        candidate = output.with_name(
            f"{output.stem}.candidate-{uuid.uuid4().hex[:12]}{output.suffix}"
        )
        atomic_json_write(
            candidate,
            {
                "schema_version": 1,
                "episode_revision": expected_revision,
                "episode": episode.model_dump(),
                "sources": [story.model_dump() for story in stories],
                "render_job": (
                    {
                        **latest_render.model_dump(),
                        "output_path": (
                            f"/api/render-jobs/{latest_render.id}/artifact"
                        ),
                        "sha256": sha256_file(render_path),
                    }
                    if latest_render
                    else None
                ),
                "is_demo": is_demo,
                "warning": warning,
                "synthetic_content_disclosure_required": True,
                "created_at": utc_timestamp(),
            },
        )
        candidate.replace(output)
        packaged = repository.mark_episode_packaged_if_current(
            episode_id,
            expected_revision=expected_revision,
            render_job_id=latest_render.id,
            expected_compliance=gates,
            timestamp=utc_timestamp(),
        )
        if packaged is None:
            if output.exists():
                output.unlink()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "episode, voice, or render changed while the publish "
                    "package was being created"
                ),
            )
        return PublishPackage(
            episode_id=episode_id,
            output_path=(
                f"/api/episodes/{episode_id}/publish-package/file"
            ),
            is_demo=is_demo,
            warning=warning,
        )

    @api.get("/api/episodes/{episode_id}/publish-package/file")
    def download_publish_package(episode_id: str) -> FileResponse:
        episode = _episode_or_404(repository, episode_id)
        if episode.status != "packaged":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="episode does not have a current publish package",
            )
        identifier = (
            f"publish-packages/{episode_id}-r{episode.revision}.json"
        )
        try:
            path = resolve_asset(app_settings, identifier)
        except ArtifactError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"publish package is unavailable: {exc}",
            ) from exc
        return FileResponse(
            path,
            filename=path.name,
            media_type="application/json",
        )

    # ------------------------------------------------------------------
    # Post Studio: prompt -> image -> human review -> Instagram
    # ------------------------------------------------------------------

    def _post_or_404(post_id: str) -> dict[str, Any]:
        post = repository.get_post(post_id)
        if post is None:
            raise _not_found("post", post_id)
        return post

    def _serialize_post(post: dict[str, Any]) -> Post:
        post_id = str(post["id"])
        assets = repository.list_post_assets(post_id)
        return Post(
            id=post_id,
            prompt=str(post["prompt"]),
            format=post["format"],
            status=post["status"],
            headline=str(post["headline"]),
            caption=str(post["caption"]),
            hashtags=list(post["hashtags"]),
            alt_text=str(post["alt_text"]),
            ai_disclosure=str(post["ai_disclosure"]),
            image_prompts=list(post["image_prompts"]),
            direction_provider=str(post["direction_provider"]),
            image_provider=str(post["image_provider"]),
            checks={
                check: bool(post["checks"].get(check, False))
                for check in POST_CHECKS
            },
            revision=int(post["revision"]),
            approved_revision=int(post["approved_revision"]),
            error=str(post["error"]),
            created_at=str(post["created_at"]),
            updated_at=str(post["updated_at"]),
            assets=[
                PostAsset(
                    id=str(asset["id"]),
                    post_id=post_id,
                    position=int(asset["position"]),
                    kind=asset["kind"],
                    provider=str(asset["provider"]),
                    prompt_used=str(asset["prompt_used"]),
                    mime=str(asset["mime"]),
                    width=int(asset["width"]),
                    height=int(asset["height"]),
                    bytes=int(asset["bytes"]),
                    sha256=str(asset["sha256"]),
                    preview_path=preview_path(post_id, str(asset["id"])),
                    is_demo=bool(asset["is_demo"]),
                    post_revision=int(asset["post_revision"]),
                    created_at=str(asset["created_at"]),
                )
                for asset in assets
            ],
            publications=[
                Publication(
                    id=str(row["id"]),
                    post_id=post_id,
                    status=row["status"],
                    post_revision=int(row["post_revision"]),
                    container_id=str(row["container_id"]),
                    media_id=str(row["media_id"]),
                    permalink=str(row["permalink"]),
                    ig_user_id=str(row["ig_user_id"]),
                    error=str(row["error"]),
                    created_at=str(row["created_at"]),
                    updated_at=str(row["updated_at"]),
                )
                for row in repository.list_publications(post_id)
            ],
        )

    def _refresh_checks(post_id: str) -> dict[str, Any]:
        """Recompute every automatic gate against the current state."""
        post = _post_or_404(post_id)
        assets = repository.list_post_assets(post_id)
        checks = calculate_checks(post, assets, post.get("checks"))
        if checks == post["checks"]:
            return post
        updated = repository.update_post(
            post_id,
            {"checks": checks},
            utc_timestamp(),
            expected_revision=int(post["revision"]),
        )
        return updated or post

    async def _run_generation(
        post_id: str,
        *,
        direction_provider: str,
        image_provider: str,
        slides: int | None,
        redraft: bool,
    ) -> None:
        post = repository.get_post(post_id)
        if post is None:
            return
        revision = int(post["revision"])
        post_format = str(post["format"])

        def _abandon(message: str) -> None:
            current = repository.get_post(post_id)
            if current is None or current["status"] != "generating":
                return
            repository.update_post(
                post_id,
                {"status": "planning", "error": message[:1000]},
                utc_timestamp(),
                expected_revision=int(current["revision"]),
            )

        try:
            if redraft or not post["image_prompts"]:
                count = slide_count(
                    post_format, slides or len(post["image_prompts"]) or None
                )
                try:
                    plan, used_provider = await create_plan(
                        app_settings,
                        str(post["prompt"]),
                        post_format,
                        count,
                        provider=direction_provider,
                    )
                except ProviderError as exc:
                    _abandon(str(exc))
                    return
                written = repository.update_post(
                    post_id,
                    {
                        "headline": plan["headline"],
                        "caption": plan["caption"],
                        "hashtags": plan["hashtags"],
                        "alt_text": plan["alt_text"],
                        "ai_disclosure": plan["ai_disclosure"],
                        "image_prompts": plan["image_prompts"],
                        "direction_provider": used_provider,
                    },
                    utc_timestamp(),
                    expected_revision=revision,
                )
                if written is None:
                    _abandon("the post changed while direction was being written")
                    return
                post = written

            assets = await generate_assets(
                app_settings,
                repository,
                post,
                image_provider=image_provider,
                timestamp=utc_timestamp(),
            )
            checks = calculate_checks(post, assets, post.get("checks"))
            repository.update_post(
                post_id,
                {"status": "review", "error": "", "checks": checks},
                utc_timestamp(),
                expected_revision=revision,
            )
        except PipelineError as exc:
            _abandon(str(exc))
        except Exception as exc:  # a background task must never die silently
            _abandon(f"{type(exc).__name__}: {exc}")

    @api.get("/api/posts", response_model=list[Post])
    def list_posts(
        status_filter: str | None = Query(default=None, alias="status"),
        limit: int = Query(default=50, ge=1, le=200),
    ) -> list[Post]:
        return [
            _serialize_post(post)
            for post in repository.list_posts(status=status_filter, limit=limit)
        ]

    @api.post(
        "/api/posts",
        response_model=Post,
        status_code=status.HTTP_201_CREATED,
    )
    def create_post(
        payload: PostCreate, background_tasks: BackgroundTasks
    ) -> Post:
        timestamp = utc_timestamp()
        post = repository.create_post(
            {
                "id": f"post-{uuid.uuid4().hex[:16]}",
                "prompt": payload.prompt,
                "format": payload.format,
                "status": "generating" if payload.generate else "planning",
                "checks": default_checks(),
                # The request, not the resolution. Which provider actually
                # produced each slide is recorded on the asset itself, so a key
                # configured later is picked up on the next generation.
                "image_provider": payload.image_provider,
                "direction_provider": payload.direction_provider,
                "revision": 1,
                "approved_revision": 0,
                "created_at": timestamp,
                "updated_at": timestamp,
            }
        )
        if payload.generate:
            background_tasks.add_task(
                _run_generation,
                post["id"],
                direction_provider=payload.direction_provider,
                image_provider=payload.image_provider,
                slides=payload.slides,
                redraft=True,
            )
        return _serialize_post(post)

    @api.get("/api/posts/{post_id}", response_model=Post)
    def get_post(post_id: str) -> Post:
        return _serialize_post(_post_or_404(post_id))

    @api.patch("/api/posts/{post_id}", response_model=Post)
    def patch_post(post_id: str, payload: PostPatch) -> Post:
        post = _post_or_404(post_id)
        if post["status"] in {"generating", "publishing"}:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"the post is {post['status']}; wait for it to finish",
            )
        if post["status"] == "published":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "this post is live on Instagram; editing it here would "
                    "make the local record disagree with what was published. "
                    "Create a new post instead."
                ),
            )
        values = payload.model_dump(exclude_unset=True)
        # Changing the prompt or an image prompt changes the picture, so the
        # existing slides stop being a faithful preview of what would publish.
        imagery_changed = bool({"prompt", "image_prompts"} & values.keys())
        next_status = "review" if repository.list_post_assets(post_id) else "planning"
        if imagery_changed:
            next_status = "planning"
        updated = repository.update_post(
            post_id,
            {**values, "status": next_status, "error": ""},
            utc_timestamp(),
            expected_revision=int(post["revision"]),
            bump_revision=True,
            carry_assets=not imagery_changed,
        )
        if updated is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="the post changed while this edit was being saved",
            )
        return _serialize_post(_refresh_checks(post_id))

    @api.post(
        "/api/posts/{post_id}/generate",
        response_model=Post,
        status_code=status.HTTP_202_ACCEPTED,
    )
    def generate_post(
        post_id: str,
        background_tasks: BackgroundTasks,
        payload: PostGenerateRequest | None = Body(default=None),
    ) -> Post:
        request = payload or PostGenerateRequest()
        post = _post_or_404(post_id)
        if post["status"] in {"generating", "publishing"}:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"the post is already {post['status']}",
            )
        if post["status"] == "published":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "this post is already live on Instagram; create a new "
                    "post instead of regenerating it"
                ),
            )
        started = repository.update_post(
            post_id,
            {"status": "generating", "error": ""},
            utc_timestamp(),
            expected_revision=int(post["revision"]),
        )
        if started is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="the post changed while generation was being queued",
            )
        background_tasks.add_task(
            _run_generation,
            post_id,
            direction_provider=(
                request.direction_provider or post["direction_provider"] or "auto"
            ),
            image_provider=(
                request.image_provider or post["image_provider"] or "auto"
            ),
            slides=request.slides,
            redraft=request.redraft,
        )
        return _serialize_post(started)

    @api.post("/api/posts/{post_id}/upload", response_model=Post)
    async def upload_post_asset(
        post_id: str,
        file: UploadFile = File(...),
        kind: str = Form(default="image"),
    ) -> Post:
        post = _post_or_404(post_id)
        if post["status"] in {"generating", "publishing", "published"}:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"the post is {post['status']}; uploads are closed",
            )
        payload = await file.read(MAX_UPLOAD_BYTES + 1)
        if len(payload) > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="uploads are limited to twenty-five megabytes",
            )
        if not payload:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="the uploaded file is empty",
            )
        try:
            assets = register_uploaded_asset(
                app_settings,
                repository,
                post,
                payload=payload,
                kind=kind,
                mime=file.content_type or "",
                timestamp=utc_timestamp(),
            )
        except PipelineError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(exc),
            ) from exc
        checks = calculate_checks(post, assets, post.get("checks"))
        repository.update_post(
            post_id,
            {"status": "review", "error": "", "checks": checks},
            utc_timestamp(),
            expected_revision=int(post["revision"]),
        )
        return _serialize_post(_post_or_404(post_id))

    @api.get("/api/posts/{post_id}/assets/{asset_id}/file")
    def download_post_asset(post_id: str, asset_id: str) -> FileResponse:
        _post_or_404(post_id)
        asset = repository.get_post_asset(asset_id)
        if asset is None or asset["post_id"] != post_id:
            raise _not_found("post asset", asset_id)
        try:
            path = resolve_asset(app_settings, str(asset["path"]))
        except ArtifactError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"slide file is unavailable: {exc}",
            ) from exc
        return FileResponse(
            path, filename=path.name, media_type=str(asset["mime"])
        )

    @api.get("/api/public/media/{filename}")
    def public_media(filename: str) -> FileResponse:
        """Unauthenticated fetch endpoint, for Instagram's servers only.

        The forty character token in the filename is the capability. Tokens
        are minted per asset and replaced whenever slides are regenerated.
        """
        token, _, extension = filename.partition(".")
        if extension not in {"jpg", "mp4"} or len(token) != 40:
            raise _not_found("media", filename)
        asset = repository.get_post_asset_by_token(token)
        if asset is None:
            raise _not_found("media", filename)
        try:
            path = resolve_asset(app_settings, str(asset["path"]))
        except ArtifactError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"media is unavailable: {exc}",
            ) from exc
        return FileResponse(
            path,
            media_type=str(asset["mime"]),
            headers={"Cache-Control": "public, max-age=300"},
        )

    @api.get("/api/posts/{post_id}/checks", response_model=PostChecksReport)
    def post_checks(post_id: str) -> PostChecksReport:
        post = _refresh_checks(post_id)
        checks = {
            check: bool(post["checks"].get(check, False))
            for check in POST_CHECKS
        }
        blocking = [
            CHECK_LABELS[check]
            for check, passed in checks.items()
            if not passed
        ]
        return PostChecksReport(
            post_id=post_id,
            checks=checks,
            all_passed=not blocking,
            blocking=blocking,
        )

    @api.post("/api/posts/{post_id}/approve", response_model=Post)
    def approve_post(post_id: str) -> Post:
        post = _refresh_checks(post_id)
        assets = repository.list_post_assets(post_id)
        if post["status"] not in {"review", "approved"}:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"a post in '{post['status']}' cannot be approved; "
                    "generate slides first"
                ),
            )
        errors = post_approval_errors(post, assets)
        if errors:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": "post failed review validation",
                    "errors": errors,
                },
            )
        checks = {
            **calculate_checks(post, assets, post.get("checks")),
            "human_reviewed": True,
        }
        approved = repository.approve_post_if_current(
            post_id,
            expected_revision=int(post["revision"]),
            checks=checks,
            timestamp=utc_timestamp(),
        )
        if approved is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="the post changed while approval was being saved",
            )
        return _serialize_post(approved)

    @api.get(
        "/api/posts/{post_id}/publish-preview",
        response_model=PublishPreview,
    )
    async def publish_preview(post_id: str) -> PublishPreview:
        """Everything the publish call would do, without doing any of it."""
        post = _refresh_checks(post_id)
        assets = repository.list_post_assets(post_id)
        blockers = post_publish_blockers(post, assets, app_settings)

        host = media_host_readiness(app_settings)
        if not host["ready"]:
            blockers.append(str(host["detail"]))

        published_today = repository.count_publications_since(
            f"{today_ist()}T00:00:00Z"
        )
        if published_today >= app_settings.instagram_daily_post_limit:
            blockers.append(
                f"the local daily cap of "
                f"{app_settings.instagram_daily_post_limit} posts is reached"
            )

        media_urls: list[str] = []
        if not blockers:
            try:
                media_urls = [
                    f"{app_settings.public_base_url}/api/public/media/"
                    f"{asset['public_token']}."
                    f"{'mp4' if asset['kind'] == 'video' else 'jpg'}"
                    if app_settings.media_host == "local"
                    else f"{app_settings.s3_public_base_url}/"
                    f"{app_settings.s3_key_prefix.strip('/')}/"
                    f"{asset['public_token']}."
                    f"{'mp4' if asset['kind'] == 'video' else 'jpg'}"
                    for asset in assets
                ]
            except (KeyError, TypeError):
                media_urls = []

        diagnosis = await diagnose_instagram(app_settings)
        return PublishPreview(
            post_id=post_id,
            revision=int(post["revision"]),
            target="instagram",
            format=post["format"],
            caption=full_caption(
                str(post["caption"]), list(post["hashtags"])
            ),
            slides=len(assets),
            media_urls=media_urls,
            blockers=blockers,
            ready=not blockers,
            quota=diagnosis.get("quota") or {},
            account=diagnosis.get("account") or {},
        )

    @api.post("/api/posts/{post_id}/publish", response_model=Post)
    async def publish_post(post_id: str, payload: PublishRequest) -> Post:
        """Send the approved post to Instagram. This cannot be undone here."""
        post = _refresh_checks(post_id)
        assets = repository.list_post_assets(post_id)

        if int(post["revision"]) != payload.expected_revision:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "the post changed since it was reviewed; reload, "
                    "re-approve, and confirm again"
                ),
            )
        blockers = post_publish_blockers(post, assets, app_settings)
        host = media_host_readiness(app_settings)
        if not host["ready"]:
            blockers.append(str(host["detail"]))
        published_today = repository.count_publications_since(
            f"{today_ist()}T00:00:00Z"
        )
        if published_today >= app_settings.instagram_daily_post_limit:
            blockers.append(
                f"the local daily cap of "
                f"{app_settings.instagram_daily_post_limit} posts is reached"
            )
        if blockers:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"message": "post is not publishable", "blockers": blockers},
            )

        timestamp = utc_timestamp()
        publication = repository.create_publication(
            {
                "id": f"pub-{uuid.uuid4().hex[:16]}",
                "post_id": post_id,
                "status": "pending",
                "post_revision": int(post["revision"]),
                "created_at": timestamp,
                "updated_at": timestamp,
            }
        )
        if publication is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "this revision already has a publish attempt on record. "
                    "Check Instagram before trying again."
                ),
            )
        try:
            await publish_to_instagram(
                app_settings,
                repository,
                post,
                assets,
                str(publication["id"]),
                utc_timestamp,
            )
        except PipelineError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=str(exc),
            ) from exc
        return _serialize_post(_post_or_404(post_id))

    @api.get("/api/instagram/status")
    async def instagram_status() -> dict[str, Any]:
        return {
            **await diagnose_instagram(app_settings),
            "media_host": media_host_readiness(app_settings),
            "daily_limit": app_settings.instagram_daily_post_limit,
            "published_today": repository.count_publications_since(
                f"{today_ist()}T00:00:00Z"
            ),
        }

    @api.post("/api/instagram/exchange-token")
    async def instagram_exchange_token() -> dict[str, Any]:
        """Exchange a short-lived Meta token for a 60-day token (Instagram Login)."""
        try:
            body = await exchange_long_lived_token(app_settings)
        except InstagramError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc
        access_token = body.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Meta returned no access_token",
            )
        return {
            "access_token": access_token,
            "token_type": body.get("token_type", "bearer"),
            "expires_in": body.get("expires_in"),
            "message": (
                "Copy access_token into INSTAGRAM_ACCESS_TOKEN or "
                "META_ACCESS_TOKEN, then restart the API."
            ),
        }

    @api.post("/api/instagram/refresh-token")
    async def instagram_refresh_token() -> dict[str, Any]:
        """Refresh a long-lived Instagram Login token before it expires."""
        try:
            body = await refresh_long_lived_token(app_settings)
        except InstagramError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc
        access_token = body.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Meta returned no access_token",
            )
        return {
            "access_token": access_token,
            "token_type": body.get("token_type", "bearer"),
            "expires_in": body.get("expires_in"),
            "message": (
                "Copy access_token into INSTAGRAM_ACCESS_TOKEN or "
                "META_ACCESS_TOKEN, then restart the API."
            ),
        }

    return api


app = create_app()
