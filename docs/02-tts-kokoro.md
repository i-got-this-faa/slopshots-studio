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
