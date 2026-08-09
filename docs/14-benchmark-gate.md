# 14 — Benchmark Gate

**Status: Selected pending re-confirm (end-to-end 10 s prototype, < 10 min/video target)**

## Purpose

Every architectural commitment assumes this machine can run the pipeline at
acceptable speed. That is currently **unmeasured**. This gate exists to kill
or confirm the architecture before any real build-out.

## The prototype

One 10-second slice through the full chain, on the target box:

1. **Script** — a real 40-word excerpt, normalized per [01](01-script-intake.md).
2. **TTS** — Kokoro, chosen voice, `voice.wav` (10 s).
3. **Align** — WhisperX → `words.json`; record flagged-word ratio.
4. **Placements** — 3 hand-written placements (skip the LLM; it's network,
   not compute).
5. **Timeline** — assemble `timeline.json` by hand per [07](07-timeline-edl.md).
6. **Render** — generated filtergraph: gameplay crop + karaoke ASS + 1
   overlay pop-in + 1 zoom-punch + ducked music. Full encode settings from
   [08](08-render-ffmpeg.md).
7. **Validate** — the [11](11-validation.md) gate, timed too.

## Measurements

| Stage | Wall time | Notes |
|-------|-----------|-------|
| TTS (Kokoro, CPU) | ___ | scales ~linearly with script length |
| Alignment (WhisperX int8) | ___ | model load time counted separately |
| ASS generation | ___ | expected negligible |
| Render (libx264 `-preset slow`) | ___ | the number most likely to fail |
| Validation | ___ | |
| **Total** | ___ | |

Hardware recorded verbatim: CPU, RAM, OS, ffmpeg version, model sizes.

## Acceptance (pending re-confirm)

- **Total < 10 min for a 60–90 s video** (extrapolated from the 10 s slice,
  render scales ~linearly, TTS/align sublinearly with model load amortized).
- Karaoke timing judged acceptable by eye on the slice (`\kf` vs `\k`
  decision gets its first real data point here).
- Flagged-word ratio < 10 %.

## If it fails

- Render too slow → `-preset medium` → smaller draft canvas → still failing:
  hardware question moves to the user (the compute options from the grilling:
  GPU, cloud, or overnight queueing).
- Alignment too slow → smaller faster-whisper model → timed-alignment-only
  path (skip transcription scaffold).
- TTS quality fails the ear test → voice/model decision reopens; everything
  downstream is voice-agnostic.
