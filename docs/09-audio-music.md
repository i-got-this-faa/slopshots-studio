# 09 — Audio & Music

**Status: Decided (licensed library + sidechain duck), Recommendation (fades, targets)**

## Chain

```
voice.wav ──aresample── compressor ── split ──┬────────── amix ── loudnorm ── aac
                                              └─ sidechain key ─┐
music ───────────────────────────────────────────────────────── sidechaincompress
                                                   (ducked music returns to amix)
```

## Ducking

`sidechaincompress` with the narration as the key:

```
[music][voice_sc]sidechaincompress=threshold=0.02:ratio=8:attack=20:release=400:makeup=1[musicduck]
```

- Music bed baseline: **−22 dB** relative to voice (`gain_db` in
  [07](07-timeline-edl.md)), ducked a further ~8–12 dB under speech.
- Attack 20 ms / release 400 ms: fast enough to dip on sentence starts,
  slow enough not to pump between words.

## Loudness

- Music library is pre-normalized at ingest (two-pass `loudnorm` to
  −16 LUFS per track) so per-video render needs only light correction.
- Final mix target: **−14 LUFS integrated**, true peak ≤ −1 dBTP
  (YouTube norm). Measured — not assumed — at validation
  ([11](11-validation.md)).

Narration is compressed before the final normalization with
`threshold=0.1:ratio=4:attack=20:release=250:makeup=4`. This controls isolated
speech peaks so the one-pass final `loudnorm` can reach the validation window
without clipping or flattening the whole mix.

## Production rules (borrowed from video-use)

- **30 ms fades at every audio cut** — no exceptions; clicks at seams are
  the most audible amateur signal in the genre.
- Music enters at −∞ and fades in over 0.5–1.0 s; last 1.5 s fades out.
- Game audio: **not used**. Gameplay is a visual bed only.

## Music library

- Small licensed set (start: 5–10 tracks), rights cleared for monetized
  short-form. `source` + license file live next to each track.
- Track selection: from `timeline.json` — manual at approval time in v1
  (one line in chat), genre-mood auto-pick later.

## Failure modes

| Failure | Detection | Fix |
|---------|-----------|-----|
| Pumping artifacts | Ear at approval | Release ↑, ratio ↓ |
| Music masks quiet words | LUFS segment check + ear | Baseline −22 → −26 dB |
| Click at chunk seam | silencedetect won't catch it; ear will | Crossfade length ↑ in [02](02-tts-kokoro.md) |
