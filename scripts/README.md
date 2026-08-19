# Render assembly scripts

The assembly entry points are:

- `assemble.ps1` — primary Windows/PowerShell interface;
- `assemble.sh` — Bash interface for Linux, macOS, WSL, and the Oracle host;
- `assemble_video.py` — shared cross-platform engine so both interfaces execute identical FFmpeg stages.

They do not download tools, models, media, or fonts. Missing prerequisites fail with an actionable message.

## Prerequisites

- Python 3.10 or newer.
- `ffmpeg` and `ffprobe` on `PATH`.
- A full FFmpeg build containing `overlay`, `subtitles`/libass, `drawtext`, and `drawbox`.
- Montserrat, Arial, DejaVu Sans, or Liberation Sans. Set `GIANI_FONT_FILE` to a bold `.ttf` if automatic discovery cannot find one.
- A reviewed voice file, reviewed UTF-8 SRT, cue JSON, and either:
  - the production `anchor_synced.mp4` from the Kaggle notebook; or
  - an idle canonical loop for an explicitly unsynced test/fallback.

The scripts probe actual media duration with `ffprobe`; there is no hard-coded 92-second assumption.

## Production assembly

PowerShell:

```powershell
.\scripts\assemble.ps1 `
  -Anchor .\work\anchor_synced.mp4 `
  -Voice .\work\voice.mp3 `
  -Captions .\work\subs.srt `
  -CueSheet .\work\episode-cues.json `
  -Output .\dist\episode-2026-07-27.mp4 `
  -Aspect vertical `
  -AnchorMode synced
```

Bash:

```bash
bash ./scripts/assemble.sh \
  --anchor ./work/anchor_synced.mp4 \
  --voice ./work/voice.mp3 \
  --captions ./work/subs.srt \
  --cue-sheet ./work/episode-cues.json \
  --output ./dist/episode-2026-07-27.mp4 \
  --aspect vertical \
  --anchor-mode synced
```

Use `horizontal` for the weekly 16:9 episode. The output is 1080×1920 or 1920×1080, H.264/yuv420p at 25 fps with AAC stereo audio.

Production mode consumes the LatentSync output and deliberately ignores any audio embedded in that video. It maps the separately approved voice as the only audio source, so B-roll can never replace or mix over the narration.

## Cue sheet

Copy [cues.example.json](cues.example.json), change the episode metadata, then move reviewed entries from `cue_template` into `cues`. Relative media paths resolve from the cue-sheet directory.

```json
{
  "schema_version": 1,
  "lower_third": {
    "name": "Mira",
    "title": "AI Desk",
    "date": "2026-07-27",
    "start_seconds": 3,
    "end_seconds": 10
  },
  "end_card": {
    "text": "Full breakdown Saturday  •  Subscribe",
    "duration_seconds": 5
  },
  "cues": [
    {
      "label": "Story 1 coverage",
      "start_seconds": 12,
      "end_seconds": 17,
      "file": "../assets/broll/clips/03-code-scroll-vertical.mp4",
      "fit": "cover"
    }
  ]
}
```

Rules enforced by the engine:

- schema version must be `1`;
- `0 <= start_seconds < end_seconds`;
- a cue cannot extend past voice duration;
- cues cannot overlap;
- every referenced clip must exist and contain data;
- `fit` is `cover` or `contain`;
- lower third must fit inside narration;
- end card is 1–15 seconds.

The machine-readable schema is [cues.schema.json](cues.schema.json). The 15 canonical prompts and expected media specs are in [the B-roll manifest](../assets/broll/manifest.json). No fake clip files are present; generate and review the real videos before adding cue entries.

## What the engine does

For `--anchor-mode synced`:

1. validates anchor video, voice audio, SRT, cue JSON, B-roll, font, and FFmpeg filters;
2. probes voice and anchor duration and rejects a mismatch over 0.75 seconds;
3. normalizes the synced anchor to the selected aspect without reversing mouth motion;
4. overlays full-frame B-roll on the reviewed time ranges, without B-roll audio;
5. burns captions with a discovered fallback font;
6. draws the name/title/date lower third;
7. maps and normalizes the approved voice;
8. creates and appends the end card;
9. probes the finished streams and duration;
10. atomically renames a same-directory partial file to the requested output.

The idle path implements the required ping-pong loop:

```text
forward clip + reversed clip -> seamless-ish loop -> repeat to ffprobe voice duration
```

An idle loop is **not lip-synced**. A real render with `--anchor-mode idle` is blocked unless `--allow-unsynced` (PowerShell: `-AllowUnsynced`) is explicitly supplied. Use it only for diagnostics or a consciously chosen fallback; production should pass the Kaggle LatentSync output in `synced` mode.

## Dry run and command manifest

Dry run still requires real inputs, `ffmpeg`, and `ffprobe`. It validates/probes everything and records all transform commands without rendering:

```powershell
.\scripts\assemble.ps1 `
  -Anchor .\work\anchor_synced.mp4 `
  -Voice .\work\voice.mp3 `
  -Captions .\work\subs.srt `
  -CueSheet .\scripts\cues.example.json `
  -Output .\dist\episode.mp4 `
  -Aspect vertical `
  -DryRun
```

```bash
bash ./scripts/assemble.sh \
  --anchor ./work/anchor_synced.mp4 \
  --voice ./work/voice.mp3 \
  --captions ./work/subs.srt \
  --cue-sheet ./scripts/cues.example.json \
  --output ./dist/episode.mp4 \
  --aspect vertical \
  --dry-run
```

Every successful run writes `<output>.commands.json` unless `--command-manifest`/`-CommandManifest` is supplied. It contains each argument as a JSON array as well as a display string, the probed duration, aspect, font, cue count, and atomic-publish status. It contains paths but no provider credentials.

Use `--keep-temp` or `-KeepTemp` only while diagnosing a failed filter. Intermediate files can be large.

## Limitations

- Ping-pong endpoints can show a small pause when the source clip has duplicate first/last frames. Select a canonical loop with minimal head drift.
- Burned captions are phrase-level SRT cues generated from word timestamps; they are not animated karaoke captions.
- Full-frame B-roll is deterministic. Picture-in-picture, animated transitions, music mixing, and per-word highlighting are outside this v1 contract.
- The script does not run LatentSync or MuseTalk. Lip sync happens in the private GPU notebook before production assembly.
- Font metrics vary slightly across operating systems. Review at least one frame containing captions and the lower third before publishing.
- Atomic publish uses `os.replace` and therefore requires the partial and final paths to remain on the same filesystem; the engine always creates them in the same output directory.
