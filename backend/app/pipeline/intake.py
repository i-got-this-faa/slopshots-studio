"""Script normalization and duration lint from docs/01-script-intake.md."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from ..models import LintIssue, NormalizationResult


_CURRENCY_NAMES = {"$": "dollar", "€": "euro", "£": "pound"}
_URL_RE = re.compile(r"(?:https?://|www\.)[^\s]+", re.IGNORECASE)
_HANDLE_RE = re.compile(r"(?<!\w)[@#][A-Za-z0-9_]+")
_NUMBER_RE = re.compile(r"(?<![\w-])\d+(?:,\d{3})*(?:\.\d+)?(?![\w-])")
_CURRENCY_RE = re.compile(
    r"(?P<symbol>[$€£])(?P<number>\d+(?:,\d{3})*(?:\.\d+)?)"
)
_WORD_RE = re.compile(r"[A-Za-z]+(?:[-'][A-Za-z]+)*")


def _under_hundred(number: int) -> str:
    ones = (
        "zero",
        "one",
        "two",
        "three",
        "four",
        "five",
        "six",
        "seven",
        "eight",
        "nine",
        "ten",
        "eleven",
        "twelve",
        "thirteen",
        "fourteen",
        "fifteen",
        "sixteen",
        "seventeen",
        "eighteen",
        "nineteen",
    )
    tens = ("", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety")
    if number < 20:
        return ones[number]
    return tens[number // 10] + (f"-{ones[number % 10]}" if number % 10 else "")


def number_to_words(number: int) -> str:
    """Convert ordinary script-sized integers without a third-party package."""

    if number < 0:
        return f"minus {number_to_words(-number)}"
    if number < 100:
        return _under_hundred(number)
    if number < 1_000:
        remainder = number % 100
        suffix = f" {_under_hundred(remainder)}" if remainder else ""
        return f"{_under_hundred(number // 100)} hundred{suffix}"
    for divisor, name in ((1_000_000_000, "billion"), (1_000_000, "million"), (1_000, "thousand")):
        if number >= divisor:
            quotient, remainder = divmod(number, divisor)
            suffix = f" {number_to_words(remainder)}" if remainder else ""
            return f"{number_to_words(quotient)} {name}{suffix}"
    return "zero"


def _number_phrase(raw: str) -> str:
    clean = raw.replace(",", "")
    if "." not in clean:
        return number_to_words(int(clean))
    whole, fraction = clean.split(".", 1)
    digits = " ".join(number_to_words(int(digit)) for digit in fraction)
    return f"{number_to_words(int(whole))} point {digits}"


def _currency_phrase(match: re.Match[str]) -> str:
    symbol = match.group("symbol")
    raw_number = match.group("number")
    plural = raw_number.replace(",", "") not in {"1", "1.0"}
    noun = _CURRENCY_NAMES[symbol] + ("s" if plural else "")
    return f"{_number_phrase(raw_number)} {noun}"


def _load_lexicon(path: Path | None) -> dict[str, str]:
    """Read the intentionally tiny ``key: value`` lexicon without requiring PyYAML.

    The supported format is a flat YAML mapping, which is enough for recurring
    pronunciation fixes and keeps intake usable in a minimal installation.
    """

    if path is None or not path.exists():
        return {}
    entries: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        key = key.strip().strip("'\"")
        value = value.strip().strip("'\"")
        if key and value:
            entries[key] = value
    return entries


def _apply_lexicon(text: str, lexicon: dict[str, str]) -> str:
    for source, replacement in sorted(lexicon.items(), key=lambda item: -len(item[0])):
        text = re.sub(
            rf"(?<!\w){re.escape(source)}(?!\w)",
            replacement,
            text,
            flags=re.IGNORECASE,
        )
    return text


def normalize_script(text: str, lexicon_path: Path | None = None) -> str:
    """Apply the v1 normalization rules before TTS and alignment."""

    normalized = unicodedata.normalize("NFKC", text).replace("\r\n", "\n")
    normalized = _URL_RE.sub(" ", normalized)
    normalized = _HANDLE_RE.sub(" ", normalized)
    normalized = re.sub(r"\bMr\.(?=\s|$)", "mister", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\bDr\.(?=\s|$)", "doctor", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\bGTA\s+V\b", "GTA five", normalized, flags=re.IGNORECASE)
    normalized = normalized.replace("...", ". ").replace("--", ". ")
    normalized = _CURRENCY_RE.sub(_currency_phrase, normalized)
    normalized = _NUMBER_RE.sub(lambda match: _number_phrase(match.group(0)), normalized)
    normalized = _apply_lexicon(normalized, _load_lexicon(lexicon_path))

    # Remove emoji and other symbol characters while preserving ordinary
    # punctuation used to make sentence boundaries and pauses.
    normalized = "".join(
        char
        for char in normalized
        if unicodedata.category(char) not in {"So", "Sk", "Cs"}
    )
    normalized = re.sub(r"[^\w\s.,!?;:'\"()\-]", " ", normalized, flags=re.UNICODE)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def lint_script(normalized: str) -> tuple[int, float, list[LintIssue], bool]:
    words = _WORD_RE.findall(normalized)
    count = len(words)
    duration = count / 2.5 if count else 0.0
    issues: list[LintIssue] = []
    if count < 130 or count > 260:
        issues.append(
            LintIssue(
                level="error",
                code="word_count_hard_limit",
                message=f"script has {count} words; hard limit is 130–260",
            )
        )
    elif count < 150 or count > 230:
        issues.append(
            LintIssue(
                level="warning",
                code="word_count_soft_limit",
                message=f"script has {count} words; target range is 150–230",
            )
        )
    if duration > 90:
        issues.append(
            LintIssue(
                level="error",
                code="estimated_duration_too_long",
                message=f"estimated narration is {duration:.1f}s; Shorts target is at most 90s",
            )
        )
    return count, duration, issues, any(issue.level == "error" for issue in issues)


def normalize_and_lint(text: str, lexicon_path: Path | None = None) -> NormalizationResult:
    normalized = normalize_script(text, lexicon_path)
    count, duration, issues, hard_fail = lint_script(normalized)
    return NormalizationResult(
        original=text,
        normalized=normalized,
        word_count=count,
        estimated_duration_s=duration,
        hard_fail=hard_fail,
        issues=issues,
    )
