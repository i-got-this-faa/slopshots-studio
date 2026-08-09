# SlopShots All-in-One

This repository contains the pipeline specification plus a runnable first
implementation: `frontend/` is the SvelteKit operator dashboard and `backend/`
is the FastAPI service that owns the real media stages.

## Local prerequisites

Use Python 3.11 or 3.12, Node.js 20 or newer, and native FFmpeg, FFprobe,
espeak-ng, and libsndfile installations. FFprobe is shipped with FFmpeg. On
Debian/Ubuntu:

```bash
sudo apt-get update
sudo apt-get install -y ffmpeg espeak-ng libsndfile1
```

On macOS, the equivalent is `brew install ffmpeg espeak-ng libsndfile`.

The render contract requires FFmpeg with the `subtitles`, `loudnorm`,
`blackdetect`, `freezedetect`, and `silencedetect` filters. The setup checker
verifies all of these binaries and filters:

```bash
python3 tests/check_local_setup.py --binaries-only
```

## Backend: FastAPI plus real local models

The backend setup contract is `backend/app/main.py` exporting an ASGI object
named `app`. From the repository root, create the project virtual environment
and install the real integration packages with:

```bash
make setup
make check-local PYTHON=.venv/bin/python
cp .env.example .env
set -a; . ./.env; set +a
make run-backend
```

`make setup-api` installs only FastAPI/Uvicorn and is enough for the API and
health surface. Its base requirements deliberately include
`python-multipart>=0.0.9,<1`: FastAPI imports the media upload route at startup,
which uses `File`, `Form`, and `UploadFile`. `make setup` additionally installs the versions declared in
`backend/requirements-integrations.txt`: Kokoro, soundfile, NumPy, and
WhisperX. Kokoro needs the system `espeak-ng` executable for phonemization;
WhisperX needs a compatible CPU PyTorch/torchaudio stack. If pip cannot select
the right CPU wheels for the host, install those matching wheels first and
rerun `make setup`.

Package installation does not fetch model weights. The first real synthesis or
alignment stage may download Kokoro, Whisper, and alignment weights from
Hugging Face. `make check-local` imports the installed Python packages but does
not initialize a model or download weights.

Recommended local defaults for the backend configuration are:

```text
SLOPSHOTS_KOKORO_VOICE=af_heart
SLOPSHOTS_KOKORO_LANGUAGE=a
SLOPSHOTS_KOKORO_SPEED=1.0
SLOPSHOTS_WHISPERX_MODEL=small
SLOPSHOTS_WHISPERX_DEVICE=cpu
SLOPSHOTS_WHISPERX_COMPUTE_TYPE=int8

# OpenCode Zen (OpenAI-compatible Chat Completions)
SLOPSHOTS_OPENCODE_ZEN_BASE_URL=https://opencode.ai/zen/v1
SLOPSHOTS_OPENCODE_ZEN_API_KEY=replace-with-your-opencode-zen-key
SLOPSHOTS_OPENCODE_ZEN_MODEL=deepseek-v4-flash-free
```

The placement LLM defaults to OpenCode Zen's free DeepSeek V4 Flash model.
The backend sends the bare model ID (`deepseek-v4-flash-free`) to the direct
`/v1/chat/completions` endpoint; the `opencode/` prefix is only for an
`opencode.json` model selection. The older `SLOPSHOTS_OPENAI_*` variables are
still accepted as compatibility aliases.

The pipeline uses the normalized script for both Kokoro and WhisperX, emits
`words.json`, and renders with native FFmpeg. See [docs/02-tts-kokoro.md](docs/02-tts-kokoro.md),
[docs/03-alignment-whisperx.md](docs/03-alignment-whisperx.md), and
[docs/08-render-ffmpeg.md](docs/08-render-ffmpeg.md) for stage details.

## Frontend: SvelteKit

In a second terminal, from the SvelteKit app:

```bash
cd frontend
npm ci
VITE_API_BASE_URL=http://127.0.0.1:8000 \
  npm run dev -- --host 127.0.0.1 --port 5173
```

The frontend reads `VITE_API_BASE_URL` for browser requests. If it is unset,
the UI intentionally falls back to local demo data; with it set, job creation
and approval actions call the Python API.
For a production-like check, run `npm run check` and `npm run build` in
`frontend/`.

## Development API contract

The current frontend/backend boundary is intentionally small. `/api/v1` is
the canonical prefix used by the frontend, the route manifest, and the smoke
check:

| Method | Route | Purpose |
|---|---|---|
| `GET` | `/api/v1/health` | Report model-free service and integration availability |
| `GET`, `PATCH` | `/api/v1/settings` | Read or update runtime settings |
| `POST` | `/api/v1/intake/normalize` | Normalize and lint a script without a job |
| `GET` | `/api/v1/jobs`, `/api/v1/jobs/{job_id}` | List or inspect file-backed jobs |
| `POST` | `/api/v1/jobs` | Create a file-backed video job |
| `GET` | `/api/v1/media`, `/api/v1/media/{asset_id}` | List or inspect registered media |
| `POST` | `/api/v1/media/register` | Register an existing local media file |
| `POST` | `/api/v1/media/upload` | Upload a bounded media file as multipart form data |
| `PATCH` | `/api/v1/jobs/{job_id}` | Update media and stage settings |
| `POST` | `/api/v1/jobs/{job_id}/intake` | Store and lint a job script |
| `POST` | `/api/v1/jobs/{job_id}/approve` | Approve the selected job |
| `POST` | `/api/v1/jobs/{job_id}/reject` | Reject the selected job |
| `POST` | `/api/v1/jobs/{job_id}/revise` | Request a revision |
| `POST` | `/api/v1/jobs/{job_id}/stages/{stage}/run` | Run or resume a cached stage |

The compatibility dashboard/action routes remain available for older operator
clients, but they are not part of the canonical contract or smoke test. The
executable schemas and API route manifest are in [tests/schemas](tests/schemas).
The development CORS allowlist defaults to `http://127.0.0.1:5173` plus
`http://localhost:5173` and can be overridden with `SLOPSHOTS_CORS_ORIGINS`.

The model-free health response is shaped like
`tests/schemas/health-response.schema.json`. It reports the data directory,
job count, required-vs-optional integration availability (including the
optional OpenCode Zen placement service), and executable/package
availability without loading model weights.

The pipeline artifact contracts remain the documented ones:

- `words.json`: `[ {"w", "start", "end", "conf"} ]`
- placements: `{ "placements": [ ... ] }`, using word/phrase `anchor_text`
- `timeline.json`: versioned 1080×1920/30fps EDL

The tests read the examples in [docs/03-alignment-whisperx.md](docs/03-alignment-whisperx.md),
[docs/05-overlay-placement.md](docs/05-overlay-placement.md), and
[docs/07-timeline-edl.md](docs/07-timeline-edl.md) and validate their shape.

## Checks

These checks use only the Python standard library. They do not require
FastAPI, SvelteKit, FFmpeg, model packages, model weights, or network access.
They validate the documented artifact/API contracts and smoke-test helpers:

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
# or:
make test
```

After `make setup` and the system-package install, verify local integrations
with `make check-local`. This is a strict environment check; it imports the
installed packages but never loads model weights.

After starting the backend, the optional live smoke check verifies
`/openapi.json`, every canonical `/api/v1` route in the manifest, health,
settings, the model-free job list, and the browser CORS preflight without
creating a job or running a stage:

```bash
python3 tests/smoke_api.py --base-url http://127.0.0.1:8000
```

There is deliberately no `docker-compose.yml` yet: this checkout has no
service Dockerfiles, and real model caches plus CPU/GPU PyTorch selection are
local-machine concerns. Host-native setup keeps those choices visible until
the frontend/backend implementations and pinned images exist.

Useful upstream references: [Kokoro](https://github.com/hexgrad/kokoro),
[WhisperX](https://github.com/m-bain/whisperX),
[FastAPI/Uvicorn](https://fastapi.tiangolo.com/deployment/manually/), and
[SvelteKit](https://svelte.dev/docs/kit).
