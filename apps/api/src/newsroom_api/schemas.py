from __future__ import annotations

import datetime as dt
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator


EpisodeKind = Literal["daily", "deep_dive"]
EpisodeStatus = Literal["planning", "draft", "approved", "packaged"]
RenderStatus = Literal["queued", "running", "complete", "failed"]

PostFormat = Literal[
    "feed_square",
    "feed_portrait",
    "feed_landscape",
    "carousel",
    "story",
    "reel",
]
PostStatus = Literal[
    "planning", "generating", "review", "approved", "publishing", "published"
]
PublicationStatus = Literal["pending", "creating", "publishing", "published", "failed"]
ImageProvider = Literal[
    "auto", "gemini", "imagen", "openai", "stability", "replicate", "offline"
]


class Story(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    source: str
    url: str
    published_at: str
    summary: str
    why_it_matters: str
    score: float
    selected: bool
    topic: str
    is_demo: bool


class StorySelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selected: bool = True


class Episode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: EpisodeKind
    status: EpisodeStatus
    date: str
    angle: str
    story_ids: list[str]
    script: str
    sections: dict[str, str]
    title: str = Field(max_length=100)
    description: str
    hashtags: list[str] = Field(max_length=10)
    overlays: list[dict[str, Any]] = Field(max_length=20)
    cues: list[dict[str, Any]] = Field(max_length=100)
    word_count: int
    runtime_seconds: int
    compliance: dict[str, bool]
    revision: int = Field(default=1, ge=1)
    voice_revision: int = Field(default=0, ge=0)
    updated_at: str


class EpisodeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: EpisodeKind
    date: dt.date | None = None
    angle: str = Field(min_length=1, max_length=500)
    story_ids: list[str] | None = None

    @field_validator("angle")
    @classmethod
    def clean_angle(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("angle is mandatory")
        return cleaned

    @field_validator("story_ids")
    @classmethod
    def unique_story_ids(cls, value: list[str] | None) -> list[str] | None:
        if value is not None and len(value) != len(set(value)):
            raise ValueError("story_ids must be unique")
        return value


class EpisodePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: dt.date | None = None
    angle: str | None = Field(default=None, min_length=1, max_length=500)
    story_ids: list[str] | None = None
    script: str | None = None
    sections: dict[str, str] | None = None
    title: str | None = Field(default=None, max_length=100)
    description: str | None = None
    hashtags: list[str] | None = None
    overlays: list[dict[str, Any]] | None = None
    cues: list[dict[str, Any]] | None = None

    @field_validator("angle")
    @classmethod
    def clean_angle(cls, value: str | None) -> str | None:
        if value is None:
            return value
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("angle cannot be blank")
        return cleaned

    @field_validator("story_ids")
    @classmethod
    def unique_story_ids(cls, value: list[str] | None) -> list[str] | None:
        if value is not None and len(value) != len(set(value)):
            raise ValueError("story_ids must be unique")
        return value

    @model_validator(mode="after")
    def at_least_one_change(self) -> "EpisodePatch":
        if not self.model_fields_set:
            raise ValueError("at least one field is required")
        null_fields = sorted(
            field_name
            for field_name in self.model_fields_set
            if getattr(self, field_name) is None
        )
        if null_fields:
            raise ValueError(
                "patch fields cannot be null: " + ", ".join(null_fields)
            )
        return self


class DraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: Literal["auto", "offline", "anthropic"] = "auto"


class ComplianceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    passed: bool


class ResearchRefreshRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    live: bool | None = None


class RenderJob(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    episode_id: str
    status: RenderStatus
    progress: int = Field(ge=0, le=100)
    stage: str
    output_path: str
    error: str
    episode_revision: int = Field(default=1, ge=1)


class ComplianceReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    episode_id: str
    gates: dict[str, bool]
    all_passed: bool
    blocking: list[str]


class VoiceArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    episode_id: str
    provider: Literal["demo", "elevenlabs"]
    output_path: str
    is_demo: bool
    error: str = ""


class PublishPackage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    episode_id: str
    output_path: str
    is_demo: bool
    warning: str = ""


class RefreshResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["live", "partial", "demo"]
    fetched: int
    stored: int
    errors: list[str]
    stories: list[Story]


# ---------------------------------------------------------------------------
# Post Studio
# ---------------------------------------------------------------------------


class PostAsset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    post_id: str
    position: int = Field(ge=0)
    kind: Literal["image", "video"]
    provider: str
    prompt_used: str
    mime: str
    width: int = Field(ge=0)
    height: int = Field(ge=0)
    bytes: int = Field(ge=0)
    sha256: str
    preview_path: str
    is_demo: bool
    post_revision: int = Field(ge=1)
    created_at: str


class Publication(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    post_id: str
    status: PublicationStatus
    post_revision: int = Field(ge=1)
    container_id: str
    media_id: str
    permalink: str
    ig_user_id: str
    error: str
    created_at: str
    updated_at: str


class Post(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    prompt: str
    format: PostFormat
    status: PostStatus
    headline: str
    caption: str
    hashtags: list[str] = Field(max_length=30)
    alt_text: str
    ai_disclosure: str
    image_prompts: list[str] = Field(max_length=10)
    direction_provider: str
    image_provider: str
    checks: dict[str, bool]
    revision: int = Field(ge=1)
    approved_revision: int = Field(ge=0)
    error: str
    created_at: str
    updated_at: str
    assets: list[PostAsset] = Field(default_factory=list)
    publications: list[Publication] = Field(default_factory=list)


class PostCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(min_length=3, max_length=2000)
    format: PostFormat = "feed_square"
    slides: int | None = Field(default=None, ge=1, le=10)
    image_provider: ImageProvider = "auto"
    direction_provider: Literal["auto", "offline", "anthropic", "openai"] = "auto"
    generate: bool = True

    @field_validator("prompt")
    @classmethod
    def clean_prompt(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("a prompt is mandatory")
        return cleaned


class PostPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt: str | None = Field(default=None, min_length=3, max_length=2000)
    headline: str | None = Field(default=None, max_length=200)
    caption: str | None = Field(default=None, max_length=2200)
    hashtags: list[str] | None = Field(default=None, max_length=30)
    alt_text: str | None = Field(default=None, max_length=1000)
    image_prompts: list[str] | None = Field(default=None, max_length=10)

    @model_validator(mode="after")
    def at_least_one_change(self) -> "PostPatch":
        if not self.model_fields_set:
            raise ValueError("at least one field is required")
        null_fields = sorted(
            name
            for name in self.model_fields_set
            if getattr(self, name) is None
        )
        if null_fields:
            raise ValueError(
                "patch fields cannot be null: " + ", ".join(null_fields)
            )
        return self


class PostGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    image_provider: ImageProvider | None = None
    direction_provider: Literal["auto", "offline", "anthropic", "openai"] | None = None
    slides: int | None = Field(default=None, ge=1, le=10)
    redraft: bool = True


class PublishRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirm: Literal[True]
    expected_revision: int = Field(ge=1)


class PostChecksReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    post_id: str
    checks: dict[str, bool]
    all_passed: bool
    blocking: list[str]


class PublishPreview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    post_id: str
    revision: int
    target: str
    format: PostFormat
    caption: str
    slides: int
    media_urls: list[str]
    blockers: list[str]
    ready: bool
    quota: dict[str, Any] = Field(default_factory=dict)
    account: dict[str, Any] = Field(default_factory=dict)
