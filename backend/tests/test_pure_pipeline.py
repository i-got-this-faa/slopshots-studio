from app.models import (
    Animation,
    Canvas,
    GameplayTrack,
    KaraokeMode,
    MusicTrack,
    OverlayTrack,
    PlacementProposal,
    SubtitlesTrack,
    Timeline,
    TimelineTracks,
    VoiceTrack,
    WordTiming,
    Zone,
)
from app.pipeline.ass import build_cards, generate_ass, validate_ass_bounds
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
    assert "acompressor=threshold=0.1:ratio=4" in graph


def test_music_filtergraph_splits_voice_for_mix_and_sidechain():
    timeline = Timeline(
        canvas=Canvas(),
        tracks=TimelineTracks(
            gameplay=GameplayTrack(clip="gameplay.mp4"),
            voice=VoiceTrack(file="voice.wav"),
            subtitles=SubtitlesTrack(ass="subtitles.ass"),
            music=MusicTrack(file="music.mp3"),
            overlays=[
                OverlayTrack(
                    asset="visual.png",
                    t=1,
                    duration_s=2,
                    zone=Zone.MIDDLE,
                    animation=Animation.POP_IN,
                    scale=1,
                )
            ],
        ),
        duration_s=10.3,
    )

    graph = generate_filtergraph(timeline, duration_s=10.3)

    assert "[voice]asplit=2[voice_mix][voice_key]" in graph
    assert "[music][voice_key]sidechaincompress=" in graph
    assert "[voice_mix][ducked]amix=" in graph
    assert "scale=760:390:force_original_aspect_ratio=decrease" in graph
    assert "pad=760:390:(ow-iw)/2:(oh-ih)/2:color=black@0" in graph


def test_ass_cards_show_four_words_on_two_lines_without_overlap():
    words = [
        WordTiming(w=word, start=index * 0.25, end=index * 0.25 + 0.2, conf=1)
        for index, word in enumerate(
            ["the", "beat", "lifts", "us", "then", "the", "beat", "drops."]
        )
    ]

    cards = build_cards(words)
    assert [len(card.words) for card in cards] == [4, 4]
    assert all(card.end <= following.start for card, following in zip(cards, cards[1:]))

    ass = generate_ass(words)
    card_lines = [line for line in ass.splitlines() if line.startswith("Dialogue: 1")]
    backdrop_lines = [line for line in ass.splitlines() if line.startswith("Dialogue: 0")]
    highlight_lines = [line for line in ass.splitlines() if line.startswith("Dialogue: 2")]
    assert len(highlight_lines) == len(words)
    assert all(line.count(r"\kf") == 1 for line in highlight_lines)
    assert all(r"\kf" not in line for line in card_lines)
    assert len(card_lines) == 2
    assert len(backdrop_lines) == 2
    assert all(line.count(r"\N") == 1 for line in card_lines)
    assert "Style: Backdrop" in ass
    assert "Montserrat ExtraBold,92" in ass


def test_ass_splits_cards_before_a_line_can_clip():
    words = [
        WordTiming(w=word, start=index * 0.25, end=index * 0.25 + 0.2, conf=1)
        for index, word in enumerate(["the", "most", "dangerous", "feature"])
    ]

    cards = build_cards(words)

    assert [[word.word for word in card.words] for card in cards] == [
        ["the", "most", "dangerous"],
        ["feature"],
    ]

