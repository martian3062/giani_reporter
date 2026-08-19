# Giani AI Newsroom API

FastAPI + SQLite backend for the Phase A human-in-the-loop AI news
production workflow. It manages research candidates, story selection,
episodes, deterministic offline drafts, compliance, voice artifacts, render
handoffs, and publish packages.

The backend never disguises placeholders as current news. On first start it
idempotently creates three stale, visibly labelled `[DEMO]` stories. If live
research cannot return recent source material, the refresh endpoint returns
those demo records with `mode: "demo"` instead of fabricating facts.

## Run locally

Python 3.10 or newer is required.

```powershell
cd E:\giani_reporter\apps\api
$env:UV_PROJECT_ENVIRONMENT = 'E:\cache\venvs\giani_reporter'
$env:UV_CACHE_DIR = 'E:\cache\uv'
uv sync --extra dev
uv run uvicorn newsroom_api.main:app --reload --host 127.0.0.1 --port 8000
```

OpenAPI is available at `http://127.0.0.1:8000/docs`.

Run the tests with:

```powershell
uv run pytest
```

## Configuration

All storage defaults are relative to this backend directory, not the process
working directory.

| Variable | Default | Purpose |
|---|---|---|
| `NEWSROOM_DATA_DIR` | `data` | SQLite/data directory |
| `NEWSROOM_ASSETS_DIR` | `assets` | Generated artifact directory |
| `NEWSROOM_DATABASE_PATH` | `<data>/newsroom.sqlite3` | Optional explicit database file |
| `NEWSROOM_LIVE_RESEARCH` | `true` | Enable live RSS/Hacker News refresh by default |
| `NEWSROOM_REQUEST_TIMEOUT_SECONDS` | `8` | External HTTP timeout |
| `NEWSROOM_CORS_ORIGINS` | localhost ports 3000 and 5173 | Extra comma-separated origins |
| `ANTHROPIC_API_KEY` | unset | Enables Anthropic when draft provider is `auto` or `anthropic` |
| `ANTHROPIC_MODEL` | `claude-sonnet-4-20250514` | Anthropic model identifier |
| `ELEVENLABS_API_KEY` | unset | Enables ElevenLabs raw HTTP voice generation |
| `ELEVENLABS_VOICE_ID` | unset | Saved broadcast voice ID |
| `ELEVENLABS_MODEL_ID` | `eleven_multilingual_v2` | ElevenLabs model |

Relative path overrides are resolved against `apps/api`. Absolute overrides
are also accepted. CORS permits `localhost`, `127.0.0.1`, and `::1` on any
port for local frontends.

### Post Studio

Image generation. Set one key; `auto` uses the first configured provider in the
order below. With none set, slides are visibly stamped placeholders that the
publish gate always refuses.

| Variable | Default | Purpose |
|---|---|---|
| `NEWSROOM_IMAGE_PROVIDER` | `auto` | `auto`, `gemini`, `imagen`, `openai`, `stability`, `replicate`, `offline` |
| `NEWSROOM_IMAGE_TIMEOUT_SECONDS` | `120` | Per-image HTTP timeout |
| `GOOGLE_API_KEY` | unset | Gemini image and Imagen. `GEMINI_API_KEY` is also read |
| `GEMINI_IMAGE_MODEL` | `gemini-2.5-flash-image` | Gemini image model |
| `IMAGEN_MODEL` | `imagen-4.0-generate-001` | Imagen model |
| `OPENAI_API_KEY` | unset | OpenAI images |
| `OPENAI_IMAGE_MODEL` | `gpt-image-1` | OpenAI image model |
| `STABILITY_API_KEY` | unset | Stable Image Core |
| `REPLICATE_API_TOKEN` | unset | Replicate |
| `REPLICATE_MODEL` | `black-forest-labs/flux-1.1-pro` | Replicate model slug |

Public media hosting. Instagram fetches `image_url` from its own servers, so a
generated slide needs a public HTTPS address before it can be published.

| Variable | Default | Purpose |
|---|---|---|
| `NEWSROOM_MEDIA_HOST` | `local` | `local` serves from this API; `s3` uploads to a bucket |
| `NEWSROOM_PUBLIC_BASE_URL` | unset | Public HTTPS root for `local` mode |
| `S3_ENDPOINT_URL` | unset | S3-compatible endpoint (R2, B2, MinIO, AWS) |
| `S3_BUCKET` / `S3_REGION` | unset / `auto` | Target bucket |
| `S3_ACCESS_KEY_ID` / `S3_SECRET_ACCESS_KEY` | unset | SigV4 credentials |
| `S3_PUBLIC_BASE_URL` | unset | Public root the bucket serves from |
| `S3_KEY_PREFIX` | `giani/posts` | Object key prefix |

Instagram publishing (Meta Graph API).

| Variable | Default | Purpose |
|---|---|---|
| `META_APP_ID` | unset | Meta app id. `FACEBOOK_APP_ID` is also read |
| `META_APP_SECRET` | unset | Meta app secret. `FACEBOOK_APP_SECRET` is also read. Enables `appsecret_proof` on Graph calls and the token exchange endpoints |
| `INSTAGRAM_LOGIN_MODE` | `facebook` | `facebook` uses `graph.facebook.com`; `instagram` uses `graph.instagram.com` |
| `INSTAGRAM_GRAPH_VERSION` | `v21.0` | Graph API version |
| `INSTAGRAM_USER_ID` | unset | Instagram Business or Creator account id |
| `INSTAGRAM_ACCESS_TOKEN` | unset | Long-lived user token. `META_ACCESS_TOKEN` and `FACEBOOK_ACCESS_TOKEN` are also read |
| `INSTAGRAM_PUBLISH_ENABLED` | `false` | Master switch. Publishing is refused while false |
| `INSTAGRAM_DAILY_POST_LIMIT` | `5` | Local cap per IST day, under Instagram's own quota |
| `INSTAGRAM_POLL_ATTEMPTS` / `INSTAGRAM_POLL_INTERVAL_SECONDS` | `30` / `3` | Container status polling |
| `NEWSROOM_SITE` | unset | When `NEWSROOM_PUBLIC_BASE_URL` is unset, a bare hostname becomes `https://<host>` so Docker/production can omit the duplicate |

**Local dev:** set keys in your shell, tunnel the API (`cloudflared tunnel --url http://127.0.0.1:8000` or ngrok), and point `NEWSROOM_PUBLIC_BASE_URL` at the tunnel URL.

**Production (Compose):** put the same keys in `infra/.env`. Set `NEWSROOM_SITE` to your real domain (no `http://` prefix) and either leave `NEWSROOM_PUBLIC_BASE_URL` unset or set it explicitly. Instagram media is served at `/api/public/media/*`, which Caddy exempts from basic auth.

After pasting a short-lived token from the Meta developer console, call `POST /api/instagram/exchange-token` (with `META_APP_SECRET` set) to get a 60-day token. Refresh before expiry with `POST /api/instagram/refresh-token`.

`GET /api/capabilities` reports which of these resolved and what is missing.
Full setup is in [Instagram-Post-Pipeline.md](../../Instagram-Post-Pipeline.md).

## API workflow

1. `POST /api/research/refresh` fetches recent RSS and Hacker News material.
2. `POST /api/stories/{id}/select` changes the editorial shortlist.
3. `POST /api/episodes` creates a daily episode with exactly three stories or
   a deep dive with exactly one. A nonblank human angle is mandatory.
4. `POST /api/episodes/{id}/draft` creates a safe deterministic offline draft.
   If `ANTHROPIC_API_KEY` exists, provider `auto` attempts Anthropic and safely
   falls back offline on provider failure. Explicit provider `anthropic`
   returns a provider error instead of silently changing modes.
5. `PATCH /api/episodes/{id}` supports human script and metadata edits.
6. `POST /api/episodes/{id}/approve` enforces story count, `[VERIFY]` removal,
   word count, sentence length, source links, title length, voice-safe
   punctuation, spelled-out numbers, hype rules, and advice restrictions.
7. Compliance is reviewed through
   `GET /api/episodes/{id}/compliance` and
   `PUT /api/episodes/{id}/compliance/{gate}`. All 11 gates begin unchecked;
   none is auto-passed. Unsafe content can force a gate off, but only the
   producer can pass it.
8. `POST /api/episodes/{id}/voice` writes an ElevenLabs MP3 when configured.
   Otherwise it writes an obvious `.demo.txt` artifact; it never creates a
   fake MP3. Retrieve the current artifact through
   `GET /api/episodes/{id}/voice/file`.
9. `POST /api/episodes/{id}/render` queues a persisted background job. The
   current Phase A implementation produces an honest, checksummed assembly
   manifest for the private GPU lip-sync and FFmpeg stages, not a pretend
   video. Poll it with `GET /api/render-jobs/{id}` or list all jobs with
   `GET /api/render-jobs`; download the completed manifest from
   `GET /api/render-jobs/{id}/artifact`.
10. `POST /api/episodes/{id}/publish-package` writes a metadata/source/render
    JSON package only after approval and every compliance gate passes. Demo
    packages carry a prominent non-publication warning. Retrieve it from
    `GET /api/episodes/{id}/publish-package/file`.

## Post Studio workflow

A separate pipeline from prompt to a published Instagram post. It is the only
path in this service that can publish, and it never does so without an explicit
human confirmation.

1. `POST /api/posts` takes `{prompt, format, slides?, image_provider?}` and
   returns immediately with status `generating`. A background task writes the
   creative direction, then generates one image per slide and centre-crops each
   to Instagram's exact box as a JPEG under eight megabytes.
2. `GET /api/posts/{id}` is polled until the status leaves `generating`. On
   failure the status returns to `planning` with the reason in `error`; no
   partial slide set is ever attached.
3. `PATCH /api/posts/{id}` edits the caption, hashtags, alt text, headline,
   prompt, or image prompts. Every edit opens a new revision and revokes
   approval. Editing the prompt or an image prompt also detaches the slides,
   since they no longer preview what would publish; editing only text carries
   them forward.
4. `POST /api/posts/{id}/upload` attaches an operator-supplied photo or video
   instead, normalized the same way. This is how a rendered Reel enters the
   pipeline.
5. `GET /api/posts/{id}/checks` reports eleven gates. Ten are recomputed from
   the post on every read; the eleventh is human approval.
6. `POST /api/posts/{id}/approve` records that a human cleared this exact
   revision. It refuses while any automatic gate fails, and a placeholder image
   fails one permanently.
7. `GET /api/posts/{id}/publish-preview` is a dry run. It reports the target
   account, the remaining Instagram quota, the caption exactly as it would be
   sent, and every blocker, without contacting the publishing endpoints.
8. `POST /api/posts/{id}/publish` takes `{confirm: true, expected_revision}`.
   It creates the container, polls until Instagram reports `FINISHED`,
   publishes, and records the permalink. A unique index allows only one
   non-failed attempt per revision, so a double click cannot post twice.
9. `GET /api/instagram/status` checks the token, account, quota, and media host
   readiness at any time without publishing.

Media served for Instagram lives at `GET /api/public/media/{token}.jpg`. That
route is unauthenticated by design — Instagram's fetchers carry no credentials —
and gated by a forty character per-asset token that is replaced whenever slides
are regenerated. In the Compose deployment, `infra/Caddyfile` exempts exactly
this path from basic auth and gates everything else.

Other read endpoints are:

- `GET /api/health`
- `GET /api/overview`
- `GET /api/capabilities`
- `GET /api/stories`
- `GET /api/episodes`
- `GET /api/episodes/{id}`
- `GET /api/posts`
- `GET /api/posts/{id}`

Story, episode, and render-job responses include the complete field set used
by the frontend build plan.

## Research behavior

Live refresh reads the six configured AI news RSS sources and Hacker News.
Items with a verifiable publication time older than 24 hours are excluded;
Hacker News items must have a score above 100. Results are deduplicated,
ranked, and capped at eight. Feed summaries are stored as source-provided
material. `why_it_matters` is deliberately neutral because the human editor,
not the backend, chooses the angle.

Force the deterministic demo path without network access:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/api/research/refresh `
  -ContentType application/json `
  -Body '{"live":false}'
```

## Safety and persistence

- SQLite uses WAL mode, foreign keys, a busy timeout, and one connection per
  operation so background render updates are safe.
- Provider keys are read from environment variables and are never written to
  SQLite, manifests, responses, or logs.
- Content edits demote approved or packaged episodes back to `draft`.
- Episode, voice, and render revisions are compared when writing artifacts,
  so a stale provider response or background job cannot overwrite a newer
  human edit.
- Voice, render, and package paths are resolved under `NEWSROOM_ASSETS_DIR`;
  traversal and missing-file responses fail closed.
- Production metadata requires exactly five unique hashtags, exactly four
  ordered overlays of at most 42 characters, and reviewed B-roll cues every
  eight to twelve seconds.
- Drafting never publishes. Packaging never uploads to social platforms.
- Generated databases, voice files, manifests, and packages are ignored by
  Git.
