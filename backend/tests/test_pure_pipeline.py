from app.models import (
    Animation,
    Canvas,
    GameplayTrack,
    KaraokeMode,
    PlacementProposal,
    SubtitlesTrack,
    Timeline,
    TimelineTracks,
    VoiceTrack,
    WordTiming,
    Zone,
)
from app.pipeline.ass import generate_ass, validate_ass_bounds
from app.pipeline.ffmpeg import generate_filtergraph
from app.pipeline.intake import normalize_script, normalize_and_lint
from app.pipeline.placement import resolve_placements


def test_script_normalization_rules_are_deterministic():
    normalized = normalize_script("Mr. paid $5 to play GTA V... visit https://example.test @handle #tag")
    assert "mister" in normalized
    assert "five dollars" in normalized
    assert "GTA five" in normalized
    assert "https" not in normalized
    assert "@" not in normalized


def test_duration_lint_has_hard_and_soft_ranges():
    result = normalize_and_lint("one two three")
    assert result.hard_fail is True
    assert any(issue.code == "word_count_hard_limit" for issue in result.issues)


def test_anchor_resolution_queues_same_zone_and_warns_on_duplicate():
    words = [
        WordTiming(w="forty-two", start=1.0, end=1.4, conf=0.99),
        WordTiming(w="then", start=1.5, end=1.8, conf=0.99),
        WordTiming(w="forty-two", start=3.0, end=3.4, conf=0.99),
    ]
    proposals = [
        PlacementProposal(
            asset_id="meme/one",
            anchor_text="forty-two",
            zone=Zone.TOP_LEFT,
            duration_s=2.0,
            animation=Animation.POP_IN,
        ),
        PlacementProposal(
            asset_id="meme/two",
            anchor_text="then",
            zone=Zone.TOP_LEFT,
            duration_s=1.0,
            animation=Animation.SLIDE_UP,
        ),
    ]
    result = resolve_placements(proposals, words, voice_duration_s=10)
    assert len(result.placements) == 2
    assert result.placements[1].t_start >= result.placements[0].t_start + 2.0
    assert any("first occurrence" in warning for warning in result.warnings)


def test_ass_and_filtergraph_use_safe_canvas_contract():
    words = [
        WordTiming(w="So", start=0.1, end=0.3, conf=1),
        WordTiming(w="this", start=0.3, end=0.5, conf=1),
        WordTiming(w="works.", start=0.5, end=0.9, conf=1),
    ]
    ass = generate_ass(words, mode=KaraokeMode.KF)
    assert "PlayResX: 1080" in ass
    assert "\\kf" in ass
    assert validate_ass_bounds(ass) == []
    timeline = Timeline(
        canvas=Canvas(),
        tracks=TimelineTracks(
            gameplay=GameplayTrack(clip="gameplay.mp4"),
            voice=VoiceTrack(file="voice.wav"),
            subtitles=SubtitlesTrack(ass="subtitles.ass"),
        ),
        duration_s=10.3,
    )
    graph = generate_filtergraph(timeline, duration_s=10.3)
    assert "scale=1080:1920" in graph
    assert "subtitles='subtitles.ass'" in graph
    assert "[aout]" in graph

