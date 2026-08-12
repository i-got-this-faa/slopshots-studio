# 02 — TTS: Kokoro

**Status: Decided**

## Choice

[Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) — Apache-2.0, 82M
params, runs on CPU, best quality-per-size of the local options. No word
timestamps are emitted (true of all local engines considered) — timestamps
come from [03](03-alignment-whisperx.md).

Rejected: Piper (flatter delivery, weak for the genre), XTTS v2 (wants a GPU;
Coqui Public Model License is non-commercial).

## Setup

```bash
pip install kokoro soundfile   # plus espeak-ng system package
```

## Generation

- Input: `script.normalized.txt`; output: `voice.wav` (mono, 24 kHz is
  native; resample to 48 kHz at render).
- Default speed 1.0; adjust ±0.1 to land in the 60–90 s window
  ([01](01-script-intake.md)).
- Voice: pick by **ear test** — render the same 3 script samples through the
  candidate voices (`af_heart`, `af_bella`, `am_adam`, …) before the first
  real video. The voice *is* the channel identity.

## Voice presets

The API exposes `GET /api/v1/voice-presets`. A job can select one with
`voice_preset`; job creation resolves the preset to the concrete Kokoro voice
and speed before TTS and persists both values for reproducible cache keys.

| Preset | Kokoro voice | Speed | Direction |
|--------|--------------|-------|-----------|
| `mad-scientist` | `am_onyx` | 1.08 | Fast, intense, lower delivery |
| `nervous-sidekick` | `am_puck` | 1.14 | Quick, youthful, restless delivery |
| `sleazy-charmer` | `am_liam` | 1.04 | Smooth, upbeat, overconfident delivery |
| `loud-dad` | `am_fenrir` | 0.94 | Big, blunt sitcom-dad delivery |
| `scheming-prodigy` | `am_echo` | 1.10 | Precise, clipped, smug delivery |
| `warm-storyteller` | `af_heart` | 0.98 | Friendly narration |
| `sharp-commentator` | `af_bella` | 1.03 | Clear, assertive commentary |

These are original style directions using Kokoro's licensed voice packs, not
clones or impersonations of actors or copyrighted characters. Kokoro 0.9
supports voice selection and speed but not per-voice pitch or reference-audio
cloning.

## Chunking

Kokoro handles long input via sentence segmentation internally; if manual
chunking is needed, split on sentence boundaries only and concatenate with
30 ms crossfades. Alignment runs on the final stitched file, so chunk seams
must be click-free but carry no timestamp logic.

## Failure modes

| Failure | Detection | Fix |
|---------|-----------|-----|
| Wrong pronunciation | Alignment mismatch ([03](03-alignment-whisperx.md)) | Lexicon entry, re-TTS |
| Flat/robotic delivery | Human ear test | Different voice; genre-fit is a hard gate |
| Duration outside 60–90 s | `ffprobe` on `voice.wav` | Speed factor, then script edit |

## Cost

Local: zero marginal cost per re-render. Re-TTS is always the cheapest
iteration step — prefer re-generating audio over patching it.
