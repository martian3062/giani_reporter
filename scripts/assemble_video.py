#!/usr/bin/env python3
"""Deterministic FFmpeg assembly engine used by the PowerShell and Bash entry points."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import platform
import shlex
import shutil
import subprocess
import sys
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ASPECTS = {
    "vertical": {"width": 1080, "height": 1920, "caption_margin": 150},
    "horizontal": {"width": 1920, "height": 1080, "caption_margin": 72},
}


class BuildError(RuntimeError):
    """An actionable operator-facing build failure."""


@dataclass(frozen=True)
class Cue:
    start: float
    end: float
    path: Path
    fit: str
    label: str


class CommandRecorder:
    def __init__(self, *, dry_run: bool) -> None:
        self.dry_run = dry_run
        self.commands: list[dict[str, Any]] = []

    def run(
        self,
        step: str,
        arguments: list[str],
        *,
        cwd: Path,
        execute_in_dry_run: bool = False,
        capture: bool = False,
    ) -> subprocess.CompletedProcess[str] | None:
        command = [str(value) for value in arguments]
        self.commands.append(
            {
                "step": step,
                "cwd": str(cwd),
                "argv": command,
                "display": shlex.join(command),
            }
        )
        prefix = "[dry-run] " if self.dry_run and not execute_in_dry_run else ""
        print(f"{prefix}{step}: {shlex.join(command)}")
        if self.dry_run and not execute_in_dry_run:
            return None
        try:
            return subprocess.run(
                command,
                cwd=cwd,
                check=True,
                text=True,
                capture_output=capture,
            )
        except subprocess.CalledProcessError as exc:
            details = (exc.stderr or exc.stdout or "").strip()
            if details:
                raise BuildError(f"{step} failed:\n{details}") from exc
            raise BuildError(f"{step} failed with exit code {exc.returncode}.") from exc


def require_tool(name: str, install_hint: str) -> str:
    executable = shutil.which(name)
    if executable:
        return executable
    raise BuildError(
        f"Required command {name!r} was not found on PATH. {install_hint} "
        "Open a new terminal after installation and retry."
    )


def require_file(value: str | Path, label: str) -> Path:
    path = Path(value).expanduser().resolve()
    if not path.is_file():
        raise BuildError(f"{label} does not exist or is not a file: {path}")
    if path.stat().st_size == 0:
        raise BuildError(f"{label} is empty: {path}")
    return path


def read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BuildError(f"{label} is not valid UTF-8 JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise BuildError(f"{label} must contain one JSON object: {path}")
    return value


def probe_media(
    ffprobe: str,
    path: Path,
    recorder: CommandRecorder,
    *,
    cwd: Path,
    step: str,
) -> dict[str, Any]:
    result = recorder.run(
        step,
        [
            ffprobe,
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(path),
        ],
        cwd=cwd,
        execute_in_dry_run=True,
        capture=True,
    )
    assert result is not None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise BuildError(f"ffprobe returned invalid JSON for {path}.") from exc


def duration_seconds(probe: dict[str, Any], label: str) -> float:
    try:
        value = float(probe.get("format", {}).get("duration") or 0)
    except (TypeError, ValueError) as exc:
        raise BuildError(f"ffprobe did not report a numeric duration for {label}.") from exc
    if not math.isfinite(value) or value <= 0:
        raise BuildError(f"ffprobe did not report a positive duration for {label}.")
    return value


def require_stream(probe: dict[str, Any], stream_type: str, label: str) -> None:
    streams = probe.get("streams")
    if not isinstance(streams, list) or not any(
        stream.get("codec_type") == stream_type
        for stream in streams
        if isinstance(stream, dict)
    ):
        raise BuildError(f"{label} has no {stream_type} stream.")


def finite_number(value: Any, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise BuildError(f"{label} must be numeric.") from exc
    if not math.isfinite(number):
        raise BuildError(f"{label} must be finite.")
    return number


def load_cues(cue_sheet: Path, voice_duration: float) -> tuple[dict[str, Any], list[Cue]]:
    document = read_json(cue_sheet, "Cue sheet")
    if document.get("schema_version") != 1:
        raise BuildError("Cue sheet schema_version must be 1.")
    raw_cues = document.get("cues", [])
    if not isinstance(raw_cues, list):
        raise BuildError("Cue sheet 'cues' must be an array.")

    cues: list[Cue] = []
    for index, raw in enumerate(raw_cues, start=1):
        if not isinstance(raw, dict):
            raise BuildError(f"Cue {index} must be an object.")
        start = finite_number(raw.get("start_seconds"), f"Cue {index} start_seconds")
        end = finite_number(raw.get("end_seconds"), f"Cue {index} end_seconds")
        if start < 0 or end <= start:
            raise BuildError(f"Cue {index} must satisfy 0 <= start_seconds < end_seconds.")
        if end > voice_duration + 0.05:
            raise BuildError(
                f"Cue {index} ends at {end:.3f}s, after the {voice_duration:.3f}s voice."
            )
        fit = str(raw.get("fit", "cover")).lower()
        if fit not in {"cover", "contain"}:
            raise BuildError(f"Cue {index} fit must be 'cover' or 'contain'.")
        file_value = raw.get("file")
        if not isinstance(file_value, str) or not file_value.strip():
            raise BuildError(f"Cue {index} must provide a non-empty file path.")
        candidate = Path(file_value).expanduser()
        if not candidate.is_absolute():
            candidate = cue_sheet.parent / candidate
        path = require_file(candidate, f"Cue {index} B-roll")
        cues.append(
            Cue(
                start=start,
                end=end,
                path=path,
                fit=fit,
                label=str(raw.get("label") or f"cue-{index}"),
            )
        )

    cues.sort(key=lambda cue: (cue.start, cue.end))
    for previous, current in zip(cues, cues[1:]):
        if current.start < previous.end:
            raise BuildError(
                f"B-roll cues overlap: {previous.label!r} ends at {previous.end:.3f}s "
                f"but {current.label!r} starts at {current.start:.3f}s."
            )
    return document, cues


def choose_font(workspace: Path) -> tuple[Path, str]:
    configured = os.environ.get("GIANI_FONT_FILE")
    candidates: list[tuple[Path, str]] = []
    if configured:
        candidates.append((Path(configured).expanduser(), "Giani Font"))

    repository_font = Path(__file__).resolve().parents[1] / "assets" / "fonts" / "Montserrat-Bold.ttf"
    candidates.extend(
        [
            (repository_font, "Montserrat"),
            (Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "Montserrat-Bold.ttf", "Montserrat"),
            (Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "arialbd.ttf", "Arial"),
            (Path("/usr/share/fonts/truetype/montserrat/Montserrat-Bold.ttf"), "Montserrat"),
            (Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"), "DejaVu Sans"),
            (Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"), "Liberation Sans"),
            (Path("/Library/Fonts/Montserrat-Bold.ttf"), "Montserrat"),
            (Path("/Library/Fonts/Arial Bold.ttf"), "Arial"),
            (Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"), "Arial"),
        ]
    )
    for source, family in candidates:
        if source.is_file() and source.stat().st_size > 0:
            destination = workspace / "font.ttf"
            shutil.copy2(source, destination)
            return destination, family
    raise BuildError(
        "No usable caption font was found. Install Montserrat, Arial, DejaVu Sans, "
        "or Liberation Sans; alternatively set GIANI_FONT_FILE to a bold .ttf file."
    )


def escape_ass_value(value: str) -> str:
    return value.replace("\\", "").replace(",", " ").replace("'", "")


def check_ffmpeg_filters(ffmpeg: str) -> None:
    result = subprocess.run(
        [ffmpeg, "-hide_banner", "-filters"],
        check=True,
        text=True,
        capture_output=True,
    )
    listing = result.stdout + result.stderr
    missing = [
        name
        for name in ("overlay", "subtitles", "drawtext", "drawbox")
        if name not in listing
    ]
    if missing:
        raise BuildError(
            "This FFmpeg build lacks required filters: "
            + ", ".join(missing)
            + ". Install a full FFmpeg build with libass and libfreetype support."
        )


def write_text(path: Path, text: str) -> None:
    path.write_text(text.replace("\r", " ").replace("\n", " ").strip() + "\n", encoding="utf-8")


def fit_filter(width: int, height: int, fit: str) -> str:
    if fit == "contain":
        return (
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black"
        )
    return (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height}"
    )


def format_number(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".")


def parse_arguments(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Assemble an AI-news episode with FFmpeg and an audited cue sheet."
    )
    parser.add_argument(
        "--anchor",
        required=True,
        help="LatentSync output in synced mode, or canonical idle clip in idle mode.",
    )
    parser.add_argument("--voice", required=True, help="Approved voice audio.")
    parser.add_argument("--captions", required=True, help="Reviewed UTF-8 SRT captions.")
    parser.add_argument("--cue-sheet", required=True, help="Version-1 cue JSON.")
    parser.add_argument("--output", required=True, help="Final MP4 path.")
    parser.add_argument("--aspect", choices=sorted(ASPECTS), default="vertical")
    parser.add_argument(
        "--anchor-mode",
        choices=("synced", "idle"),
        default="synced",
        help=(
            "'synced' consumes the production LatentSync output. 'idle' builds a "
            "ping-pong bed but is not lip-synced."
        ),
    )
    parser.add_argument(
        "--allow-unsynced",
        action="store_true",
        help="Required for a non-dry-run build with --anchor-mode idle.",
    )
    parser.add_argument(
        "--command-manifest",
        help="JSON command-manifest path (default: <output>.commands.json).",
    )
    parser.add_argument("--dry-run", action="store_true", help="Probe and validate, then record but do not run FFmpeg transforms.")
    parser.add_argument("--keep-temp", action="store_true", help="Keep intermediate files for diagnosis.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_arguments(argv or sys.argv[1:])
    install_hint = (
        "Install FFmpeg from https://ffmpeg.org/download.html or with "
        "`winget install Gyan.FFmpeg`, `brew install ffmpeg`, or your Linux package manager."
    )
    ffmpeg = require_tool("ffmpeg", install_hint)
    ffprobe = require_tool("ffprobe", install_hint)
    check_ffmpeg_filters(ffmpeg)

    anchor = require_file(args.anchor, "Anchor video")
    voice = require_file(args.voice, "Voice audio")
    captions = require_file(args.captions, "Captions")
    cue_sheet = require_file(args.cue_sheet, "Cue sheet")
    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.suffix.lower() != ".mp4":
        raise BuildError("Output must use an .mp4 extension.")
    manifest_path = (
        Path(args.command_manifest).expanduser().resolve()
        if args.command_manifest
        else output.with_suffix(output.suffix + ".commands.json")
    )
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    recorder = CommandRecorder(dry_run=args.dry_run)
    workspace = Path(
        tempfile.mkdtemp(prefix=".giani-assemble-", dir=str(output.parent))
    ).resolve()
    completed = False
    partial_path: Path | None = None
    try:
        anchor_probe = probe_media(
            ffprobe, anchor, recorder, cwd=workspace, step="probe anchor"
        )
        voice_probe = probe_media(
            ffprobe, voice, recorder, cwd=workspace, step="probe voice"
        )
        require_stream(anchor_probe, "video", "Anchor")
        require_stream(voice_probe, "audio", "Voice")
        anchor_duration = duration_seconds(anchor_probe, "anchor")
        voice_duration = duration_seconds(voice_probe, "voice")
        if voice_duration > 15 * 60:
            raise BuildError("Voice exceeds the supported 15-minute assembly ceiling.")
        if args.anchor_mode == "idle" and not args.dry_run and not args.allow_unsynced:
            raise BuildError(
                "--anchor-mode idle creates the required ping-pong loop but cannot "
                "lip-sync it. Use the Kaggle LatentSync output with --anchor-mode synced, "
                "or pass --allow-unsynced only for an intentional fallback/test render."
            )
        if args.anchor_mode == "synced" and abs(anchor_duration - voice_duration) > 0.75:
            raise BuildError(
                f"Synced anchor duration ({anchor_duration:.3f}s) differs from voice "
                f"({voice_duration:.3f}s) by more than 0.75s. Re-run the lip-sync job."
            )

        cue_document, cues = load_cues(cue_sheet, voice_duration)
        aspect = ASPECTS[args.aspect]
        width = int(aspect["width"])
        height = int(aspect["height"])
        caption_margin = int(aspect["caption_margin"])

        lower = cue_document.get("lower_third") or {}
        if not isinstance(lower, dict):
            raise BuildError("Cue sheet lower_third must be an object.")
        lower_name = str(lower.get("name") or "Mira")
        lower_title = str(lower.get("title") or "AI Desk")
        lower_date = str(lower.get("date") or dt.date.today().isoformat())
        lower_start = finite_number(lower.get("start_seconds", 3), "lower_third start_seconds")
        lower_end = finite_number(lower.get("end_seconds", 10), "lower_third end_seconds")
        if lower_start < 0 or lower_end <= lower_start or lower_end > voice_duration + 0.05:
            raise BuildError("lower_third must fit inside the voice duration.")

        end_card = cue_document.get("end_card") or {}
        if not isinstance(end_card, dict):
            raise BuildError("Cue sheet end_card must be an object.")
        end_text = str(end_card.get("text") or "Full breakdown Saturday  •  Subscribe")
        end_seconds = finite_number(end_card.get("duration_seconds", 5), "end_card duration_seconds")
        if not 1 <= end_seconds <= 15:
            raise BuildError("end_card duration_seconds must be between 1 and 15.")

        copied_captions = workspace / "captions.srt"
        copied_captions.write_text(
            captions.read_text(encoding="utf-8-sig"), encoding="utf-8", newline="\n"
        )
        font_path, font_family = choose_font(workspace)
        write_text(
            workspace / "lower_third.txt",
            f"{lower_name}  •  {lower_title}  •  {lower_date}",
        )
        write_text(workspace / "end_card.txt", end_text)

        loop_path = workspace / "anchor_pingpong.mp4"
        bed_path = workspace / "anchor_bed.mp4"
        main_path = workspace / "episode_main.mp4"
        card_path = workspace / "end_card.mp4"
        partial_path = output.parent / (
            f".{output.stem}.partial-{os.getpid()}-{uuid.uuid4().hex}.mp4"
        )

        if args.anchor_mode == "idle":
            recorder.run(
                "create ping-pong anchor",
                [
                    ffmpeg,
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-i",
                    str(anchor),
                    "-filter_complex",
                    (
                        f"[0:v]fps=25,{fit_filter(width, height, 'cover')},setsar=1,"
                        "split=2[forward][reverse_in];[reverse_in]reverse[reverse];"
                        "[forward][reverse]concat=n=2:v=1:a=0,format=yuv420p[out]"
                    ),
                    "-map",
                    "[out]",
                    "-an",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "medium",
                    "-crf",
                    "18",
                    str(loop_path),
                ],
                cwd=workspace,
            )

            recorder.run(
                "extend anchor to voice duration",
                [
                    ffmpeg,
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-stream_loop",
                    "-1",
                    "-i",
                    str(loop_path),
                    "-t",
                    format_number(voice_duration),
                    "-an",
                    "-r",
                    "25",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "medium",
                    "-crf",
                    "18",
                    "-pix_fmt",
                    "yuv420p",
                    str(bed_path),
                ],
                cwd=workspace,
            )
        else:
            recorder.run(
                "normalize synced anchor",
                [
                    ffmpeg,
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-i",
                    str(anchor),
                    "-t",
                    format_number(voice_duration),
                    "-vf",
                    f"fps=25,{fit_filter(width, height, 'cover')},setsar=1,format=yuv420p",
                    "-an",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "medium",
                    "-crf",
                    "18",
                    str(bed_path),
                ],
                cwd=workspace,
            )

        composite_arguments = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(bed_path),
            "-i",
            str(voice),
        ]
        for cue in cues:
            composite_arguments.extend(["-stream_loop", "-1", "-i", str(cue.path)])

        filters = ["[0:v]setpts=PTS-STARTPTS[base0]"]
        base_label = "base0"
        for index, cue in enumerate(cues, start=1):
            input_index = index + 1
            cue_duration = cue.end - cue.start
            cue_label = f"cue{index}"
            next_base = f"base{index}"
            filters.append(
                f"[{input_index}:v]fps=25,{fit_filter(width, height, cue.fit)},"
                f"trim=duration={format_number(cue_duration)},"
                f"setpts=PTS-STARTPTS+{format_number(cue.start)}/TB[{cue_label}]"
            )
            filters.append(
                f"[{base_label}][{cue_label}]overlay=0:0:eof_action=pass:repeatlast=0:"
                f"enable='between(t,{format_number(cue.start)},{format_number(cue.end)})'"
                f"[{next_base}]"
            )
            base_label = next_base

        safe_family = escape_ass_value(font_family)
        filters.append(
            f"[{base_label}]subtitles=filename=captions.srt:fontsdir=.:"
            "force_style='"
            f"FontName={safe_family},FontSize=18,Bold=1,"
            "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
            f"BorderStyle=1,Outline=3,Shadow=0,Alignment=2,MarginV={caption_margin}"
            "'[captioned]"
        )
        lower_height = 112 if args.aspect == "vertical" else 76
        lower_y = height - (390 if args.aspect == "vertical" else 200)
        lower_font_size = 46 if args.aspect == "vertical" else 34
        filters.append(
            "[captioned]"
            f"drawbox=x=0:y={lower_y}:w=iw:h={lower_height}:"
            "color=0x0B1220@0.86:t=fill:"
            f"enable='between(t,{format_number(lower_start)},{format_number(lower_end)})'"
            "[lowerbox]"
        )
        filters.append(
            "[lowerbox]"
            "drawtext=fontfile=font.ttf:textfile=lower_third.txt:"
            f"fontcolor=white:fontsize={lower_font_size}:x=48:y={lower_y + 26}:"
            f"enable='between(t,{format_number(lower_start)},{format_number(lower_end)})'"
            "[video_out]"
        )
        composite_arguments.extend(
            [
                "-filter_complex",
                ";".join(filters),
                "-map",
                "[video_out]",
                "-map",
                "1:a:0",
                "-filter:a",
                (
                    "aresample=48000,"
                    "aformat=sample_fmts=fltp:channel_layouts=stereo,"
                    f"apad,atrim=0:{format_number(voice_duration)}"
                ),
                "-t",
                format_number(voice_duration),
                "-r",
                "25",
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "18",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-ar",
                "48000",
                "-movflags",
                "+faststart",
                str(main_path),
            ]
        )
        recorder.run("overlay cues, captions, and lower third", composite_arguments, cwd=workspace)

        recorder.run(
            "create end card",
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"color=c=0x0B1220:s={width}x{height}:r=25:d={format_number(end_seconds)}",
                "-f",
                "lavfi",
                "-i",
                "anullsrc=channel_layout=stereo:sample_rate=48000",
                "-filter:v",
                (
                    "drawtext=fontfile=font.ttf:textfile=end_card.txt:"
                    f"fontcolor=white:fontsize={58 if args.aspect == 'vertical' else 48}:"
                    "x=(w-text_w)/2:y=(h-text_h)/2"
                ),
                "-t",
                format_number(end_seconds),
                "-r",
                "25",
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "18",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-ar",
                "48000",
                "-shortest",
                str(card_path),
            ],
            cwd=workspace,
        )

        recorder.run(
            "append end card",
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(main_path),
                "-i",
                str(card_path),
                "-filter_complex",
                (
                    "[0:v]setpts=PTS-STARTPTS[v0];[0:a]asetpts=PTS-STARTPTS[a0];"
                    "[1:v]setpts=PTS-STARTPTS[v1];[1:a]asetpts=PTS-STARTPTS[a1];"
                    "[v0][a0][v1][a1]concat=n=2:v=1:a=1[v][a]"
                ),
                "-map",
                "[v]",
                "-map",
                "[a]",
                "-r",
                "25",
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "18",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-ar",
                "48000",
                "-movflags",
                "+faststart",
                str(partial_path),
            ],
            cwd=workspace,
        )

        final_probe: dict[str, Any] | None = None
        if not args.dry_run:
            final_probe = probe_media(
                ffprobe,
                partial_path,
                recorder,
                cwd=workspace,
                step="validate assembled output",
            )
            require_stream(final_probe, "video", "Assembled output")
            require_stream(final_probe, "audio", "Assembled output")
            final_duration = duration_seconds(final_probe, "assembled output")
            expected_duration = voice_duration + end_seconds
            if abs(final_duration - expected_duration) > 0.75:
                raise BuildError(
                    f"Assembled duration {final_duration:.3f}s differs from expected "
                    f"{expected_duration:.3f}s by more than 0.75s."
                )
            os.replace(partial_path, output)
            completed = True
            print(f"Published atomically: {output}")

        manifest = {
            "schema_version": 1,
            "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "status": "dry_run" if args.dry_run else "complete",
            "platform": {
                "system": platform.system(),
                "release": platform.release(),
                "python": platform.python_version(),
            },
            "inputs": {
                "anchor": str(anchor),
                "voice": str(voice),
                "captions": str(captions),
                "cue_sheet": str(cue_sheet),
            },
            "output": str(output),
            "aspect": args.aspect,
            "anchor_mode": args.anchor_mode,
            "resolution": {"width": width, "height": height},
            "voice_duration_seconds": voice_duration,
            "end_card_duration_seconds": end_seconds,
            "cue_count": len(cues),
            "font": {"family": font_family, "source": str(font_path)},
            "commands": recorder.commands,
            "atomic_publish": not args.dry_run,
            "warnings": (
                ["Output is not lip-synced because --anchor-mode idle was selected."]
                if args.anchor_mode == "idle"
                else []
            ),
        }
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(f"Command manifest: {manifest_path}")
        if args.dry_run:
            print("Dry run complete; no video was written.")
        return 0
    finally:
        if args.keep_temp:
            print(f"Intermediate workspace retained: {workspace}")
        else:
            shutil.rmtree(workspace, ignore_errors=True)
        if (
            not completed
            and not args.dry_run
            and partial_path is not None
            and partial_path.is_file()
        ):
            try:
                partial_path.unlink()
            except OSError:
                pass


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BuildError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
