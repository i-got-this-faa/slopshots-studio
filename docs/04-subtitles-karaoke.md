# 04 — Subtitles: ASS Karaoke Cards

**Status: Selected pending re-confirm (`\kf` sweep), Recommendation (card spec, font)**

## Rendering path

`words.json` → generator emits one `.ass` file → burned into the video by
FFmpeg's `subtitles` filter **in the main render pass**. No per-word PNG
machinery. libass has native karaoke primitives — this is what it was built
for.

## Karaoke mode

- **`\kf` smooth sweep** (selected, pending re-confirm): fill sweeps across
  each word as spoken. Maximally exposes alignment error — see the tolerance
  note in [03](03-alignment-whisperx.md).
- **`\k` instant swap**: word snaps to highlight color. The genre-standard
  look and the designated fallback. The generator takes a per-run `--mode
  kf|k` switch; changing modes must never touch timing logic.

## Card chunking

From the word stream, build cards of:

- **1–3 words**, ≤ 16 visible characters;
- break on sentence punctuation always;
- break on inter-word gaps > 300 ms;
- a card's on-screen span = first word's `start` − 80 ms → last word's `end`
  + 120 ms (lead-in/linger for readability).

## Style

| Property | Value |
|----------|-------|
| Font | Montserrat ExtraBold (OFL — commercially safe) |
| Case | Uppercase (genre norm) |
| Fill | white; active word sweeps to accent (`&H00D7FF` gold) |
| Outline | 6–8 px black — must survive bright Minecraft sky |
| Position | horizontally centered, ~60 % frame height |
| Safe zones | bottom 300 px and right rail reserved for platform UI; generator clamps |

## Sample output

```ass
[Script Info]
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Style: Card,Montserrat ExtraBold,72,&H00FFFFFF,&H0000D7FF,&H00000000,&H64000000,1,0,0,0,100,100,0,0,1,7,3,5,30,30,780,1

[Events]
Dialogue: 0,0:00:00.04,0:00:01.03,Card,,0,0,0,,{\kf19}SO {\kf12}THIS {\kf48}GUY
```

(`\kf` units are centiseconds; SecondaryColour = sweep target.)

## Validation hooks

The render gate ([11](11-validation.md)) checks card bounds: no Dialogue
event may place text below y = 1620 (1080×1920 canvas) or exceed PlayResX.
Checked statically from the `.ass` — cheap, catches generator bugs before
encode.
