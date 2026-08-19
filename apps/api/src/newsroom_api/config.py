from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


DEFAULT_CORS_ORIGINS: tuple[str, ...] = (
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
)


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    try:
        return int(value.strip())
    except ValueError:
        return default


def _resolve_path(api_root: Path, value: str | None, default_name: str) -> Path:
    path = Path(value) if value else Path(default_name)
    if not path.is_absolute():
        path = api_root / path
    return path.resolve()


def _first_env(*names: str) -> str:
    for name in names:
        value = os.getenv(name)
        if value is not None and value.strip():
            return value.strip()
    return ""


def _resolve_public_base_url() -> str:
    """Public HTTPS root for Instagram media fetches.

    ``NEWSROOM_PUBLIC_BASE_URL`` wins when set. Otherwise derive from
    ``NEWSROOM_SITE`` so Docker/production can omit the duplicate — a bare
    hostname becomes ``https://<host>``; an ``http://`` value is kept as-is
    for local tunnels (media_host will refuse non-HTTPS at publish time).
    """
    explicit = os.getenv("NEWSROOM_PUBLIC_BASE_URL", "").strip()
    if explicit:
        return explicit.rstrip("/")
    site = os.getenv("NEWSROOM_SITE", "").strip()
    if not site:
        return ""
    if site.startswith(("http://", "https://")):
        return site.rstrip("/")
    return f"https://{site.rstrip('/')}"


@dataclass(slots=True)
class Settings:
    api_root: Path = field(
        default_factory=lambda: Path(__file__).resolve().parents[2]
    )
    data_dir: Path | None = None
    assets_dir: Path | None = None
    database_path: Path | None = None
    live_research: bool = True
    request_timeout_seconds: float = 8.0
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-4-20250514"
    elevenlabs_api_key: str | None = None
    elevenlabs_voice_id: str | None = None
    elevenlabs_model_id: str = "eleven_multilingual_v2"
    cors_origins: tuple[str, ...] = DEFAULT_CORS_ORIGINS

    # --- Post Studio: image generation -------------------------------------
    image_provider: str = "auto"
    image_timeout_seconds: float = 120.0
    google_api_key: str | None = None
    gemini_image_model: str = "gemini-2.5-flash-image"
    imagen_model: str = "imagen-4.0-generate-001"
    openai_api_key: str | None = None
    openai_image_model: str = "gpt-image-1"
    openai_text_model: str = "gpt-4o-mini"
    stability_api_key: str | None = None
    stability_model: str = "sd3.5-large"
    replicate_api_token: str | None = None
    replicate_model: str = "black-forest-labs/flux-1.1-pro"

    # --- Post Studio: public media hosting ---------------------------------
    media_host: str = "local"
    public_base_url: str = ""
    s3_endpoint_url: str = ""
    s3_bucket: str = ""
    s3_region: str = "auto"
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_public_base_url: str = ""
    s3_key_prefix: str = "giani/posts"

    # --- Post Studio: Instagram / Meta publishing --------------------------
    meta_app_id: str = ""
    meta_app_secret: str = ""
    instagram_login_mode: str = "facebook"
    instagram_graph_version: str = "v21.0"
    instagram_user_id: str = ""
    instagram_access_token: str = ""
    instagram_publish_enabled: bool = False
    instagram_daily_post_limit: int = 5
    instagram_poll_attempts: int = 30
    instagram_poll_interval_seconds: float = 3.0

    def __post_init__(self) -> None:
        self.api_root = self.api_root.resolve()
        self.data_dir = (self.data_dir or self.api_root / "data").resolve()
        self.assets_dir = (self.assets_dir or self.api_root / "assets").resolve()
        self.database_path = (
            self.database_path or self.data_dir / "newsroom.sqlite3"
        ).resolve()
        self.public_base_url = self.public_base_url.rstrip("/")
        self.s3_public_base_url = self.s3_public_base_url.rstrip("/")
        self.s3_endpoint_url = self.s3_endpoint_url.rstrip("/")

    @classmethod
    def from_env(cls) -> "Settings":
        api_root = Path(__file__).resolve().parents[2]
        data_dir = _resolve_path(
            api_root, os.getenv("NEWSROOM_DATA_DIR"), "data"
        )
        assets_dir = _resolve_path(
            api_root, os.getenv("NEWSROOM_ASSETS_DIR"), "assets"
        )
        database_value = os.getenv("NEWSROOM_DATABASE_PATH")
        database_path = (
            _resolve_path(api_root, database_value, "data/newsroom.sqlite3")
            if database_value
            else data_dir / "newsroom.sqlite3"
        )
        origins = tuple(
            item.strip()
            for item in os.getenv(
                "NEWSROOM_CORS_ORIGINS",
                ",".join(DEFAULT_CORS_ORIGINS),
            ).split(",")
            if item.strip()
        )
        return cls(
            api_root=api_root,
            data_dir=data_dir,
            assets_dir=assets_dir,
            database_path=database_path,
            live_research=_env_bool("NEWSROOM_LIVE_RESEARCH", True),
            request_timeout_seconds=float(
                os.getenv("NEWSROOM_REQUEST_TIMEOUT_SECONDS", "8")
            ),
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
            anthropic_model=os.getenv(
                "ANTHROPIC_MODEL", "claude-sonnet-4-20250514"
            ),
            elevenlabs_api_key=os.getenv("ELEVENLABS_API_KEY"),
            elevenlabs_voice_id=os.getenv("ELEVENLABS_VOICE_ID"),
            elevenlabs_model_id=os.getenv(
                "ELEVENLABS_MODEL_ID", "eleven_multilingual_v2"
            ),
            cors_origins=origins,
            image_provider=os.getenv("NEWSROOM_IMAGE_PROVIDER", "auto")
            .strip()
            .lower(),
            image_timeout_seconds=float(
                os.getenv("NEWSROOM_IMAGE_TIMEOUT_SECONDS", "120")
            ),
            google_api_key=(
                os.getenv("GOOGLE_API_KEY")
                or os.getenv("GEMINI_API_KEY")
            ),
            gemini_image_model=os.getenv(
                "GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image"
            ),
            imagen_model=os.getenv("IMAGEN_MODEL", "imagen-4.0-generate-001"),
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            openai_image_model=os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1"),
            openai_text_model=os.getenv("OPENAI_TEXT_MODEL", "gpt-4o-mini"),
            stability_api_key=os.getenv("STABILITY_API_KEY"),
            stability_model=os.getenv("STABILITY_MODEL", "sd3.5-large"),
            replicate_api_token=os.getenv("REPLICATE_API_TOKEN"),
            replicate_model=os.getenv(
                "REPLICATE_MODEL", "black-forest-labs/flux-1.1-pro"
            ),
            media_host=os.getenv("NEWSROOM_MEDIA_HOST", "local")
            .strip()
            .lower(),
            meta_app_id=_first_env("META_APP_ID", "FACEBOOK_APP_ID"),
            meta_app_secret=_first_env("META_APP_SECRET", "FACEBOOK_APP_SECRET"),
            public_base_url=_resolve_public_base_url(),
            s3_endpoint_url=os.getenv("S3_ENDPOINT_URL", ""),
            s3_bucket=os.getenv("S3_BUCKET", ""),
            s3_region=os.getenv("S3_REGION", "auto"),
            s3_access_key_id=os.getenv("S3_ACCESS_KEY_ID", ""),
            s3_secret_access_key=os.getenv("S3_SECRET_ACCESS_KEY", ""),
            s3_public_base_url=os.getenv("S3_PUBLIC_BASE_URL", ""),
            s3_key_prefix=os.getenv("S3_KEY_PREFIX", "giani/posts"),
            instagram_login_mode=os.getenv(
                "INSTAGRAM_LOGIN_MODE", "facebook"
            )
            .strip()
            .lower(),
            instagram_graph_version=os.getenv(
                "INSTAGRAM_GRAPH_VERSION", "v21.0"
            ),
            instagram_user_id=_first_env("INSTAGRAM_USER_ID", "META_USER_ID"),
            instagram_access_token=_first_env(
                "INSTAGRAM_ACCESS_TOKEN",
                "META_ACCESS_TOKEN",
                "FACEBOOK_ACCESS_TOKEN",
            ),
            instagram_publish_enabled=_env_bool(
                "INSTAGRAM_PUBLISH_ENABLED", False
            ),
            instagram_daily_post_limit=_env_int(
                "INSTAGRAM_DAILY_POST_LIMIT", 5
            ),
            instagram_poll_attempts=_env_int("INSTAGRAM_POLL_ATTEMPTS", 30),
            instagram_poll_interval_seconds=float(
                os.getenv("INSTAGRAM_POLL_INTERVAL_SECONDS", "3")
            ),
        )

    def prepare_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.assets_dir.mkdir(parents=True, exist_ok=True)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        (self.assets_dir / "posts").mkdir(parents=True, exist_ok=True)

    # --- derived helpers ---------------------------------------------------

    @property
    def instagram_api_base(self) -> str:
        host = (
            "https://graph.instagram.com"
            if self.instagram_login_mode == "instagram"
            else "https://graph.facebook.com"
        )
        return f"{host}/{self.instagram_graph_version.strip('/')}"

    @property
    def meta_app_configured(self) -> bool:
        return bool(self.meta_app_id.strip() and self.meta_app_secret.strip())

    @property
    def instagram_configured(self) -> bool:
        return bool(
            self.instagram_user_id.strip()
            and self.instagram_access_token.strip()
        )

    @property
    def s3_configured(self) -> bool:
        return bool(
            self.s3_endpoint_url
            and self.s3_bucket
            and self.s3_access_key_id
            and self.s3_secret_access_key
            and self.s3_public_base_url
        )

    def configured_image_providers(self) -> tuple[str, ...]:
        available: list[str] = []
        if self.google_api_key:
            available.extend(("gemini", "imagen"))
        if self.openai_api_key:
            available.append("openai")
        if self.stability_api_key:
            available.append("stability")
        if self.replicate_api_token:
            available.append("replicate")
        available.append("offline")
        return tuple(available)

    def resolve_image_provider(self, requested: str | None = None) -> str:
        choice = (requested or self.image_provider or "auto").strip().lower()
        available = self.configured_image_providers()
        if choice in {"", "auto"}:
            return available[0]
        return choice
