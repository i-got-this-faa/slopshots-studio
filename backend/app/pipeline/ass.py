"""ASS karaoke card generation and static bounds validation."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

from ..models import KaraokeMode, WordTiming


@dataclass(frozen=True)
class KaraokeCard:
    words: list[WordTiming]
    start: float
    end: float


def _sentence_break(word: str) -> bool:
    return bool(re.search(r"[.!?;:]$", word))


MAX_LINE_CHARS = 14


def _line_length(lengths: list[int]) -> int:
    return sum(lengths) + max(0, len(lengths) - 1)


def _fits_two_lines(words: list[WordTiming], *, max_line_chars: int) -> bool:
    lengths = [len(word.word) for word in words]
    if _line_length(lengths) <= max_line_chars:
        return True
    return any(
        _line_length(lengths[:index]) <= max_line_chars
        and _line_length(lengths[index:]) <= max_line_chars
        for index in range(1, len(lengths))
    )


def build_cards(
    words: list[WordTiming],
    *,
    max_words: int = 4,
    max_chars: int = 29,
    max_line_chars: int = MAX_LINE_CHARS,
) -> list[KaraokeCard]:
    cards: list[KaraokeCard] = []
    current: list[WordTiming] = []
    current_chars = 0
    for word in words:
        visible_length = len(word.word)
        proposed_chars = visible_length if not current else current_chars + 1 + visible_length
        gap = word.start - current[-1].end if current else 0.0
        proposed_words = [*current, word]
        should_break = bool(current) and (
            len(current) >= max_words
            or proposed_chars > max_chars
            or not _fits_two_lines(proposed_words, max_line_chars=max_line_chars)
            or gap > 0.3
        )
        if should_break:
            cards.append(
                KaraokeCard(
                    words=current,
                    start=max(0.0, current[0].start - 0.08),
                    end=current[-1].end + 0.12,
                )
            )
            current = []
            current_chars = 0
        current.append(word)
        current_chars = visible_length if not current_chars else current_chars + 1 + visible_length
        if _sentence_break(word.word):
            cards.append(
                KaraokeCard(
                    words=current,
                    start=max(0.0, current[0].start - 0.08),
                    end=current[-1].end + 0.12,
                )
            )
            current = []
            current_chars = 0
    if current:
        cards.append(
            KaraokeCard(
                words=current,
                start=max(0.0, current[0].start - 0.08),
                end=current[-1].end + 0.12,
            )
        )

    # Lead-in and linger padding must never put two cards at the same fixed
    # ASS position simultaneously. Switch at the midpoint between their
    # adjacent word timings instead of letting libass draw both strings.
    for index in range(len(cards) - 1):
        card = cards[index]
        following = cards[index + 1]
        if card.end <= following.start:
            continue
        boundary = (card.words[-1].end + following.words[0].start) / 2
        boundary = max(card.start + 0.01, min(following.end - 0.01, boundary))
        cards[index] = replace(card, end=boundary)
        cards[index + 1] = replace(following, start=boundary)

    return cards


def _ass_time(seconds: float) -> str:
    centiseconds = max(0, round(seconds * 100))
    hours, remainder = divmod(centiseconds, 360000)
    minutes, remainder = divmod(remainder, 6000)
    secs, cs = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{cs:02d}"


def _escape_ass(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


def _line_break_index(card: KaraokeCard) -> int | None:
    if len(card.words) <= 1:
        return None
    lengths = [len(word.word) for word in card.words]
    if _line_length(lengths) <= MAX_LINE_CHARS:
        return None
    return min(
        range(1, len(lengths)),
        key=lambda index: (
            max(_line_length(lengths[:index]), _line_length(lengths[index:])),
            abs(_line_length(lengths[:index]) - _line_length(lengths[index:])),
        ),
    )


def _card_text(
    card: KaraokeCard,
    mode: KaraokeMode,
    *,
    active_index: int | None = None,
) -> str:
    pieces: list[str] = []
    for index, word in enumerate(card.words):
        escaped = _escape_ass(word.word.upper())
        if index != active_index:
            color = r"{\1c&H00FFFFFF&\2c&H00FFFFFF&}" if active_index is not None else ""
            pieces.append(f"{color}{escaped}")
            continue
        if mode == KaraokeMode.KF:
            duration_cs = max(1, round((word.end - word.start) * 100))
            pieces.append(
                rf"{{\1c&H00FFFFFF&\2c&H0000D7FF&\kf{duration_cs}}}{escaped}"
            )
        else:
            pieces.append(rf"{{\1c&H0000D7FF&\2c&H0000D7FF&}}{escaped}")
    line_break = _line_break_index(card)
    if line_break is None:
        return " ".join(pieces)
    return " ".join(pieces[:line_break]) + r"\N" + " ".join(pieces[line_break:])


def _card_line_lengths(card: KaraokeCard) -> list[int]:
    lengths = [len(word.word) for word in card.words]
    line_break = _line_break_index(card)
    if line_break is None:
        return [_line_length(lengths)]
    return [_line_length(lengths[:line_break]), _line_length(lengths[line_break:])]


def _backdrop_text(card: KaraokeCard, subtitle_y: int) -> str:
    line_lengths = _card_line_lengths(card)
    box_width = min(940, max(320, max(line_lengths) * 58 + 64))
    box_height = 126 if len(line_lengths) == 1 else 236
    left = (1080 - box_width) // 2
    top = subtitle_y - box_height // 2
    return (
        rf"{{\an7\pos({left},{top})\p1\bord0\shad0}}"
        f"m 0 0 l {box_width} 0 {box_width} {box_height} 0 {box_height}"
        r"{\p0}"
    )


def generate_ass(
    words: list[WordTiming],
    *,
    mode: KaraokeMode = KaraokeMode.KF,
    subtitle_y: int = 1152,
) -> str:
    if not 0 <= subtitle_y <= 1620:
        raise ValueError("subtitle y must stay above the platform-safe footer")
    cards = build_cards(words)
    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "PlayResX: 1080",
        "PlayResY: 1920",
        "WrapStyle: 2",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        "Style: Backdrop,Arial,10,&H50000000,&H50000000,&H50000000,&H50000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1",
        "Style: Card,Montserrat ExtraBold,92,&H00FFFFFF,&H00D7FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,7,2,5,30,30,768,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for card in cards:
        start = _ass_time(card.start)
        end = _ass_time(card.end)
        lines.append(f"Dialogue: 0,{start},{end},Backdrop,,0,0,0,,{_backdrop_text(card, subtitle_y)}")
        base_text = rf"{{\an5\pos(540,{subtitle_y})}}{_card_text(card, mode)}"
        lines.append(f"Dialogue: 1,{start},{end},Card,,0,0,0,,{base_text}")
        for index, word in enumerate(card.words):
            highlight_start = max(card.start, word.start)
            highlight_end = min(card.end, word.end)
            if index + 1 < len(card.words):
                highlight_end = min(highlight_end, card.words[index + 1].start)
            if highlight_end <= highlight_start:
                continue
            highlight_text = rf"{{\an5\pos(540,{subtitle_y})}}{_card_text(card, mode, active_index=index)}"
            lines.append(
                f"Dialogue: 2,{_ass_time(highlight_start)},{_ass_time(highlight_end)},"
                f"Card,,0,0,0,,{highlight_text}"
            )
    return "\n".join(lines) + "\n"


def validate_ass_bounds(ass_text: str, *, width: int = 1080, height: int = 1920) -> list[str]:
    errors: list[str] = []
    position_re = re.compile(r"\\pos\(\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\)")
    for line_number, line in enumerate(ass_text.splitlines(), start=1):
        if not line.startswith("Dialogue:"):
            continue
        match = position_re.search(line)
        if not match:
            continue
        x, y = float(match.group(1)), float(match.group(2))
        if not 0 <= x <= width:
            errors.append(f"Dialogue line {line_number} x={x:g} is outside PlayResX")
        if not 0 <= y <= height - 300:
            errors.append(f"Dialogue line {line_number} y={y:g} enters the safe footer")
    return errors

