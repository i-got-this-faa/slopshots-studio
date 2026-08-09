# 11 — Validation Gate

**Status: Decided (full automated gate + eyeball)**

Runs on `final.mp4` before anything reaches a human. Fail = auto-reject with
a reason; the pipeline re-renders with adjusted params where the failure is
parameteric (max 3 attempts, video-use style), else halts for the human.

## Format checks (ffprobe)

| Check | Expect |
|-------|--------|
| Resolution | 1080×1920 exactly |
| Duration | = voice duration + 0.3 s, and ≤ 90 s |
| Video codec | h264 (High), yuv420p, 30 fps |
| Audio codec | aac, 48 kHz, present and non-silent |
| Container | mp4, faststart |

## Content checks (ffmpeg filters)

```
ffmpeg -i final.mp4 -vf blackdetect=d=0.5:pix_th=0.10 -an -f null -
ffmpeg -i final.mp4 -vf freezedetect=n=0.001:d=2 -an -f null -
ffmpeg -i final.mp4 -af silencedetect=n=-45dB:d=1.5 -vn -f null -
ffmpeg -i final.mp4 -af loudnorm=print_format=json -vn -f null -
```

| Check | Reject when |
|-------|-------------|
| `blackdetect` | any black run ≥ 0.5 s |
| `freezedetect` | frozen video ≥ 2 s (overlay window bugs show up here) |
| `silencedetect` | silence ≥ 1.5 s inside narration span |
| `loudnorm` | integrated outside −14 ± 1.5 LUFS, or true peak > −1 dBTP |
| Subtitle bounds | static `.ass` check ([04](04-subtitles-karaoke.md)) — pre-render, free |

## Human eyeball

Upload is manual ([13](13-upload.md)), so the eyeball is free and mandatory:
watch once at 1×. What the human is judging: karaoke timing feel, meme
appropriateness, music balance. Everything mechanical should already be
green — if the human is catching mechanical errors, the gate is missing a
check; add it.

## Self-eval upgrade path (not v1)

The declined option from the grilling: re-transcribe `final.mp4` audio with
WhisperX and diff against `words.json` — catches render-stage audio bugs the
input-side gate can't. Revisit if a bad render ever ships.
