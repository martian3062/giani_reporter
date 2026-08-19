# Giani infrastructure and render worker

This directory contains the deployable infrastructure for the newsroom, the importable research workflow, and the private Kaggle render notebook. It does not contain credentials or generated media.

## What runs

| Service | Internal address | Public route | Persistence |
|---|---|---|---|
| Vite newsroom UI | `web:8080` | `NEWSROOM_SITE/*` | Immutable image |
| FastAPI newsroom | `newsroom:8000` | `NEWSROOM_SITE/api/*` | `newsroom_data` |
| n8n | `n8n:5678` | `N8N_SITE/*` | `n8n_data` |
| Caddy | reverse proxy | ports 80/443 | `caddy_data`, `caddy_config` |

Only Caddy publishes host ports. The API, UI, and n8n share an internal Docker network and cannot be reached directly from the host or Internet. Caddy Basic Auth protects both public sites; n8n owner authentication remains enabled behind that outer gate.

The newsroom writes its SQLite database and generated voice/package media under the writable `/data` volume. Repository assets are separately mounted read-only at `/source-assets`.

## Local setup

Prerequisites:

- Docker Engine or Docker Desktop with the Compose v2 plugin (`docker compose`).
- PowerShell, Bash, or another shell capable of editing an environment file.
- Enough memory to build the Vite app and run the three application containers. No local GPU is required.

From the repository root:

```powershell
Copy-Item infra/.env.example infra/.env
```

Edit `infra/.env` before starting:

1. Generate two independent random values for `N8N_ENCRYPTION_KEY` and `N8N_USER_MANAGEMENT_JWT_SECRET` (run this twice):

   ```powershell
   python -c "import secrets; print(secrets.token_hex(32))"
   ```
2. Generate Caddy hashes for both gates; the example deliberately leaves them blank.

   ```powershell
   docker run --rm caddy:2.10.2-alpine caddy hash-password --plaintext 'YOUR LONG PASSWORD'
   ```

   Put the hash in single quotes in `.env` so Compose does not expand its dollar signs.
3. Keep `TELEGRAM_ENABLED=false`.
4. Leave the provider API-key values empty for deterministic/demo behavior, or add keys only to the untracked `.env`.

Validate and start:

```powershell
docker compose --env-file infra/.env -f infra/compose.yml config
docker compose --env-file infra/.env -f infra/compose.yml up -d --build
docker compose --env-file infra/.env -f infra/compose.yml ps
```

Open:

- Newsroom: `http://localhost`
- n8n: `http://n8n.localhost`
- API health, through Caddy: `http://localhost/api/health`

Local HTTP is for initial setup only; Basic Auth is not confidential without TLS. `n8n.localhost` normally resolves to loopback automatically. If the local resolver does not support wildcard localhost names, add `127.0.0.1 n8n.localhost` to the hosts file.

Inspect failures without exposing secrets:

```powershell
docker compose --env-file infra/.env -f infra/compose.yml ps
docker compose --env-file infra/.env -f infra/compose.yml logs --tail 100 newsroom web n8n caddy
```

## n8n workflow

The workflow is [newsroom-research-digest.json](n8n/workflows/newsroom-research-digest.json). It includes:

- a manual trigger;
- a daily `06:30` cron trigger in the `Asia/Kolkata` workflow timezone;
- `POST http://newsroom:8000/api/research/refresh`;
- deterministic score sorting and neutral top-eight formatting;
- optional, chunked Telegram delivery.

The workflow never picks the three editorial stories, writes an angle, or writes the final script.

Import after creating the n8n owner account:

```powershell
docker compose --env-file infra/.env -f infra/compose.yml exec n8n `
  n8n import:workflow --input=/opt/giani/workflows/newsroom-research-digest.json
```

Alternatively use **Workflows → Import from file** in the n8n editor. The imported workflow is deliberately inactive. Run it manually, inspect the top-eight output, then activate it.

Telegram remains off unless all three operator actions are completed:

1. Create a Telegram bot and add its token as an **n8n Telegram API credential**. Do not put the bot token in the repository or a workflow expression.
2. Select that credential on the `Optional Telegram delivery` node and put the non-secret destination ID in `TELEGRAM_CHAT_ID`.
3. Set `TELEGRAM_ENABLED=true`, recreate n8n, run manually, and only then activate the schedule.

The workflow uses trusted environment expressions, so Compose sets `N8N_BLOCK_ENV_ACCESS_IN_NODE=false`. Do not import unreviewed workflows into this instance.

## Oracle VM production steps

Free-tier shape, quota, and regional capacity change. Verify the current Oracle documentation before provisioning.

1. Create an Ubuntu 22.04 ARM instance using `VM.Standard.A1.Flex`. The plan assumes up to 4 OCPU and 24 GB RAM, subject to current tenancy limits and regional capacity.
2. Download and back up the SSH private key during creation. Restrict SSH ingress to the operator IP.
3. Create a small billing budget alert even if the selected resources are marked Always Free.
4. Point two DNS records at the VM, for example `desk.example.com` and `automation.example.com`.
5. Open TCP 80 and 443, plus UDP 443 for HTTP/3. Do **not** open 5678, 8000, or 8080. Account for both Oracle security lists/network security groups and the Ubuntu firewall.
6. Install Docker Engine and the Compose v2 plugin from Docker's official Ubuntu repository. Confirm `docker compose version`; the obsolete `docker-compose` v1 package is not sufficient.
7. Copy or clone the repository onto the VM. Create `infra/.env` with:

   ```dotenv
   NEWSROOM_SITE=desk.example.com
   N8N_SITE=automation.example.com
   N8N_HOST=automation.example.com
   N8N_PROTOCOL=https
   N8N_EDITOR_BASE_URL=https://automation.example.com/
   N8N_WEBHOOK_URL=https://automation.example.com/
   N8N_SECURE_COOKIE=true
   ```

8. Generate production secrets and password hashes on the VM. Start with the same Compose commands used locally.
9. Confirm every container is healthy, create the n8n owner immediately, import/test the workflow, and verify that Caddy obtained certificates.
10. Back up `newsroom_data`, `n8n_data`, and the untracked environment file on a schedule. Test a restore before relying on the backup.

Caddy obtains and renews public certificates automatically when DNS and ingress are correct. Its named volumes preserve ACME state across container replacement.

## Kaggle LatentSync worker

The private notebook is [latentsync_1_6_render.ipynb](kaggle/latentsync_1_6_render.ipynb). It is pinned to ByteDance LatentSync commit `a229c3948406bc2cf6eaf4873e662e70c6a04746` and follows the official 1.6 checkpoint/config/inference commands.

One-time operator steps:

1. Phone-verify the Kaggle account and create a **private** notebook.
2. Upload/import the notebook, enable Internet, and select a GPU accelerator.
3. Confirm one GPU has at least 18 GB VRAM. The notebook checks each device independently.
4. Add these Kaggle Secrets and attach them to the notebook:

   | Secret | Required | Value |
   |---|---:|---|
   | `R2_ANCHOR_VIDEO_GET_URL` | yes | Short-lived signed GET for the canonical idle video |
   | `R2_VOICE_AUDIO_GET_URL` | yes | Short-lived signed GET for the approved voice |
   | `R2_SYNCED_VIDEO_PUT_URL` | no | Signed PUT for `anchor_synced.mp4` |
   | `R2_CAPTIONS_PUT_URL` | no | Signed PUT for `subs.srt` |
   | `R2_RENDER_MANIFEST_PUT_URL` | no | Signed PUT for `render_manifest.json` |

5. Generate signed URLs outside the notebook with the narrowest bucket/key permission and practical expiry. If a signed PUT includes `Content-Type` in its signature, use `video/mp4`, `application/x-subrip; charset=utf-8`, or `application/json` exactly as the notebook sends it.
6. Run all cells. Review the three files under `/kaggle/working/giani_output`.

Signed URLs are bearer secrets. The notebook never prints them or writes them into the output manifest; it stores only SHA-256 fingerprints.

### T4 correction and fallback

ByteDance documents **18 GB minimum VRAM for LatentSync 1.6**. A T4 has 16 GB. `T4 x2` still provides 16 GB per device because the official inference process does not pool both cards. This notebook therefore stops before installing/running 1.6 on a T4.

LatentSync 1.5 is not implemented in this notebook; silently switching checkpoints and configs would make the render non-reproducible. If Kaggle offers only a 16 GB card:

1. stop this notebook;
2. use the official [MuseTalk](https://github.com/TMElyralab/MuseTalk) inference path as the documented lighter fallback, in a separate pinned notebook/environment;
3. keep the same signed-input/output contract and review the face for artifacts before assembly.

Do not set up a fake aggregate-VRAM check and do not attempt to publish an out-of-memory partial render.

Kaggle does not offer this repository an inbound webhook. The supported first version is manual **Run All**. Later automation can push a private kernel with `kaggle kernels push`, poll `kaggle kernels status`, and retrieve artifacts with `kaggle kernels output`; daily input transfer should still use expiring R2 signed URLs or another private job manifest.

## Security and operating limits

- `.env` and credentials are intentionally absent. Do not commit either.
- Required secrets and Basic Auth hashes are blank in `.env.example`, so Compose fails closed until they are set.
- n8n Community Edition is fair-code and appropriate for this internal automation; review its license before offering automation as a service.
- n8n uses its embedded SQLite database here, appropriate for one operator. Queue mode and multi-instance scaling require a different database/worker design.
- Caddy protects the UI/API but does not add application-level roles. Do not make the desk public as a multi-user service without adding real authorization.
- R2 bucket creation, signed-URL generation, model accounts, and publishing credentials are manual prerequisites.
- Provider/free-tier quotas and image versions are time-sensitive. Re-check before production updates.
- Episode review, compliance approval, synthetic-content disclosure, and upload remain human actions.

## Post Studio and Instagram publishing

Post Studio is the one path that can publish on its own. It stays disabled
until `INSTAGRAM_PUBLISH_ENABLED=true`, and even then every post needs an
explicit human approval of the exact revision plus a typed confirmation.

Two deployment notes matter here:

- **`/api/public/media/*` is exempt from Caddy's basic auth.** Instagram fetches
  post media from its own servers with no credentials, so that one path must be
  open. Its forty character per-asset token is the capability, and tokens are
  replaced whenever slides are regenerated. Every other path stays gated.
- **`NEWSROOM_PUBLIC_BASE_URL` must be the real public HTTPS name** of the
  newsroom site, or set `NEWSROOM_MEDIA_HOST=s3` and publish media from a
  bucket instead. Instagram will not fetch from a private address, and it
  requires HTTPS.

Set the image provider key, the media host, and the Meta/Instagram credentials in
`infra/.env`. The same variable names work when running the API directly on
your laptop — only the public media URL differs:

| | Local (uvicorn) | Production (Compose + Caddy) |
|---|---|---|
| API keys | PowerShell `$env:...` or a local `.env` loader | `infra/.env` |
| Public media | Tunnel (`cloudflared`, ngrok) → `NEWSROOM_PUBLIC_BASE_URL` | `NEWSROOM_SITE=desk.example.com` (HTTPS derived automatically) or explicit `NEWSROOM_PUBLIC_BASE_URL`, or `NEWSROOM_MEDIA_HOST=s3` |
| Meta app + token | `META_APP_ID`, `META_APP_SECRET`, `INSTAGRAM_USER_ID`, `META_ACCESS_TOKEN` | Same names in `infra/.env` |
| Token exchange | `POST /api/instagram/exchange-token` after pasting a short-lived token | Same endpoint, behind Caddy basic auth |

Setup is documented in
[Instagram-Post-Pipeline.md](../Instagram-Post-Pipeline.md).
