# 08 — Render: FFmpeg Filtergraph Generation

**Status: Decided**

## Strategy

A generator reads `timeline.json` and emits **one** `filter_complex` graph,
executed in a single `ffmpeg` invocation. One pass, no intermediates.

Why one graph: no intermediate codec losses, no temp-disk I/O, and the whole
render is reproducible from `timeline.json` + inputs. The cost is
debuggability — mitigated by the segment mode below.

## Graph skeleton (order matters)

```
[0:v] trim, crop 9:16, fps, scale=1080:1920        → gameplay base
      effects (zoom-punch/shake envelopes)          → base fx
      overlay chain (one per asset, enable=between) → + overlays
      subtitles=subtitles.ass                       → + karaoke
[1:a] voice: aresample 48k                          → voice
[2:a] music: volume, loudnorm, sidechaincompress    → ducked bed
      voice+music amix                              → audio out
```

- Overlays: `overlay=x:y:enable='between(t,T0,T1)'` with animation
  envelopes per [07](07-timeline-edl.md). PNG inputs via `-i` (static) or
  `movie=` — bounded count (~10/video), so `-i` fan-in is fine.
- Zoom-punch/shake: animated `crop`/`scale` expressions driven by `t`.
- Audio graph details in [09](09-audio-music.md).

## Encode settings (validation contract, [11](11-validation.md))

```
-c:v libx264 -preset slow -crf 18 -pix_fmt yuv420p -r 30
-c:a aac -b:a 192k -ar 48000
-movflags +faststart
1080x1920, duration = voice duration (+ 0.3 s tail)
```

`-preset slow` is the benchmark variable — on weak CPUs drop to `medium`
before touching CRF.

## Debuggability

- **Segment mode**: `--from 12 --to 15` renders a 3 s slice — the approval
  loop never waits for full renders to check one overlay.
- **Draft mode**: `-crf 28 -preset veryfast`, 540×960 — 8× faster eyeball
  passes.
- The emitted graph is written to `render/filtergraph.txt` and the exact
  command to `render/cmd.sh` — every render is replayable by hand.

## Performance expectations (to verify in benchmark)

Software x264 at 1080×1920 with ~10 overlay inputs and libass: expect
0.5–2× realtime on a modern CPU, far worse on old silicon. The benchmark
gate ([14](14-benchmark-gate.md)) exists precisely to measure this box.

## Failure modes

| Failure | Signal | Fix |
|---------|--------|-----|
| Filtergraph syntax error | ffmpeg exit ≠ 0, logged | Generator bug; `cmd.sh` reproduces it standalone |
| Overlay never appears | Validation freeze/black checks pass but approval catches it | `enable=between` window vs resolved `t` — check anchor resolution |
| Audio out of sync | Human ear | Usually a trim/offset sign error in the graph |
