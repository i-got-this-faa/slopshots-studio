# 07 — Timeline / EDL

**Status: Decided (JSON source of truth, fixed effects pack), Selected pending re-confirm (zones)**

`timeline.json` is the single source of truth between decision-making and
rendering. The FFmpeg generator ([08](08-render-ffmpeg.md)) consumes it and
nothing else. Human approval edits this file (via agent chat), not the
render code.

## Schema

```json
{
  "version": 1,
  "canvas": {"w": 1080, "h": 1920, "fps": 30},
  "tracks": {
    "gameplay": {
      "clip": "library/mc-parkour-017.mp4",
      "start_offset_s": 43.2,
      "crop": "center-9x16"
    },
    "voice": {"file": "voice.wav", "gain_db": 0},
    "subtitles": {"ass": "subtitles.ass"},
    "overlays": [
      {
        "asset": "meme/surprised-cat.png",
        "t": 12.48, "duration_s": 2.5,
        "zone": "top-left",
        "animation": "pop-in",
        "scale": 0.35
      }
    ],
    "effects": [
      {"type": "zoom-punch", "t": 12.48, "amount": 1.08, "in_s": 0.12, "out_s": 0.25},
      {"type": "shake", "t": 31.0, "amp_px": 6, "duration_s": 0.4}
    ],
    "music": {"file": "music/phonk-03.mp3", "gain_db": -22, "duck": true}
  }
}
```

## Layout zones (pending re-confirm)

```
┌──────────────────┐
│ top-left  top-right│   ← overlay zones (y ≈ 15–40 %)
│      middle        │   ← sparse use; big reaction moments
│    [subtitles]     │   ← ~60 % height, reserved, never overlays
│   platform-safe    │   ← bottom 300 px: nothing, ever
└──────────────────┘
```

One active overlay per zone at a time ([05](05-overlay-placement.md)
collision rule). Zones map to absolute rects in the generator; changing zone
geometry must not touch placements.

## Effects pack (fixed vocabulary, bounded params)

| Effect | Params | Filtergraph sketch |
|--------|--------|--------------------|
| `zoom-punch` | amount ≤ 1.15, in/out ≤ 0.4 s | `zoompan` or `scale`+`crop` envelope |
| `shake` | amp ≤ 10 px, ≤ 0.5 s | `crop` with sinusoidal x/y offsets |
| `flash` | — | `curves` spike or white `drawbox` frame |
| `fade` | in/out s | `fade=t=in:st=…` |
| overlay `pop-in` | — | `scale` envelope + `overlay=eof_action=…` |
| overlay `bounce` | — | pop-in + overshoot keyframes |
| overlay `slide-up` | — | animated `overlay=y=…` |

Anything outside this table is a v2 conversation — no general keyframe
system.

## Invariants (validated pre-render)

- `overlays[*].t + duration_s ≤ voice duration`.
- No overlay in the subtitle band or bottom 300 px.
- One active overlay per zone (post-collision-resolution).
- Every referenced file exists.
- `version` present — schema evolves with migrations, never silent drift.
