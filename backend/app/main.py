"""FastAPI entry point for the SlopShots backend slice."""

from __future__ import annotations

import mimetypes
import os
import json
import tempfile
import uuid
from pathlib import Path
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, FastAPI, File, Form, Query, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from .config import SettingsManager, get_settings
from .errors import (
    ApprovalRequiredError,
    CommandExecutionError,
    ConflictError,
    DependencyUnavailableError,
    InvalidRequestError,
    NotFoundError,
    PipelineError,
    StageBlockedError,
)
from .models import (
    ApprovalRequest,
    ApprovalResponse,
    AppSettings,
    ArtifactListResponse,
    HealthResponse,
    IntegrationAvailability,
    MediaAsset,
    MediaKind,
    MediaListResponse,
    MediaRegisterRequest,
    MediaSource,
    NormalizationResult,
    ScriptIntakeRequest,
    ScriptIntakeResponse,
    SettingsUpdate,
    StageName,
    StageRunRequest,
    StageRunResponse,
    StageStatusResponse,
    JobStatus,
    VideoJob,
    VideoJobCreate,
    VoicePreset,
    VOICE_PRESETS,
    VideoJobUpdate,
)
from .pipeline.ffmpeg import FFmpegAdapter
from .pipeline.integrations import (
    KokoroTTSAdapter,
    OpenAIPlacementAdapter,
    WhisperXAlignmentAdapter,
)
from .pipeline.service import PipelineService
from .store import JobStore


API_VERSION = "1.0.0"


def create_app(app_settings: AppSettings | None = None) -> FastAPI:
    manager = SettingsManager(app_settings or get_settings())
    store = JobStore(
        manager.value.data_dir,
        media_input_roots=manager.value.media_input_roots,
        max_upload_bytes=manager.value.max_upload_bytes,
    )
    pipeline = PipelineService(store, manager)

    app = FastAPI(
        title="SlopShots Pipeline API",
        version=API_VERSION,
        description="File-backed stage-cached backend for the SlopShots video pipeline.",
    )
    cors_origins = [
        origin.strip()
        for origin in os.getenv(
            "SLOPSHOTS_CORS_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173",
        ).split(",")
        if origin.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.settings_manager = manager
    app.state.store = store
    app.state.pipeline = pipeline

    @app.exception_handler(PipelineError)
    async def pipeline_error_handler(_: Request, exc: PipelineError) -> JSONResponse:
        status = 500
        if isinstance(exc, NotFoundError):
            status = 404
        elif isinstance(exc, InvalidRequestError):
            status = 400
        elif isinstance(exc, (ConflictError, StageBlockedError, ApprovalRequiredError)):
            status = 409
        elif isinstance(exc, DependencyUnavailableError):
            status = 424
        elif isinstance(exc, CommandExecutionError):
            status = 502
        body: dict[str, object] = {"code": getattr(exc, "code", "pipeline_error"), "message": str(exc)}
        if isinstance(exc, DependencyUnavailableError):
            body["dependency"] = exc.dependency
            if exc.executable:
                body["executable"] = exc.executable
        return JSONResponse(status_code=status, content={"detail": body})

    @app.exception_handler(RequestValidationError)
    async def request_validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "detail": {
                    "code": "request_validation_failed",
                    "message": "request validation failed",
                    "errors": json.loads(json.dumps(exc.errors(), default=str)),
                }
            },
        )

    @app.get("/", include_in_schema=False)
    async def root() -> dict[str, str]:
        return {"service": "slopshots-backend", "health": "/health"}

    router = APIRouter(prefix="/api/v1")

    @router.get("/health", response_model=HealthResponse)
    async def api_health() -> HealthResponse:
        return _health(manager, store)

    @router.get("/settings", response_model=AppSettings)
    async def get_runtime_settings() -> AppSettings:
        return manager.value

    @router.patch("/settings", response_model=AppSettings)
    async def update_runtime_settings(update: SettingsUpdate) -> AppSettings:
        return manager.update(update)

    @router.get("/voice-presets", response_model=list[VoicePreset])
    async def list_voice_presets() -> list[VoicePreset]:
        return list(VOICE_PRESETS)

    @router.post("/intake/normalize", response_model=NormalizationResult)
    async def normalize_script(request: ScriptIntakeRequest) -> NormalizationResult:
        return pipeline.intake(request.script)

    @router.get("/media", response_model=MediaListResponse)
    async def list_media(kind: MediaKind | None = None) -> MediaListResponse:
        return MediaListResponse(assets=store.list_media(kind=kind))

    @router.get("/media/{asset_id:path}", response_model=MediaAsset)
    async def get_media(asset_id: str) -> MediaAsset:
        return store.get_media(asset_id)

    @router.post("/media/register", response_model=MediaAsset, status_code=201)
    def register_media(request: MediaRegisterRequest) -> MediaAsset:
        return store.register_media(request)

    @router.post("/media/upload", response_model=MediaAsset, status_code=201)
    async def upload_media(
        file: UploadFile = File(...),
        asset_id: str = Form(...),
        kind: MediaKind = Form(...),
        source: MediaSource = Form(...),
        confirmed: bool = Form(False),
        description: str = Form(""),
        tags: str = Form(""),
    ) -> MediaAsset:
        """Stream an upload to a bounded temp file before managed registration."""

        incoming_dir = store.data_dir / ".incoming"
        incoming_dir.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{uuid.uuid4().hex}-",
            suffix=".upload",
            dir=incoming_dir,
        )
        temporary = Path(temporary_name)
        total = 0
        try:
            with os.fdopen(descriptor, "wb") as handle:
                while True:
                    chunk = await file.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > store.max_upload_bytes:
                        raise InvalidRequestError(
                            f"upload exceeds maximum size of {store.max_upload_bytes} bytes"
                        )
                    handle.write(chunk)
                handle.flush()
                os.fsync(handle.fileno())
            return await run_in_threadpool(
                store.register_uploaded_media,
                temporary,
                asset_id=asset_id,
                kind=kind,
                source=source.value,
                confirmed=confirmed,
                description=description,
                tags=[tag.strip() for tag in tags.split(",") if tag.strip()],
                filename=file.filename or f"{asset_id}.bin",
                declared_media_type=file.content_type,
            )
        finally:
            await file.close()
            temporary.unlink(missing_ok=True)

    @router.post("/jobs", response_model=VideoJob, status_code=201)
    async def create_job(request: VideoJobCreate) -> VideoJob:
        return _present_job(store.create(request, manager.value))

    @router.get("/jobs", response_model=list[VideoJob])
    async def list_jobs(limit: Annotated[int, Query(ge=1, le=100)] = 50) -> list[VideoJob]:
        return [_present_job(job) for job in store.list()[:limit]]

    @router.get("/jobs/{job_id}", response_model=VideoJob)
    async def get_job(job_id: str) -> VideoJob:
        return _present_job(store.get(job_id))

    @router.patch("/jobs/{job_id}", response_model=VideoJob)
    def update_job(job_id: str, update: VideoJobUpdate) -> VideoJob:
        return _present_job(store.update(job_id, update))

    @router.post("/jobs/{job_id}/intake", response_model=ScriptIntakeResponse)
    def intake_job(job_id: str, request: ScriptIntakeRequest) -> ScriptIntakeResponse:
        job, result = pipeline.intake_job(job_id, request.script)
        return ScriptIntakeResponse(job=_present_job(job), result=result)

    @router.post("/jobs/{job_id}/stages/{stage}/run", response_model=StageRunResponse)
    def run_stage(job_id: str, stage: StageName, request: StageRunRequest | None = None) -> StageRunResponse:
        # Runs in FastAPI's threadpool: stage work (TTS, alignment, render) is
        # blocking and must not freeze the event loop for minutes.
        job, record = pipeline.run_stage(job_id, stage, request)
        return StageRunResponse(job=_present_job(job), stage=record)

    @router.get("/jobs/{job_id}/stages", response_model=StageStatusResponse)
    async def stage_status(job_id: str) -> StageStatusResponse:
        job = store.get(job_id)
        return StageStatusResponse(job_id=job.id, stages=job.stages)

    @router.get("/jobs/{job_id}/stages/{stage}", response_model=StageRunResponse)
    async def get_stage_status(job_id: str, stage: StageName) -> StageRunResponse:
        job = store.get(job_id)
        record = next((item for item in job.stages if item.stage == stage), None)
        if record is None:
            raise NotFoundError(f"stage '{stage.value}' is not configured")
        return StageRunResponse(job=_present_job(job), stage=record)

    @router.get("/jobs/{job_id}/artifacts", response_model=ArtifactListResponse)
    async def list_artifacts(job_id: str) -> ArtifactListResponse:
        job = store.get(job_id)
        return ArtifactListResponse(job_id=job.id, artifacts=_present_job(job).artifacts)

    @router.get("/jobs/{job_id}/artifacts/{artifact_path:path}")
    async def download_artifact(job_id: str, artifact_path: str):
        path = store.resolve_artifact(job_id, artifact_path)
        media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        return FileResponse(path, media_type=media_type, filename=path.name)

    @router.post("/jobs/{job_id}/approve", response_model=ApprovalResponse)
    def approve_job(job_id: str, request: ApprovalRequest | None = None) -> ApprovalResponse:
        request = request or ApprovalRequest()
        job, approval = pipeline.approve(
            job_id,
            decided_by=request.decided_by,
            comment=request.comment,
        )
        return ApprovalResponse(job=_present_job(job), approval=approval)

    @router.post("/jobs/{job_id}/reject", response_model=ApprovalResponse)
    def reject_job(job_id: str, request: ApprovalRequest | None = None) -> ApprovalResponse:
        request = request or ApprovalRequest()
        job, approval = pipeline.reject(
            job_id,
            decided_by=request.decided_by,
            comment=request.comment,
        )
        return ApprovalResponse(job=_present_job(job), approval=approval)

    @router.post("/jobs/{job_id}/revise", response_model=VideoJob)
    def revise_job(job_id: str, request: ApprovalRequest | None = None) -> VideoJob:
        request = request or ApprovalRequest()
        return _present_job(pipeline.revise(job_id, comment=request.comment))

    app.include_router(router)

    # Compatibility surface for the first operator dashboard. The canonical
    # pipeline API is under /api/v1; these read/action routes keep the thin
    # dashboard contract useful for browser smoke checks and older clients.
    @app.get("/dashboard")
    @app.get("/api/dashboard")
    async def dashboard() -> dict[str, object]:
        return _dashboard_payload(store, manager.value)

    @app.post("/jobs/{job_id}/{action}")
    def dashboard_action(job_id: str, action: str) -> dict[str, object]:
        if action == "approve":
            pipeline.approve(job_id, decided_by="operator-dashboard", comment=None)
        elif action == "rerun":
            pipeline.run_stage(job_id, StageName.RENDER, StageRunRequest(force=True))
        elif action == "revise":
            pipeline.revise(job_id, comment="revision requested by operator-dashboard")
        else:
            raise NotFoundError(f"unsupported dashboard action '{action}'")
        return _dashboard_job(store.get(job_id), store)

    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return _health(manager, store)

    return app


def _health(manager: SettingsManager, store: JobStore) -> HealthResponse:
    settings = manager.value
    kokoro_available, kokoro_detail = KokoroTTSAdapter.availability()
    whisperx_available, whisperx_detail = WhisperXAlignmentAdapter.availability()
    ffmpeg = FFmpegAdapter(settings.ffmpeg_bin, settings.ffprobe_bin).availability()
    openai_key = settings.openai_api_key
    openai_available, openai_detail = OpenAIPlacementAdapter(
        base_url=settings.openai_base_url,
        api_key=openai_key.get_secret_value() if openai_key else None,
        model=settings.openai_model,
        timeout_s=settings.openai_timeout_s,
    ).availability()
    integrations = {
        "kokoro": IntegrationAvailability(
            available=kokoro_available,
            dependency="kokoro",
            required=True,
            detail=kokoro_detail,
        ),
        "whisperx": IntegrationAvailability(
            available=whisperx_available,
            dependency="whisperx",
            required=True,
            detail=whisperx_detail,
        ),
        "ffmpeg": IntegrationAvailability(
            available=ffmpeg["ffmpeg"],
            dependency="ffmpeg",
            required=True,
            executable=settings.ffmpeg_bin,
            detail=None if ffmpeg["ffmpeg"] else f"executable not found: {settings.ffmpeg_bin}",
        ),
        "ffprobe": IntegrationAvailability(
            available=ffmpeg["ffprobe"],
            dependency="ffprobe",
            required=True,
            executable=settings.ffprobe_bin,
            detail=None if ffmpeg["ffprobe"] else f"executable not found: {settings.ffprobe_bin}",
        ),
        "openai_placement": IntegrationAvailability(
            available=openai_available,
            dependency=OpenAIPlacementAdapter.dependency,
            required=False,
            detail=openai_detail,
        ),
    }
    data_directory = settings.data_dir.expanduser().resolve()
    data_directory_writable = data_directory.is_dir() and os.access(data_directory, os.W_OK)
    try:
        job_count = len(store.list())
    except PipelineError:
        job_count = 0
        data_directory_writable = False
    ready = data_directory_writable and all(
        integration.available
        for integration in integrations.values()
        if integration.required
    )
    return HealthResponse(
        status="ok" if ready else "degraded",
        service="slopshots-backend",
        version=API_VERSION,
        integrations=integrations,
        data_directory=str(data_directory),
        data_directory_writable=data_directory_writable,
        job_count=job_count,
    )


def _present_job(job: VideoJob) -> VideoJob:
    artifacts = [
        artifact.model_copy(
            update={
                "download_path": f"/api/v1/jobs/{job.id}/artifacts/{quote(artifact.name, safe='/')}"
            }
        )
        for artifact in job.artifacts
    ]
    return job.model_copy(update={"artifacts": artifacts})


def _dashboard_payload(store: JobStore, settings: AppSettings) -> dict[str, object]:
    jobs = [_dashboard_job(job, store) for job in store.list()]
    in_flight = sum(job["status"] in {"queued", "rendering"} for job in jobs)
    review = sum(job["status"] == "review" for job in jobs)
    return {
        "stats": {
            "inFlight": in_flight,
            "review": review,
            "averageRender": "local",
            "passRate": "—",
        },
        "jobs": jobs,
        "settings": {
            "kokoro": {
                "voice": settings.kokoro_voice,
                "speed": settings.kokoro_speed,
                "sampleRate": "24 kHz native",
            },
            "whisperx": {
                "model": settings.whisperx_model,
                "language": settings.whisperx_language or "Auto",
                "device": settings.whisperx_device,
            },
            "ffmpeg": {
                "preset": "slow",
                "fps": "30 fps",
                "resolution": "1080 × 1920",
            },
        },
    }


def _dashboard_job(job: VideoJob, store: JobStore) -> dict[str, object]:
    status = {
        JobStatus.AWAITING_APPROVAL: "review",
        JobStatus.APPROVED: "approved",
        JobStatus.FAILED: "failed",
        JobStatus.REJECTED: "failed",
        JobStatus.RUNNING: "rendering",
        JobStatus.COMPLETED: "approved",
    }.get(job.status, "queued")
    stage_rows = []
    for stage in job.stages:
        stage_state = {
            "succeeded": "complete",
            "cached": "complete",
            "running": "active",
            "failed": "error",
            "blocked": "error",
        }.get(stage.status.value, "pending")
        stage_rows.append({
            "id": stage.stage.value,
            "name": "Kokoro TTS" if stage.stage.value == "tts" else "WhisperX align" if stage.stage.value == "align" else "Validation gate" if stage.stage.value == "validate" else stage.stage.value.title(),
            "detail": stage.message or "Waiting for stage",
            "state": stage_state,
        })
    completed = sum(row["state"] == "complete" for row in stage_rows)
    artifacts = []
    for artifact in job.artifacts:
        artifact_type = "video" if artifact.media_type.startswith("video") else "audio" if artifact.media_type.startswith("audio") else "data" if artifact.name.endswith(".json") else "command" if artifact.name.endswith(".sh") else "text"
        artifacts.append({
            "name": artifact.name,
            "type": artifact_type,
            "size": _format_bytes(artifact.size_bytes),
            "meta": artifact.media_type,
        })
    validation = [{
        "label": "Backend status",
        "value": job.last_error or "Waiting for validation stage",
        "state": "fail" if job.last_error else "warn",
    }]
    validation_path = store.job_dir(job.id) / "validation.json"
    if validation_path.exists():
        try:
            report = json.loads(validation_path.read_text(encoding="utf-8"))
            validation = [
                {
                    "label": check.get("name", "check"),
                    "value": check.get("detail", ""),
                    "state": "pass" if check.get("passed") else "fail",
                }
                for check in report.get("checks", [])
            ] or validation
        except (OSError, json.JSONDecodeError, AttributeError):
            pass
    return {
        "id": job.id,
        "title": job.name,
        "slug": job.name.lower().replace(" ", "-") or "untitled",
        "status": status,
        "statusLabel": {"review": "Ready for review", "approved": "Approved", "failed": "Pipeline failed", "rendering": "Running pipeline", "queued": "Queued"}[status],
        "updated": job.updated_at.isoformat(),
        "duration": "—",
        "progress": round(completed / max(1, len(stage_rows)) * 100),
        "scriptWords": 0,
        "owner": "local",
        "accent": "violet",
        "stages": stage_rows,
        "artifacts": artifacts,
        "validation": validation,
    }


def _format_bytes(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


app = create_app()
