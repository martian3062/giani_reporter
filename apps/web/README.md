# GIANI / Signal Desk

Editorial control center for the AI news anchor workflow. This package is a
React 19 + React Router 8 + TypeScript + Vite single-page application with six
routes:

- **Overview** — today’s rundown, Mira preview, timing, pipeline, and archive
- **Research** — ranked story notes with an exactly-three selection guard
- **Studio** — mandatory human angle, editable structured script, visual cues,
  compliance, voice, render, and publish-package controls
- **Library** — canonical Mira asset plus the 15 numbered B-roll slots
- **Runs** — polling render-job progress and honest output paths
- **Settings** — browser-safe API and optional provider configuration guidance

## Run

```powershell
cd E:\giani_reporter\apps\web
npm install
npm run dev
```

The development server listens on `http://127.0.0.1:5173`.

To point at a separate backend:

```powershell
Copy-Item .env.example .env.local
```

Then set:

```dotenv
VITE_API_URL=http://127.0.0.1:8000/api
```

Without `VITE_API_URL`, requests use `/api`, which is suitable for a same-origin
reverse proxy.

## Offline demo behavior

If health, story, and episode reads cannot establish an API connection, the
desk opens a clearly labeled fictional demo dataset. Demo changes persist in
browser storage. Demo voice files and render progress are simulations and are
labeled as such; the UI never claims a video or audio file was generated.

When the API is connected, backend episodes are adapted from their wire shape:

- `sections: Record<string, string>` becomes ordered editable section rows
- `compliance: Record<string, boolean>` becomes labeled producer gates
- backend cue/overlay timestamps become the Studio timeline model
- PATCH requests serialize only fields accepted by `EpisodePatch`

Provider secrets are never read by this app. Anthropic, ElevenLabs, R2, and
Kaggle credentials belong in the backend environment and must not use a
`VITE_` prefix.

## Quality checks

```powershell
npm test
npm run build
npm audit --audit-level=high
```

The test suite includes route-level smoke coverage, the three-story selection
guard, the mandatory-angle gate, and a raw backend-response contract fixture
for episode normalization and safe PATCH/DraftRequest serialization.

The real-browser suite uses installed Microsoft Edge at desktop and 390 px
mobile widths. Start the API and Vite server first, then run:

```powershell
npm run test:e2e
```

The desktop test completes the connected workflow from research through
manual approval, demo voice, render manifest, and publish package. The mobile
test verifies navigation and guards against horizontal overflow.

## Asset

The canonical vertical anchor image is served from:

```text
public/anchor/mira-anchor-vertical.png
```
