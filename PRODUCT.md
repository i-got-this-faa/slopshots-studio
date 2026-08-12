# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

A solo operator — the project owner — running SlopShots on their own local machine to produce narrated vertical gameplay videos for YouTube Shorts / Instagram Reels. They work in bursts: draft a script, start a job, let CPU-bound stages run, then return to inspect, review, and approve. No team, no roles, no clients in v1.

## Product Purpose

Turn a text script into a publishable 9:16 narrated gameplay video through a semi-automated, fully local pipeline. Success means one operator can reliably ship Shorts at under ten minutes of machine time per video, with automated gates catching defects so the human eyeball only judges what already passes.

## Positioning

A stage-cached, file-backed local pipeline: eight stages (script intake, Kokoro TTS, WhisperX alignment, LLM overlay placement, karaoke subtitles, timeline EDL, FFmpeg render, validation) each write inspectable artifacts and resume from the last good stage. The LLM proposes; a hard validation gate plus human approval decides. A neighboring video editor cannot truthfully copy "script to final.mp4 on one machine, with deterministic resume and a blocking quality gate before human review."

## Operating Context

- Local workstation, CPU-only (Kokoro 82M TTS, WhisperX int8 alignment, native FFmpeg). The single network dependency is the OpenCode Zen LLM endpoint used for overlay placement.
- Operator workflow: paste script → create job & intake → run stages (cache hits make re-runs cheap) → inspect artifacts and validation → approve / reject / request revision → manual upload to the platform (deliberately manual in v1).
- Backend is a FastAPI service with file-backed jobs under a data directory; the SvelteKit console at `127.0.0.1:5173` calls `/api/v1` at `127.0.0.1:8000`.
- The console must behave honestly in four data states: live backend, degraded (integrations missing), demo data (API base unset), and stale.
- Rituals with real numbers: script lint 150–230 words ≈ 60–90 s at genre pace; word-level confidence gating; loudness, black, freeze, and silence validation must pass before approval unlocks.

## Capabilities and Constraints

- Eight canonical stages — `intake, tts, align, placements, subtitles, timeline, render, validate` — each runnable, re-runnable, resumable, cache-aware, with per-stage outputs and status.
- Job lifecycle: created → running → awaiting_approval → approved / rejected / completed / failed. Approval is gated on validation passing; rejection and revision carry an operator note.
- Media: gameplay and music assets by upload or registered runner path; source provenance (original / licensed / community) and a permission confirmation are product facts, not decoration.
- Runtime settings: Kokoro voice and speed, WhisperX model/language/device/compute, alignment confidence threshold, karaoke mode (`kf` progressive fill vs `k` word highlight), stage timeout, ffmpeg/ffprobe binaries.
- Terminology that must survive: stages, artifacts, `words.json`, placements, `timeline.json` (versioned 1080×1920/30fps EDL), ASS karaoke, validation gate, eyeball.
- Publishing stays manual in v1; the console says so rather than pretending otherwise.
- OpenCode Zen placement endpoint is the accepted single point of failure; the console reports its availability via health.

## Brand Commitments

Name: SlopShots (repo "SlopShots All-in-One"; console package `slopshots-operator`). No logo, voice guide, or visual assets are established. Visual identity is open territory for the redesign.

## Evidence on Hand

- Pipeline specification: `docs/01`–`docs/14`, `docs/decisions.md`, `docs/risks.md`.
- Working FastAPI backend (`backend/app/`) implementing the canonical `/api/v1` surface: health, settings, jobs, media register/upload, intake normalize, approve/reject/revise, per-stage run.
- Working SvelteKit console (`frontend/`) with live/demo/degraded/stale handling; demo data in `frontend/src/lib/demo-data.ts`.
- Executable schemas in `tests/schemas/`; artifact examples inside the docs.
- Absences future work must not fabricate: no real rendered video exists yet, no benchmarks (project is pre-benchmark), no customers, no testimonials, no published metrics.

## Product Principles

1. The pipeline is the product: stages, artifacts, and gates are shown as they are — inspectable, resumable, cached.
2. Honesty over polish: data provenance (live vs demo vs degraded) is always visible and never faked.
3. Human judgment is the final gate: automate up to validation, then hand the operator one clear approve/reject/revise decision.
4. Local-first and plain: one machine, file-backed jobs, no cloud, no accounts.
5. Operator time is batched: start work, walk away, return to a surface that immediately says what needs attention.
