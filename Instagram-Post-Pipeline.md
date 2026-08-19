# Post Studio — prompt in, Instagram post out

**Companion to:** `AI-News-Anchor-Build-Plan.md` (format, compliance, calendar)
and `AI-News-Anchor-FREE-Stack.md` (infrastructure).
**This doc covers:** the still-image and carousel pipeline that sits beside the
video newsroom — one prompt becomes a finished post, you review it, and one
confirmed click publishes it to Instagram.

---

## 0. The pipeline

```
  your prompt
      │   "A quiet server room at dawn, blue light on the racks"
      ▼
┌─ CREATIVE DIRECTION ────────────────────── Claude, or offline fallback ─┐
│  headline · one image prompt per slide · caption · hashtags · alt text  │
└─────────────────────────────────────────────────────────────────────────┘
      ▼
┌─ IMAGE GENERATION ───── Gemini / Imagen / OpenAI / Stability / Replicate ┐
│  one API call per slide, at the aspect ratio the format requires         │
└─────────────────────────────────────────────────────────────────────────┘
      ▼
┌─ NORMALIZATION ───────────────────────────────────────── Pillow ────────┐
│  centre-crop to Instagram's exact box · JPEG · under eight megabytes     │
└─────────────────────────────────────────────────────────────────────────┘
      ▼
┌─ YOUR REVIEW ────────────────────────────────── Signal Desk /posts ─────┐
│  see every slide · edit caption, hashtags, alt text · regenerate ·       │
│  swap in your own photo · eleven automatic checks must be green          │
└─────────────────────────────────────────────────────────────────────────┘
      ▼  Approve  (records that a human cleared this exact revision)
      ▼  Check Instagram  (dry run: account, quota, every remaining blocker)
      ▼  Type PUBLISH
┌─ INSTAGRAM CONTENT PUBLISHING API ──────────────────────────────────────┐
│  create container → poll until FINISHED → media_publish → permalink      │
└─────────────────────────────────────────────────────────────────────────┘
```

Nothing between the prompt and "Type PUBLISH" touches Instagram. The publish
step is the only irreversible action, and it needs an explicit typed
confirmation plus a revision number that matches what you reviewed.

---

## 1. What to do with your key

You said you would supply a key. Paste it into the **API environment** — never
into a `VITE_*` variable, a source file, or Git. Whichever one you have works:

| You have | Set this | Notes |
|---|---|---|
| Google AI Studio key | `GOOGLE_API_KEY` | Gets you both Gemini image (Nano Banana) and Imagen. Best value. |
| OpenAI key | `OPENAI_API_KEY` | Uses `gpt-image-1`. |
| Stability key | `STABILITY_API_KEY` | Uses Stable Image Core. |
| Replicate token | `REPLICATE_API_TOKEN` | Uses `REPLICATE_MODEL`, default FLUX 1.1 Pro. |
| Anthropic key | `ANTHROPIC_API_KEY` | Optional. Writes the caption and image prompts. Without it a deterministic offline writer takes over. |

```powershell
cd E:\giani_reporter\apps\api
$env:UV_PROJECT_ENVIRONMENT = 'E:\cache\venvs\giani_reporter'
$env:UV_CACHE_DIR = 'E:\cache\uv'

$env:GOOGLE_API_KEY = 'your-key-here'      # or OPENAI_API_KEY, etc.
$env:ANTHROPIC_API_KEY = 'your-key-here'   # optional but recommended

uv run uvicorn newsroom_api.main:app --reload --host 127.0.0.1 --port 8000
```

Open the desk at `http://127.0.0.1:5173/posts`. The header chip shows which
image provider resolved. `GET /api/capabilities` prints the same thing as JSON,
plus exactly what is still missing.

**Without any image key** the pipeline still runs end to end. It produces a
visibly stamped placeholder that says `DEMO PLACEHOLDER`, marks it `is_demo`,
and the publish gate refuses it permanently. That is deliberate: the desk never
lets a placeholder reach a real account.

---

## 2. Instagram setup — the part that actually takes time

Instagram's Content Publishing API has two hard prerequisites that no amount of
code removes.

### 2.1 The account must be Business or Creator

A personal Instagram account cannot be published to by any API. Convert it in
the app: **Settings → Account type and tools → Switch to professional account**.

### 2.2 You need an app, a token, and your IG user id

Two routes. Pick one and set `INSTAGRAM_LOGIN_MODE` to match.

| | `instagram` (Instagram Login) | `facebook` (Facebook Login) |
|---|---|---|
| Host | `graph.instagram.com` | `graph.facebook.com` |
| Facebook Page required | **No** | Yes, linked to the IG account |
| Scopes | `instagram_business_basic`, `instagram_business_content_publish` | `instagram_basic`, `instagram_content_publish`, `pages_show_list`, `pages_read_engagement` |
| Simpler for one account | **Yes** | No |

Steps, Instagram Login route:

1. developers.facebook.com → **Create App** → **Business**.
2. Add the **Instagram** product → **API setup with Instagram login**.
3. Add your Instagram account under **Generate access tokens**.
4. Generate the token. Copy it and the **Instagram user id** shown next to it.
5. Exchange the short-lived token for a long-lived one (60 days):
   ```
   GET https://graph.instagram.com/access_token
       ?grant_type=ig_exchange_token
       &client_secret=<app secret>
       &access_token=<short lived token>
   ```
6. Refresh it before day 60:
   ```
   GET https://graph.instagram.com/refresh_access_token
       ?grant_type=ig_refresh_token
       &access_token=<long lived token>
   ```

```powershell
$env:META_APP_ID = '1234567890'
$env:META_APP_SECRET = 'your-app-secret'
$env:INSTAGRAM_LOGIN_MODE = 'instagram'
$env:INSTAGRAM_USER_ID = '17841400000000000'
$env:META_ACCESS_TOKEN = 'IGAA...'   # INSTAGRAM_ACCESS_TOKEN is also read
```

Exchange a short-lived token for a 60-day one without leaving the desk:

```powershell
# Paste the short-lived token into META_ACCESS_TOKEN first, then:
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/instagram/exchange-token
# → copy access_token back into META_ACCESS_TOKEN and restart the API
```

Refresh before day 60:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/instagram/refresh-token
```

`GET /api/instagram/status` confirms the account, the token, and your remaining
25-posts-per-24-hours API quota without publishing anything.

### 2.3 Media needs a public HTTPS URL

**This is the constraint people hit last and hardest.** Instagram never accepts
uploaded bytes. You pass `image_url`, and *Instagram's servers* fetch it. Your
laptop on `127.0.0.1` is not reachable from Menlo Park.

Two supported answers:

**A. Tunnel the API (fastest to try)**

```powershell
# Cloudflare Tunnel — free, no account needed for a quick trial
cloudflared tunnel --url http://127.0.0.1:8000
# → https://random-words-1234.trycloudflare.com

$env:NEWSROOM_MEDIA_HOST = 'local'
$env:NEWSROOM_PUBLIC_BASE_URL = 'https://random-words-1234.trycloudflare.com'
```

The API then serves each slide at
`/api/public/media/<40-hex-token>.jpg`. The token is minted per asset and
replaced whenever slides are regenerated, so the URL is the capability. In the
Docker deployment, `infra/Caddyfile` exempts exactly this one path from basic
auth — Instagram arrives with no credentials — and gates everything else.

**B. Object storage (what to run in production)**

Works with Cloudflare R2, Backblaze B2, MinIO, or AWS S3. Signing is SigV4,
implemented in `media_host.py`, so there is no extra dependency.

```powershell
$env:NEWSROOM_MEDIA_HOST = 's3'
$env:S3_ENDPOINT_URL = 'https://<account>.r2.cloudflarestorage.com'
$env:S3_BUCKET = 'giani-media'
$env:S3_REGION = 'auto'
$env:S3_ACCESS_KEY_ID = '...'
$env:S3_SECRET_ACCESS_KEY = '...'
$env:S3_PUBLIC_BASE_URL = 'https://media.yourdomain.com'
```

### 2.4 Arm the trigger

Publishing stays off until you say otherwise:

```powershell
$env:INSTAGRAM_PUBLISH_ENABLED = 'true'
$env:INSTAGRAM_DAILY_POST_LIMIT = '5'
```

Do one manual post to the account first. If something in the app setup is
wrong, you want to find out by hand, not through an API error.

---

## 3. Formats

| Format | Output | Slides | Instagram media type |
|---|---|---|---|
| `feed_square` | 1080×1080 | 1 | `IMAGE` |
| `feed_portrait` | 1080×1350 | 1 | `IMAGE` — best feed real estate |
| `feed_landscape` | 1080×566 | 1 | `IMAGE` |
| `carousel` | 1080×1350 | 2–10 | `CAROUSEL` with child containers |
| `story` | 1080×1920 | 1 | `STORIES` |
| `reel` | 1080×1920 | 1 video | `REELS` |

Whatever the provider returns is centre-cropped to the exact box and re-encoded
as JPEG, stepping quality down until it is under eight megabytes. Instagram
never has to resize what you send.

`reel` takes a video, not a generated image. Render the anchor episode through
the existing pipeline, then **Use my own file** on the post to attach the mp4.
That is the bridge between the two halves of this repo: the video newsroom
produces the Reel, Post Studio captions and publishes it.

---

## 4. The eleven checks

Every one is recomputed from the post itself on every read. Ten are automatic;
the eleventh is your approval, and it is revoked the moment anything else
changes.

| Check | Fails when |
|---|---|
| `prompt_present` | No human prompt on record |
| `caption_length` | Caption plus hashtags exceeds 2,200 characters, or is empty |
| `hashtag_count` | More than 30, a duplicate, or a tag that is not `#word` |
| `alt_text_present` | Alt text missing or over 1,000 characters |
| `ai_disclosure` | The caption no longer carries the AI-generated line |
| `advice_safe` | Medical, legal, financial, or political advice detected |
| `neutral_anchor` | Credential or expert framing detected |
| `asset_count` | Slide count does not match the format |
| `assets_current` | A slide belongs to an older revision than the caption |
| `no_demo_assets` | Any slide is a placeholder |
| `human_reviewed` | You have not approved *this* revision |

The advice and credential rules are the same functions the video pipeline uses,
so a caption cannot say something a script would be blocked for saying.

---

## 5. Safety rails on the publish step

| Risk | Control |
|---|---|
| Double post from a double click | Unique index on `(post_id, post_revision)` for any non-failed attempt. The second insert is refused by the database, not by a check that can be raced. |
| Publishing something you did not see | `expected_revision` in the request body must equal the current revision, and `approved_revision` must equal it too. |
| Accidental click | The button stays disabled until you type `PUBLISH`. |
| Placeholder reaching a real account | `is_demo` is a hard, unbypassable blocker. |
| Runaway posting | `INSTAGRAM_DAILY_POST_LIMIT`, counted locally per IST day, on top of Instagram's own 25/24h quota. |
| Crash mid-publish | Interrupted attempts are marked failed on restart with a message telling you to check Instagram before retrying — the pipeline never silently re-posts. |
| Failed publish stranding the post | The attempt is marked failed, the post returns to `approved`, and a retry is allowed. Only attempts that produced no media can fail this way. |
| Published but the record did not save | Reported with the Instagram media id in the error, so the post can be reconciled by hand. |

---

## 6. API reference

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/capabilities` | What is configured, what is missing, format catalog |
| `GET` | `/api/posts` | Recent posts with slides and publish history |
| `POST` | `/api/posts` | `{prompt, format, slides?, image_provider?}` — starts the pipeline |
| `GET` | `/api/posts/{id}` | Poll while `status` is `generating` |
| `PATCH` | `/api/posts/{id}` | Edit caption, hashtags, alt text, headline, prompt |
| `POST` | `/api/posts/{id}/generate` | Regenerate slides (`redraft: false`) or everything (`true`) |
| `POST` | `/api/posts/{id}/upload` | multipart `file` + `kind` — bring your own photo or video |
| `GET` | `/api/posts/{id}/assets/{asset}/file` | Private preview, for the desk |
| `GET` | `/api/public/media/{token}.jpg` | Public fetch, for Instagram only |
| `GET` | `/api/posts/{id}/checks` | The eleven gates |
| `POST` | `/api/posts/{id}/approve` | Records human review of this revision |
| `GET` | `/api/posts/{id}/publish-preview` | Dry run: account, quota, every blocker |
| `POST` | `/api/posts/{id}/publish` | `{confirm: true, expected_revision}` — goes live |
| `GET` | `/api/instagram/status` | Token, account, quota, media host readiness |

### Whole flow with curl

```bash
API=http://127.0.0.1:8000/api

ID=$(curl -s -X POST $API/posts -H 'content-type: application/json' \
  -d '{"prompt":"A quiet server room at dawn, blue light on the racks",
       "format":"feed_portrait"}' | jq -r .id)

sleep 20 && curl -s $API/posts/$ID | jq '{status, headline, error}'

curl -s -X PATCH $API/posts/$ID -H 'content-type: application/json' \
  -d '{"hashtags":["#AI","#Infrastructure","#Datacenter"]}' > /dev/null

curl -s -X POST $API/posts/$ID/approve | jq '{status, revision}'
curl -s $API/posts/$ID/publish-preview | jq '{ready, blockers}'

REV=$(curl -s $API/posts/$ID | jq .revision)
curl -s -X POST $API/posts/$ID/publish -H 'content-type: application/json' \
  -d "{\"confirm\":true,\"expected_revision\":$REV}" \
  | jq '.publications[0].permalink'
```

---

## 7. What this deliberately does not do

- **No scheduling.** Every publish is a human action taken now. Add a scheduler
  once the daily rhythm is proven, not before.
- **No auto-posting from the news pipeline.** Episodes still end at a publish
  package a human uploads. Post Studio is a separate, explicit path.
- **No named real people or brand marks in image prompts.** The direction
  prompt forbids both. Generated likenesses of real people and imitated trade
  dress are the two fastest routes to an account strike.
- **No text baked into generated images.** Image models still render letters
  badly, and a typo inside a picture cannot be edited after posting. Put words
  in the caption or in an overlay you control.
- **No second platform yet.** The container-then-publish shape is close to what
  TikTok, Threads, and LinkedIn use, so `instagram.py` is the template — but
  each has its own review and quota rules that deserve their own gates.

---

## 8. First three actions

1. **Set the image key and restart the API.** Then `GET /api/capabilities` and
   confirm `images.resolved_provider` is not `offline`.
2. **Generate one post and look at it.** No Instagram setup needed. This proves
   direction, generation, cropping, and review in about two minutes.
3. **Then do the Instagram plumbing.** Business account, app, long-lived token,
   tunnel or bucket. `GET /api/instagram/status` is green before you ever set
   `INSTAGRAM_PUBLISH_ENABLED=true`.

*Instagram Graph API behaviour verified against v21.0. Re-check the publishing
limit, the token lifetime, and the supported aspect ratios each quarter — all
three have moved in the last year.*
