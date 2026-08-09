# 01 — Script Intake

**Status: Decided (duration target), Recommendation (normalization, lint)**

## Input format

One plain-text UTF-8 file per video. No inline markup in v1 — the LLM
placement stage ([05](05-overlay-placement.md)) reads the same text, so
author-supplied cues would conflict with machine placements.

## Normalization (before TTS, mandatory)

The alignment stage ([03](03-alignment-whisperx.md)) aligns the *script text*
against the *rendered audio*. That only works if the text equals what the
voice actually says. Therefore: normalize first, then both TTS and alignment
consume `script.normalized.txt`.

Rules (extend as misreads are observed):

| Input | Output |
|-------|--------|
| `$5` / `€20` | `five dollars` / `twenty euros` |
| `GTA V` | `GTA five` |
| `Mr.` / `Dr.` | `mister` / `doctor` |
| URLs, handles (`@x`), hashtags | stripped or spoken form |
| Emoji, unicode symbols | stripped |
| `...` / `--` | sentence pause (period) |
| Numerals `42` | `forty-two` |

A persistent **pronunciation lexicon** (`lexicon.yml`) holds recurring
fixes discovered via alignment mismatches — a mismatch means the TTS said
something other than the text, i.e. a missing lexicon entry.

## Duration lint

- Genre pace ≈ **2.5 words/second** → 60–90 s ≈ **150–230 words**.
- Intake rejects scripts outside 130–260 words (hard fail) and warns outside
  150–230 (soft).
- Kokoro speed factor (±10%) is the first correction lever; script edits are
  the second. Never ship a >90 s render for a Shorts target without an
  explicit override.

## Artifacts

```
script.txt              # author input
script.normalized.txt   # canonical text for TTS + alignment + LLM prompt
```

## Failure modes

- Un-normalized token reaches TTS → alignment mismatch → re-run after
  lexicon fix (cheap: TTS is local).
- Profanity / sensitive topics: platform monetization lint runs at intake
  (warn-only in v1; the human approves anyway).
