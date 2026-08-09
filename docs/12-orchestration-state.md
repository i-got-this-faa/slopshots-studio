# 12 — Orchestration & State

**Status: Decided (stage-cached artifacts)**

## Model

No database, no queue in v1. One directory per video; every stage writes
files; the runner skips any stage whose outputs already exist and are newer
than their inputs. Resume from last good stage is just *running the pipeline
again*.

## Layout

```
videos/2026-08-07-my-story/
  script.txt               # input (human)
  script.normalized.txt    # stage 1: intake
  voice.wav                # stage 2: TTS
  words.json               # stage 3: alignment
  placements.raw.json      # stage 4: LLM output (pre-validation)
  placements.json          # stage 4b: validated, repaired, human-approved
  timeline.json            # stage 5: EDL assembly
  subtitles.ass            # stage 5b: subtitle generation
  render/
    filtergraph.txt        # emitted graph
    cmd.sh                 # exact replayable command
    draft.mp4              # draft mode output
  final.mp4                # stage 6: render
  validation.json          # stage 7: gate results
  approval.md              # human decision log (chat transcript summary)
```

## Stage contract

Each stage: read declared inputs → write declared outputs → exit non-zero on
failure with a one-line reason to stderr. The runner is a thin script
(Makefile or ~100 lines of Python) with dependency edges:

```
intake → tts → align → placements → timeline → render → validate
                     ↑ (align feeds placements via anchor resolution)
```

- Re-run semantics: `rm words.json` → align and everything downstream
  re-runs; TTS (the expensive-ish stage) is untouched.
- **Idempotency**: a stage run twice on identical inputs produces identical
  outputs (LLM stage excepted — hence `placements.json` is frozen at
  approval, never regenerated automatically).

## Approval as a state transition

`placements.json` and `timeline.json` exist only after human approval in
chat. Their presence *is* the approved state — no flags, no DB rows.

## Concurrency

One video at a time in v1 (single box, software encode). The layout is
per-video isolated, so a future worker queue parallelizes without redesign.

## Upgrade path

When volume justifies it: swap the runner for a queue (Dramatiq/Celery) and
the directory scan for SQLite. The stage contract (files in, files out)
survives unchanged.
