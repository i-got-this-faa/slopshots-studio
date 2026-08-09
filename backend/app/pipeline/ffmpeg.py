"""FFmpeg filtergraph generation, rendering, probing, and validation."""

from __future__ import annotations

import importlib.util
import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..errors import DependencyUnavailableError, PipelineError
from ..models import (
    Animation,
    EffectType,
    Timeline,
    ValidationCheck,
    ValidationResult,
    Zone,
)
from .placement import ZONE_RECTS
from .process import ProcessResult, require_executable, run_safe


def _filter_path(path: str | Path) -> str:
    """Escape a filesystem path for an FFmpeg filter argument."""

    return (
        str(path)
        .replace("\\", "\\\\")
        .replace(":", r"\:")
        .replace("'", r"\'")
        .replace(",", r"\,")
        .replace("[", r"\[")
        .replace("]", r"\]")
    )


def _duration_expression(seconds: float) -> str:
    return f"{seconds:.6f}".rstrip("0").rstrip(".")


def generate_filtergraph(timeline: Timeline, *, duration_s: float, overlay_count: int | None = None) -> str:
    """Generate the one-pass graph described in docs/08-render-ffmpeg.md."""

    if duration_s <= 0:
        raise ValueError("render duration must be positive")
    canvas = timeline.canvas
    duration = _duration_expression(duration_s)
    base_filters = [
        f"scale={canvas.w}:{canvas.h}:force_original_aspect_ratio=increase",
        f"crop={canvas.w}:{canvas.h}",
        f"fps={canvas.fps}",
        f"trim=duration={duration}",
        "setpts=PTS-STARTPTS",
    ]
    for effect in timeline.tracks.effects:
        if effect.type == EffectType.ZOOM_PUNCH:
            in_end = _duration_expression(effect.t + effect.in_s)
            out_end = _duration_expression(effect.t + effect.in_s + effect.out_s)
            zoom = (
                f"1+({effect.amount:g}-1)*if(lt(t\\,{_duration_expression(effect.t)}),0,"
                f"if(lt(t\\,{in_end}),(t-{_duration_expression(effect.t)})/{effect.in_s:g},"
                f"if(lt(t\\,{out_end}),1-(t-{in_end})/{effect.out_s:g},0)))"
            )
            base_filters.extend(
                [
                    f"scale=iw*({zoom}):ih*({zoom}):eval=frame",
                    f"crop={canvas.w}:{canvas.h}",
                ]
            )
        elif effect.type == EffectType.SHAKE:
            x = f"(iw-ow)/2+{effect.amp_px}*sin(2*PI*t*23)"
            y = f"(ih-oh)/2+{effect.amp_px}*cos(2*PI*t*19)"
            base_filters.append(
                f"crop={canvas.w}:{canvas.h}:x='{x}':y='{y}':"
                f"enable='between(t,{_duration_expression(effect.t)},{_duration_expression(effect.t + effect.duration_s)})'"
            )
        elif effect.type == EffectType.FLASH:
            base_filters.append(
                f"drawbox=x=0:y=0:w=iw:h=ih:color=white@0.8:t=fill:"
                f"enable='between(t,{_duration_expression(effect.t)},{_duration_expression(effect.t + 0.08)})'"
            )
        elif effect.type == EffectType.FADE:
            if effect.in_s is not None:
                base_filters.append(
                    f"fade=t=in:st={_duration_expression(effect.t)}:d={_duration_expression(effect.in_s)}"
                )
            if effect.out_s is not None:
                base_filters.append(
                    f"fade=t=out:st={_duration_expression(max(0, duration_s - effect.out_s))}:d={_duration_expression(effect.out_s)}"
                )
    video = f"[0:v]{','.join(base_filters)}[vbase]"
    graph = [video]
    current = "vbase"
    overlays = timeline.tracks.overlays
    if overlay_count is not None and overlay_count != len(overlays):
        raise ValueError("overlay input count does not match timeline")
    overlay_input_start = 3 if timeline.tracks.music else 2
    for index, overlay in enumerate(overlays, start=overlay_input_start):
        x, y, width, height = ZONE_RECTS[overlay.zone]
        scaled_width = max(1, round(width * overlay.scale))
        scaled_height = max(1, round(height * overlay.scale))
        overlay_label = f"ov{index}"
        graph.append(f"[{index}:v]format=rgba,scale={scaled_width}:{scaled_height}[{overlay_label}]")
        start = _duration_expression(overlay.t)
        end = _duration_expression(overlay.t + overlay.duration_s)
        x_expr, y_expr = str(x), str(y)
        if overlay.animation == Animation.SLIDE_UP:
            y_expr = f"{y}+max(0\\,{height}*(1-min(1\\,max(0\\,(t-{start})/0.20))))"
        elif overlay.animation == Animation.BOUNCE:
            y_expr = f"{y}-12*sin(min(1\\,max(0\\,(t-{start})/0.20))*PI)"
        next_label = f"v{index}"
        graph.append(
            f"[{current}][{overlay_label}]overlay=x={x_expr}:y={y_expr}:"
            f"eof_action=pass:enable='between(t,{start},{end})'[{next_label}]"
        )
        current = next_label

    subtitles = _filter_path(timeline.tracks.subtitles.ass)
    graph.append(f"[{current}]subtitles='{subtitles}'[vout]")

    voice_gain = timeline.tracks.voice.gain_db
    voice = (
        f"[1:a]aresample=48000,volume={voice_gain:g}dB,"
        f"atrim=duration={duration},asetpts=PTS-STARTPTS,"
        f"apad=whole_dur={duration}[voice]"
    )
    graph.append(voice)
    if timeline.tracks.music:
        music_gain = timeline.tracks.music.gain_db
        graph.append(
            f"[2:a]aresample=48000,volume={music_gain:g}dB,"
            f"atrim=duration={duration},asetpts=PTS-STARTPTS[music]"
        )
        graph.append(
            "[music][voice]sidechaincompress=threshold=0.02:ratio=8:"
            "attack=20:release=400:makeup=1[ducked]"
        )
        graph.append(
            f"[voice][ducked]amix=inputs=2:duration=first:dropout_transition=0,"
            "loudnorm=I=-14:TP=-1.5:LRA=11[aout]"
        )
    else:
        graph.append("[voice]loudnorm=I=-14:TP=-1.5:LRA=11[aout]")
    return ";".join(graph)


@dataclass(frozen=True)
class RenderResult:
    output_path: Path
    filtergraph: str
    command: list[str]


class FFmpegAdapter:
    """Real FFmpeg renderer. It never falls back to a Python or fake renderer."""

    def __init__(self, ffmpeg_bin: str = "ffmpeg", ffprobe_bin: str = "ffprobe") -> None:
        self.ffmpeg_bin = ffmpeg_bin
        self.ffprobe_bin = ffprobe_bin

    def availability(self) -> dict[str, bool]:
        return {
            "ffmpeg": shutil.which(self.ffmpeg_bin) is not None,
            "ffprobe": shutil.which(self.ffprobe_bin) is not None,
        }

    def render(
        self,
        timeline: Timeline,
        *,
        output_path: Path,
        duration_s: float,
        timeout_s: float = 3600,
        draft: bool = False,
        segment_from_s: float | None = None,
        segment_to_s: float | None = None,
    ) -> RenderResult:
        ffmpeg = require_executable(self.ffmpeg_bin, dependency="ffmpeg")
        if segment_from_s is not None and segment_to_s is not None:
            if segment_from_s < 0 or segment_to_s <= segment_from_s:
                raise PipelineError("segment render requires a positive from/to interval")
            duration_s = min(duration_s, segment_to_s - segment_from_s)

        graph = generate_filtergraph(timeline, duration_s=duration_s)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.unlink(missing_ok=True)
        command: list[str] = [ffmpeg, "-hide_banner", "-nostdin", "-y", "-loglevel", "error"]
        if segment_from_s is not None:
            command.extend(["-ss", _duration_expression(segment_from_s)])
        gameplay = str(timeline.tracks.gameplay.clip)
        command.extend(["-ss", _duration_expression(timeline.tracks.gameplay.start_offset_s), "-i", gameplay])
        command.extend(["-i", str(timeline.tracks.voice.file)])
        if timeline.tracks.music:
            command.extend(["-stream_loop", "-1", "-i", str(timeline.tracks.music.file)])
        for overlay in timeline.tracks.overlays:
            command.extend(["-loop", "1", "-i", str(overlay.asset)])
        command.extend(
            [
                "-filter_complex",
                graph,
                "-map",
                "[vout]",
                "-map",
                "[aout]",
                "-t",
                _duration_expression(duration_s),
                "-c:v",
                "libx264",
                "-preset",
                "veryfast" if draft else "slow",
                "-crf",
                "28" if draft else "18",
                "-pix_fmt",
                "yuv420p",
                "-r",
                str(timeline.canvas.fps),
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-ar",
                "48000",
                "-movflags",
                "+faststart",
                str(output_path),
            ]
        )
        run_safe(command, cwd=output_path.parent, timeout_s=timeout_s)
        if not output_path.is_file() or output_path.stat().st_size <= 0:
            raise PipelineError("FFmpeg completed without producing a non-empty output file")
        return RenderResult(output_path=output_path, filtergraph=graph, command=command)


class FFprobeValidationAdapter:
    """Run the mechanical validation gate against a rendered MP4."""

    def __init__(self, ffmpeg_bin: str = "ffmpeg", ffprobe_bin: str = "ffprobe") -> None:
        self.ffmpeg_bin = ffmpeg_bin
        self.ffprobe_bin = ffprobe_bin

    def probe(self, media_path: Path) -> dict[str, Any]:
        ffprobe = require_executable(self.ffprobe_bin, dependency="ffprobe")
        result = run_safe(
            [
                ffprobe,
                "-v",
                "error",
                "-show_streams",
                "-show_format",
                "-of",
                "json",
                str(media_path),
            ],
            timeout_s=120,
        )
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise PipelineError("ffprobe returned invalid JSON") from exc

    def validate(
        self,
        media_path: Path,
        *,
        expected_duration_s: float | None = None,
        subtitle_path: Path | None = None,
        timeout_s: float = 600,
    ) -> ValidationResult:
        ffmpeg = require_executable(self.ffmpeg_bin, dependency="ffmpeg")
        probe = self.probe(media_path)
        streams = probe.get("streams", [])
        video = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
        audio = next((stream for stream in streams if stream.get("codec_type") == "audio"), None)
        checks: list[ValidationCheck] = []
        errors: list[str] = []

        def check(name: str, passed: bool, detail: str) -> None:
            checks.append(ValidationCheck(name=name, passed=passed, detail=detail))
            if not passed:
                errors.append(f"{name}: {detail}")

        check("video_present", video is not None, "video stream is present" if video else "no video stream")
        check("audio_present", audio is not None, "audio stream is present" if audio else "no audio stream")
        if video:
            check(
                "resolution",
                video.get("width") == 1080 and video.get("height") == 1920,
                f"measured {video.get('width')}x{video.get('height')}, expected 1080x1920",
            )
            check("video_codec", video.get("codec_name") == "h264", f"measured {video.get('codec_name')}")
            check("pixel_format", video.get("pix_fmt") == "yuv420p", f"measured {video.get('pix_fmt')}")
            fps = _parse_rate(video.get("r_frame_rate"))
            check("frame_rate", abs(fps - 30) < 0.01, f"measured {fps:g}fps, expected 30fps")
        if audio:
            check("audio_codec", audio.get("codec_name") == "aac", f"measured {audio.get('codec_name')}")
            check("audio_rate", int(audio.get("sample_rate", 0)) == 48000, f"measured {audio.get('sample_rate')}")
        format_data = probe.get("format", {})
        duration = _as_float(format_data.get("duration"))
        if expected_duration_s is not None and duration is not None:
            check(
                "duration",
                abs(duration - expected_duration_s) <= 0.5 and duration <= 90.0 + 1e-6,
                f"measured {duration:.3f}s, expected about {expected_duration_s:.3f}s and <=90s",
            )
        elif duration is not None:
            check("duration_limit", duration <= 90.0 + 1e-6, f"measured {duration:.3f}s")
        check("container", "mp4" in str(format_data.get("format_name", "")).split(","), str(format_data.get("format_name")))

        # Run every content check in a single decode pass instead of one
        # ffmpeg invocation per filter (each pass fully decodes the file).
        legs: list[str] = []
        outputs: list[str] = []
        if video is not None:
            legs.append("[0:v]split=2[v_black][v_freeze]")
            legs.append("[v_black]blackdetect=d=0.5:pix_th=0.10[v_out_black]")
            legs.append("[v_freeze]freezedetect=n=0.001:d=2[v_out_freeze]")
            outputs.extend(("[v_out_black]", "[v_out_freeze]"))
        if audio is not None:
            legs.append("[0:a]asplit=2[a_silence][a_loud]")
            legs.append("[a_silence]silencedetect=n=-45dB:d=1.5[a_out_silence]")
            legs.append("[a_loud]loudnorm=print_format=json[a_out_loud]")
            outputs.extend(("[a_out_silence]", "[a_out_loud]"))
        content_result: ProcessResult | None = None
        if outputs:
            command = [ffmpeg, "-hide_banner", "-i", str(media_path), "-filter_complex", ";".join(legs)]
            for label in outputs:
                command += ["-map", label]
            command += ["-f", "null", "-"]
            content_result = run_safe(command, timeout_s=timeout_s, check=False)
        content_stderr = content_result.stderr if content_result is not None else ""
        check("blackdetect", not _has_duration(content_stderr, "black_duration", 0.5), "no black run >=0.5s")
        check("freezedetect", not _has_duration(content_stderr, "freeze_duration", 2.0), "no freeze >=2s")
        check("silencedetect", not _has_duration(content_stderr, "silence_duration", 1.5), "no silence >=1.5s")
        lufs, true_peak = _parse_loudnorm(content_stderr)
        if lufs is not None:
            check("loudness", -15.5 <= lufs <= -12.5, f"integrated loudness {lufs:.2f} LUFS")
        if true_peak is not None:
            check("true_peak", true_peak <= -1.0, f"true peak {true_peak:.2f} dBTP")
        if subtitle_path and subtitle_path.exists():
            from .ass import validate_ass_bounds

            subtitle_errors = validate_ass_bounds(subtitle_path.read_text(encoding="utf-8"))
            check("subtitle_bounds", not subtitle_errors, "; ".join(subtitle_errors) or "ASS positions are safe")
        if content_result is not None and content_result.returncode != 0:
            errors.append(f"content check command failed: {content_result.stderr.strip()[-500:]}")
        return ValidationResult(
            passed=not errors,
            checks=checks,
            errors=errors,
            measured_duration_s=duration,
            measured_lufs=lufs,
            measured_true_peak_db=true_peak,
        )


def _parse_rate(value: Any) -> float:
    if not value or value == "0/0":
        return 0.0
    try:
        numerator, denominator = str(value).split("/", 1)
        return float(numerator) / float(denominator)
    except (ValueError, ZeroDivisionError):
        return 0.0


def _as_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _has_duration(stderr: str, field: str, threshold: float) -> bool:
    return any(float(match) >= threshold for match in re.findall(rf"{field}:\s*(-?[0-9.]+)", stderr))


def _parse_loudnorm(stderr: str) -> tuple[float | None, float | None]:
    matches = re.findall(r"\{\s*\"input_i\".*?\}", stderr, flags=re.DOTALL)
    if not matches:
        return None, None
    try:
        data = json.loads(matches[-1])
    except json.JSONDecodeError:
        return None, None
    return _as_float(data.get("input_i")), _as_float(data.get("input_tp"))
