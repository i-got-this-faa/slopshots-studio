"""Timeline/EDL assembly and invariant checks."""

from __future__ import annotations

import json
from pathlib import Path

from ..errors import InvalidRequestError
from ..models import (
    GameplayTrack,
    MusicTrack,
    OverlayTrack,
    PlacementResolutionResult,
    SubtitlesTrack,
    Timeline,
    TimelineTracks,
    VoiceTrack,
)
from .placement import validate_resolved_placements


def read_placement_result(path: Path) -> PlacementResolutionResult:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            raw = {"placements": raw}
        return PlacementResolutionResult.model_validate(raw)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise InvalidRequestError(f"invalid placements artifact: {path.name}: {exc}") from exc


def build_timeline(
    *,
    job_dir: Path,
    gameplay_file: str | None,
    music_file: str | None,
    voice_duration_s: float,
    placements: PlacementResolutionResult,
) -> Timeline:
    if not gameplay_file:
        raise InvalidRequestError(
            "timeline stage requires gameplay_file; provide a self-recorded clip in the job settings"
        )
    if voice_duration_s <= 0:
        raise InvalidRequestError("timeline stage requires a positive voice duration")
    placement_errors = validate_resolved_placements(
        placements.placements,
        voice_duration_s=voice_duration_s,
    )
    if placement_errors:
        raise InvalidRequestError("invalid placements: " + "; ".join(placement_errors))

    timeline_overlays = [
        OverlayTrack(
            asset=placement.asset_id,
            t=placement.t_start,
            duration_s=placement.duration_s,
            zone=placement.zone,
            animation=placement.animation,
            scale=placement.scale,
        )
        for placement in placements.placements
    ]
    music = MusicTrack(file=music_file) if music_file else None
    return Timeline(
        version=1,
        duration_s=voice_duration_s + 0.3,
        tracks=TimelineTracks(
            gameplay=GameplayTrack(clip=gameplay_file),
            voice=VoiceTrack(file=str(job_dir / "voice.wav")),
            subtitles=SubtitlesTrack(ass=str(job_dir / "subtitles.ass")),
            overlays=timeline_overlays,
            effects=[],
            music=music,
        ),
    )


def validate_timeline_files(timeline: Timeline) -> list[str]:
    errors: list[str] = []
    for label, path in (
        ("gameplay", timeline.tracks.gameplay.clip),
        ("voice", timeline.tracks.voice.file),
        ("subtitles", timeline.tracks.subtitles.ass),
    ):
        if not Path(path).exists():
            errors.append(f"{label} file does not exist: {path}")
    if timeline.tracks.music and not Path(timeline.tracks.music.file).exists():
        errors.append(f"music file does not exist: {timeline.tracks.music.file}")
    for overlay in timeline.tracks.overlays:
        if not Path(overlay.asset).exists():
            errors.append(f"overlay asset does not exist: {overlay.asset}")
    return errors

