"""Word-anchor resolution and deterministic overlay collision handling."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..errors import InvalidRequestError
from ..models import (
    PlacementProposal,
    PlacementResolutionResult,
    ResolvedPlacement,
    WordTiming,
    Zone,
)


ZONE_RECTS: dict[Zone, tuple[int, int, int, int]] = {
    # x, y, width, height. All rectangles end above the subtitle band and the
    # 300px platform-safe footer on a 1080x1920 canvas.
    Zone.TOP_LEFT: (40, 180, 460, 420),
    Zone.TOP_RIGHT: (580, 180, 460, 420),
    Zone.MIDDLE: (160, 590, 760, 390),
}
SUBTITLE_BAND = (0, 1040, 1080, 580)
PLATFORM_SAFE_FOOTER_Y = 1620


def _anchor_token(value: str) -> str:
    value = value.casefold().replace("’", "'")
    return re.sub(r"[^\w'-]", "", value, flags=re.UNICODE)


def _find_anchor(words: list[WordTiming], anchor_text: str) -> list[int]:
    expected = [_anchor_token(token) for token in anchor_text.split()]
    expected = [token for token in expected if token]
    if not expected:
        return []
    actual = [_anchor_token(word.word) for word in words]
    matches: list[int] = []
    for start in range(0, len(actual) - len(expected) + 1):
        if actual[start : start + len(expected)] == expected:
            matches.append(start)
    return matches


@dataclass(frozen=True)
class _Candidate:
    original_index: int
    proposal: PlacementProposal
    anchor_index: int
    anchor_time: float


def resolve_placements(
    proposals: list[PlacementProposal],
    words: list[WordTiming],
    *,
    voice_duration_s: float,
) -> PlacementResolutionResult:
    """Resolve phrase anchors and queue same-zone collisions reproducibly.

    Candidates are ordered by resolved anchor time and then original proposal
    order. A queued placement never moves earlier than its anchor midpoint;
    when it would run past the narration it is dropped and surfaced in the
    result instead of being silently discarded.
    """

    if voice_duration_s <= 0:
        raise InvalidRequestError("voice duration must be positive before resolving placements")
    candidates: list[_Candidate] = []
    warnings: list[str] = []
    dropped: list[PlacementProposal] = []
    for original_index, proposal in enumerate(proposals):
        matches = _find_anchor(words, proposal.anchor_text)
        if not matches:
            raise InvalidRequestError(
                f"anchor '{proposal.anchor_text}' was not found in aligned words"
            )
        anchor_index = matches[0]
        first = words[anchor_index]
        last = words[anchor_index + len(proposal.anchor_text.split()) - 1]
        anchor_time = (first.start + last.end) / 2
        if len(matches) > 1:
            warnings.append(
                f"anchor '{proposal.anchor_text}' occurs {len(matches)} times; first occurrence selected"
            )
        candidates.append(
            _Candidate(
                original_index=original_index,
                proposal=proposal,
                anchor_index=anchor_index,
                anchor_time=anchor_time,
            )
        )

    candidates.sort(key=lambda candidate: (candidate.anchor_time, candidate.original_index))
    next_free: dict[Zone, float] = {zone: 0.0 for zone in Zone}
    resolved: list[ResolvedPlacement] = []
    for candidate in candidates:
        proposal = candidate.proposal
        start = max(candidate.anchor_time, next_free[proposal.zone])
        end = start + proposal.duration_s
        placement_warnings: list[str] = []
        if start > candidate.anchor_time + 1e-9:
            warning = (
                f"placement '{proposal.asset_id}' queued in {proposal.zone.value} "
                f"from {candidate.anchor_time:.3f}s to {start:.3f}s"
            )
            warnings.append(warning)
            placement_warnings.append(warning)
        if end > voice_duration_s + 1e-6:
            warning = (
                f"placement '{proposal.asset_id}' dropped: {proposal.zone.value} "
                f"has no free slot for {proposal.duration_s:.3f}s before narration ends"
            )
            warnings.append(warning)
            dropped.append(proposal)
            continue
        resolved.append(
            ResolvedPlacement(
                asset_id=proposal.asset_id,
                anchor_text=proposal.anchor_text,
                anchor_index=candidate.anchor_index,
                t_start=round(start, 6),
                duration_s=proposal.duration_s,
                zone=proposal.zone,
                animation=proposal.animation,
                reason=proposal.reason,
                scale=proposal.scale,
                warnings=placement_warnings,
            )
        )
        next_free[proposal.zone] = end

    resolved.sort(key=lambda placement: (placement.t_start, placement.zone.value, placement.asset_id))
    return PlacementResolutionResult(placements=resolved, warnings=warnings, dropped=dropped)


def validate_resolved_placements(
    placements: list[ResolvedPlacement], *, voice_duration_s: float
) -> list[str]:
    """Return invariant violations for a placement list."""

    errors: list[str] = []
    by_zone: dict[Zone, list[ResolvedPlacement]] = {zone: [] for zone in Zone}
    for placement in placements:
        if placement.t_start + placement.duration_s > voice_duration_s + 1e-6:
            errors.append(f"{placement.asset_id} exceeds narration duration")
        x, y, width, height = ZONE_RECTS[placement.zone]
        if y + height > PLATFORM_SAFE_FOOTER_Y:
            errors.append(f"zone {placement.zone.value} enters platform-safe footer")
        sx, sy, sw, sh = SUBTITLE_BAND
        if x < sx + sw and x + width > sx and y < sy + sh and y + height > sy:
            errors.append(f"zone {placement.zone.value} enters subtitle band")
        by_zone[placement.zone].append(placement)
    for zone, entries in by_zone.items():
        entries.sort(key=lambda placement: placement.t_start)
        for previous, current in zip(entries, entries[1:]):
            if current.t_start < previous.t_start + previous.duration_s - 1e-6:
                errors.append(f"overlapping placements in zone {zone.value}")
    return errors

