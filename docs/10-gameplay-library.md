# 10 — Gameplay Library

**Status: Decided (self-recorded, crop-aware capture)**

## Why self-recorded

Cleanest possible rights position — the genre's downloaded-footage habit is
a copyright-strike farm and the first thing platform reuse policies
pattern-match. Own footage + substantial editing (narration, overlays,
effects) is the strongest originality posture available.

## Capture rules (crop-aware recording)

A full-height 9:16 crop of 16:9 footage keeps ~32 % of the frame area
(~68 % lost). Fix it at capture time, not in the pipeline:

- Record with action **centered in the middle vertical third** — for
  Minecraft parkour this is natural (crosshair-centered gameplay).
- Or record windowed at 1080×1920 native (game in a vertical viewport,
  orOBS canvas crop at capture) — zero downstream loss.
- 60 fps capture preferred; deliver 30 fps render — smoother slow-punch
  effects if headroom is ever needed.

## Library metadata

```yaml
# library/mc-parkour-017.yml
file: mc-parkour-017.mp4
game: minecraft
style: parkour          # parkour | build | pvp | drive | …
duration_s: 312
intensity: medium       # visual busyness; pair frantic narration with calm footage
recorded: 2026-08-01
```

## Selection & variety

- Clip `duration_s` must exceed the 90 s max narration → no loop logic in
  v1. (Looping is a visible jump-cut farm; reject by construction.)
- Start offset randomized per video **for variety across the channel** —
  same clip never opens two videos the same way. (This is an originality/
  freshness measure, not a detection-evasion trick.)
- Track which clips have been used; rotate the library so no clip repeats
  within the last N videos.

## Failure modes

| Failure | Signal | Fix |
|---------|--------|-----|
| Action drifts off-center mid-clip | Eyeball at approval | Mark clip segment unusable in metadata |
| Library exhaustion (repeats) | Usage log | Record in batches; 20 × 3-min clips ≈ 40+ videos |
| Mixed framerates | ffprobe at ingest | Normalize to 60 fps at ingest, once |
