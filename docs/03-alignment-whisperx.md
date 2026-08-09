# 03 — Alignment: WhisperX

**Status: Decided (tool), Selected pending re-confirm (confidence gate)**

## Why forced alignment

Local TTS emits no usable word boundaries. But we hold the ground-truth
transcript (`script.normalized.txt`), so this is *forced alignment*, not
transcription — WhisperX aligns known text to audio and returns per-word
timings with confidence scores.

## Setup

```bash
pip install whisperx   # pulls faster-whisper; CPU: use int8 small/base
```

```python
import whisperx
model = whisperx.load_model("small", device="cpu", compute_type="int8")
audio = whisperx.load_audio("voice.wav")
result = model.transcribe(audio)  # language detection scaffold
align_model, meta = whisperx.load_align_model(language_code=result["language"], device="cpu")
aligned = whisperx.align(result["segments"], align_model, meta, audio, device="cpu")
```

For strict forced alignment, feed the normalized script as the transcript
segments rather than Whisper's own hypotheses where they diverge.

## Output: `words.json`

```json
[
  {"w": "So",        "start": 0.120, "end": 0.310, "conf": 0.97},
  {"w": "this",      "start": 0.310, "end": 0.430, "conf": 0.98},
  {"w": "forty-two", "start": 0.435, "end": 0.910, "conf": 0.61}
]
```

Consumers: subtitle generator ([04](04-subtitles-karaoke.md)), placement
anchor resolution ([05](05-overlay-placement.md)).

## Timing QA — confidence gate (pending re-confirm)

- Each word carries `conf`. Threshold: **0.6** initial, tune after benchmark.
- Words below threshold cluster into *flagged segments* (±1 s context),
  listed in the approval chat for a human spot-check.
- Flagged ratio > 10 % of words → treat as systemic (audio/lexicon problem),
  not per-word noise. Do not render.

The declined alternative (re-transcribe the rendered video and diff) remains
available as a later hardening step; it doubles alignment cost per video.

## Karaoke tolerance

The `\kf` sweep ([04](04-subtitles-karaoke.md)) shows errors of ±50 ms.
Expect confidence-gate tuning to be the main iteration loop after the
benchmark. If drift persists on clean audio, the escape hatch is `\k`
instant swap — a one-line change in the ASS generator.

## Failure modes

| Failure | Signal | Fix |
|---------|--------|-----|
| TTS said something else | Low conf on specific words | Lexicon ([01](01-script-intake.md)), re-TTS |
| Audio artifact at seam | Conf dip at chunk boundary | Re-chunk with longer crossfade |
| Uniform low conf | Bad audio render | Re-TTS before touching alignment |
