# SlopShots backend

This directory contains the backend-only FastAPI service for the file-backed
SlopShots pipeline described in `../docs/`. It does not modify or serve the
frontend.

## Run

Install the base API dependencies and start the service from the repository
root:

```bash
python3 -m pip install -r backend/requirements.txt -r backend/requirements-integrations.txt
uvicorn app.main:app --app-dir backend --reload
```

The default data directory is `backend/data`. Set `SLOPSHOTS_DATA_DIR` to put
video job directories elsewhere. Each job is isolated under
`<data-dir>/videos/<slug>-<id>/` and stores its stage artifacts directly.

## API surface

- `GET /health` and `GET /api/v1/health` report service and integration
  availability.
- `GET /dashboard` and `GET /api/dashboard` expose the compatibility dashboard
  contract; the SvelteKit app uses the canonical `/api/v1` routes below.
- `GET/PATCH /api/v1/settings` manages runtime settings.
- `POST /api/v1/intake/normalize` normalizes and lints a script without
  creating a job.
- `POST/GET/PATCH /api/v1/jobs` and `/api/v1/jobs/{id}` create and inspect
  jobs.
- `POST /api/v1/jobs/{id}/intake` stores a replacement script and returns its
  normalized text and lint result.
- `POST /api/v1/jobs/{id}/stages/{stage}/run` runs a cached stage and its
  prerequisites. `GET /api/v1/jobs/{id}/stages` reports stage status.
- `GET /api/v1/jobs/{id}/artifacts` lists safe download paths;
  `/api/v1/jobs/{id}/artifacts/{path}` downloads one artifact.
- `POST /api/v1/jobs/{id}/approve`, `/reject`, and `/revise` write the approval
  transition and (for approve/reject) `approval.md`.

Valid stages are `intake`, `tts`, `align`, `placements`, `subtitles`,
`timeline`, `render`, and `validate`.

The placements stage accepts a typed `placements` array in its run request.
That represents the validated output of the configured placement service; this
backend does not invent placements or silently omit them. When
`use_opencode_zen` is enabled (the legacy `use_openai` flag is also accepted)
and no manual array is supplied, the adapter uses OpenCode Zen's
OpenAI-compatible `https://opencode.ai/zen/v1/chat/completions` endpoint with
the free `deepseek-v4-flash-free` model by default. A successful request writes
`placements.raw.json`, resolves anchors against `words.json`, applies
deterministic zone collision handling, and writes `placements.json`.

## Integrations and failure behavior

Kokoro, WhisperX, FFmpeg, and FFprobe are real adapters. Optional runtime
packages and binaries are detected lazily. If one is absent, the stage fails
with a `424 dependency_unavailable` response containing the dependency and
installation/configuration hint; no synthetic audio, timings, or video is
created.

FFmpeg is invoked with an argv list (`shell=False`) and emits the exact
filtergraph and replayable command under `render/`. Timeline invariants,
subtitle bounds, confidence gating, and the FFprobe/FFmpeg validation checks
are applied before approval.

## Lightweight checks

The repository can be checked without downloading model packages:

```bash
python3 -m compileall -q backend
```

The integration requirements install the real Kokoro and WhisperX packages;
the first synthesis/alignment run may download model weights. Installing the
base requirements alone only starts the API and health surface.
