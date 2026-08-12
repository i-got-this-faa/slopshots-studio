# 04 — Subtitles: ASS Karaoke Cards

**Status: Selected pending re-confirm (`\kf` sweep), Recommendation (card spec, font)**

## Rendering path

`words.json` → generator emits one `.ass` file → burned into the video by
FFmpeg's `subtitles` filter **in the main render pass**. No per-word PNG
machinery. libass has native karaoke primitives — this is what it was built
for.

## Karaoke mode

- **`\kf` smooth sweep**: each word gets its own short layer-2 event and
  sweeps from gold to white only while that word is spoken.
- **`\k` instant swap**: the active word is solid gold for its aligned span.
- A layer-1 base card keeps every inactive word white. Future and past words
  are explicitly forced to white, so multiple words can never remain
  highlighted together.

## Card chunking

From the word stream, build cards of:

- **1–4 words**, ≤ 29 visible characters total, at most two balanced lines;
- each rendered line is limited to 14 visible characters before a new card;
- break on sentence punctuation always;
- break on inter-word gaps > 300 ms;
- a card's requested span is first word's `start` − 80 ms → last word's
  `end` + 120 ms;
- when adjacent requested spans overlap, switch once at the midpoint between
  the adjacent word timings. Two Dialogue events must never render at the same
  fixed position simultaneously.

## Style

| Property | Value |
|----------|-------|
| Font | Montserrat ExtraBold (OFL — commercially safe), 92 px |
| Case | Uppercase (genre norm) |
| Layout | Centered, max two explicitly balanced lines |
| Fill | white; exactly one active word uses accent (`&H00D7FF` gold) |
| Contrast | one shared ~69%-opaque black vector backdrop per card |
| Backdrop size | text-width estimate capped at 940 px; 126 px high for one line, 236 px for two |
| Position | horizontally centered, ~60 % frame height |
| Safe zones | bottom 300 px and right rail reserved for platform UI; generator clamps |

## Sample output

```ass
[Script Info]
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Style: Backdrop,Arial,10,&H50000000,&H50000000,&H50000000,&H50000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1
Style: Card,Montserrat ExtraBold,92,&H00FFFFFF,&H00D7FF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,7,2,5,30,30,780,1

[Events]
Dialogue: 0,0:00:00.04,0:00:01.03,Backdrop,,0,0,0,,{\p1}m 0 0 l 620 0 620 126 0 126{\p0}
Dialogue: 1,0:00:00.04,0:00:01.03,Card,,0,0,0,,SO THIS GUY
Dialogue: 2,0:00:00.23,0:00:00.35,Card,,0,0,0,,SO {\kf12}THIS GUY
```

(`\kf` units are centiseconds; the layer-2 event exists only for its active word.)

## Validation hooks

The render gate ([11](11-validation.md)) checks card bounds: no Dialogue
event may place text below y = 1620 (1080×1920 canvas) or exceed PlayResX.
Checked statically from the `.ass` — cheap, catches generator bugs before
encode.
