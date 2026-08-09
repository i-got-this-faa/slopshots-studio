"""ASS karaoke card generation and static bounds validation."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..models import KaraokeMode, WordTiming


@dataclass(frozen=True)
class KaraokeCard:
    words: list[WordTiming]
    start: float
    end: float


def _sentence_break(word: str) -> bool:
    return bool(re.search(r"[.!?;:]$", word))


def build_cards(words: list[WordTiming], *, max_words: int = 3, max_chars: int = 16) -> list[KaraokeCard]:
    cards: list[KaraokeCard] = []
    current: list[WordTiming] = []
    current_chars = 0
    for word in words:
        visible_length = len(word.word)
        proposed_chars = visible_length if not current else current_chars + 1 + visible_length
        gap = word.start - current[-1].end if current else 0.0
        should_break = bool(current) and (
            len(current) >= max_words
            or proposed_chars > max_chars
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
    return cards


def _ass_time(seconds: float) -> str:
    centiseconds = max(0, round(seconds * 100))
    hours, remainder = divmod(centiseconds, 360000)
    minutes, remainder = divmod(remainder, 6000)
    secs, cs = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{cs:02d}"


def _escape_ass(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


def _card_text(card: KaraokeCard, mode: KaraokeMode) -> str:
    tag = "kf" if mode == KaraokeMode.KF else "k"
    pieces: list[str] = []
    for word in card.words:
        duration_cs = max(1, round((word.end - word.start) * 100))
        pieces.append(f"{{\\{tag}{duration_cs}}}{_escape_ass(word.word.upper())}")
    return " ".join(pieces)


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
        "Style: Card,Montserrat ExtraBold,72,&H00FFFFFF,&H00D7FF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,7,3,5,30,30,768,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for card in cards:
        text = _card_text(card, mode)
        text = rf"{{\an5\pos(540,{subtitle_y})}}{text}"
        lines.append(
            f"Dialogue: 0,{_ass_time(card.start)},{_ass_time(card.end)},Card,,0,0,0,,{text}"
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

