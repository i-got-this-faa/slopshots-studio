"""File-backed job state and artifact storage."""

from __future__ import annotations

import json
import mimetypes
import os
import re
import shutil
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from .errors import ConflictError, InvalidRequestError, NotFoundError
from .models import (
    AppSettings,
    ArtifactInfo,
    JobStatus,
    MediaAsset,
    MediaKind,
    MediaRegisterRequest,
    StageName,
    StageRecord,
    StageStatus,
    VideoJob,
    VideoJobCreate,
    VideoJobUpdate,
    model_to_jsonable,
)


ALL_STAGES = [
    StageName.INTAKE,
    StageName.TTS,
    StageName.ALIGN,
    StageName.PLACEMENTS,
    StageName.SUBTITLES,
    StageName.TIMELINE,
    StageName.RENDER,
    StageName.VALIDATE,
]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value[:80] or "untitled"


class JobStore:
    """Persist one directory per job, with atomic JSON state writes."""

    def __init__(
        self,
        data_dir: Path,
        *,
        media_input_roots: list[Path] | None = None,
        max_upload_bytes: int = 2 * 1024 * 1024 * 1024,
    ) -> None:
        self.data_dir = data_dir.expanduser().resolve()
        self.videos_dir = self.data_dir / "videos"
        self.media_dir = self.data_dir / "assets"
        self.media_index_path = self.data_dir / "media-index.json"
        self.media_input_roots = [path.expanduser().resolve() for path in (media_input_roots or [])]
        self.max_upload_bytes = max_upload_bytes
        self._lock = threading.RLock()
        self._job_locks: dict[str, threading.RLock] = {}
        # Media index is re-read on every lookup; cache it keyed on the
        # file signature so per-overlay resolution doesn't re-parse the
        # whole library each time.
        self._media_index_cache: tuple[tuple[int, int], dict[str, dict[str, object]]] | None = None
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.videos_dir.mkdir(parents=True, exist_ok=True)
        self.media_dir.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def lock(self, job_id: str) -> Iterator[None]:
        with self._lock:
            lock = self._job_locks.setdefault(job_id, threading.RLock())
        with lock:
            yield

    def _state_path(self, job_id: str) -> Path:
        return self.job_dir(job_id) / "job.json"

    def job_dir(self, job_id: str) -> Path:
        if not re.fullmatch(r"[a-f0-9-]{8,64}", job_id):
            raise NotFoundError("invalid job id")
        matches = list(self.videos_dir.glob(f"*-{job_id[:8]}"))
        if len(matches) == 1 and (matches[0] / "job.json").exists():
            return matches[0]
        direct = self.videos_dir / job_id
        if (direct / "job.json").exists():
            return direct
        raise NotFoundError(f"video job '{job_id}' was not found")

    def create(self, request: VideoJobCreate, settings: AppSettings) -> VideoJob:
        with self._lock:
            job_id = uuid.uuid4().hex
            directory = self.videos_dir / f"{slugify(request.name)}-{job_id[:8]}"
            directory.mkdir(parents=True, exist_ok=False)
            now = utc_now()
            effective_voice = request.kokoro_voice or settings.kokoro_voice
            effective_speed = request.kokoro_speed or settings.kokoro_speed
            effective_mode = request.karaoke_mode or settings.karaoke_mode
            job = VideoJob(
                id=job_id,
                name=request.name.strip(),
                status=JobStatus.CREATED,
                created_at=now,
                updated_at=now,
                directory=str(directory),
                gameplay_file=request.gameplay_file,
                music_file=request.music_file,
                kokoro_voice=effective_voice,
                kokoro_speed=effective_speed,
                karaoke_mode=effective_mode,
                stages=[StageRecord(stage=stage) for stage in ALL_STAGES],
            )
            _atomic_write_text(directory / "script.txt", request.script)
            _atomic_write_json(
                directory / "job.config.json",
                {
                    "gameplay_file": request.gameplay_file,
                    "music_file": request.music_file,
                    "kokoro_voice": effective_voice,
                    "kokoro_speed": effective_speed,
                    "karaoke_mode": effective_mode.value,
                },
            )
            # Bootstrap the state file directly.  ``save`` intentionally
            # resolves an existing job through ``job_dir``; during creation
            # there is no job.json yet for that lookup to find.
            _atomic_write_json(directory / "job.json", model_to_jsonable(job))
            return job

    def get(self, job_id: str) -> VideoJob:
        state_path = self._state_path(job_id)
        try:
            raw = json.loads(state_path.read_text(encoding="utf-8"))
            job = VideoJob.model_validate(raw)
        except FileNotFoundError as exc:
            raise NotFoundError(f"video job '{job_id}' was not found") from exc
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise InvalidRequestError(f"job state is unreadable for '{job_id}': {exc}") from exc
        job.artifacts = self.list_artifacts(job_id)
        return job

    def save(self, job: VideoJob) -> None:
        job.updated_at = utc_now()
        _atomic_write_json(self._state_path(job.id), model_to_jsonable(job))

    def update(self, job_id: str, update: VideoJobUpdate) -> VideoJob:
        with self.lock(job_id):
            job = self.get(job_id)
            values = update.model_dump(exclude_unset=True)
            changed = False
            for key, value in values.items():
                if value is not None:
                    setattr(job, key, value)
                    changed = True
            if changed:
                for record in job.stages:
                    record.status = StageStatus.PENDING
                    record.started_at = None
                    record.finished_at = None
                    record.outputs = []
                    record.cache_hit = False
                    record.message = None
                    record.error_code = None
                    record.error = None
                job.approval = None
                job.last_error = None
                if job.status in {
                    JobStatus.APPROVED,
                    JobStatus.REJECTED,
                    JobStatus.AWAITING_APPROVAL,
                }:
                    job.status = JobStatus.CREATED
            _atomic_write_json(
                self.job_dir(job_id) / "job.config.json",
                {
                    "gameplay_file": job.gameplay_file,
                    "music_file": job.music_file,
                    "kokoro_voice": job.kokoro_voice,
                    "kokoro_speed": job.kokoro_speed,
                    "karaoke_mode": job.karaoke_mode.value,
                },
            )
            self.save(job)
            return self.get(job_id)

    def list(self) -> list[VideoJob]:
        jobs: list[VideoJob] = []
        for state_path in sorted(self.videos_dir.glob("*/job.json"), key=lambda path: path.stat().st_mtime, reverse=True):
            try:
                raw = json.loads(state_path.read_text(encoding="utf-8"))
                job = VideoJob.model_validate(raw)
                job.artifacts = self.list_artifacts(job.id)
            except (OSError, json.JSONDecodeError, ValueError, NotFoundError, InvalidRequestError):
                continue
            jobs.append(job)
        return jobs

    def read_config(self, job_id: str) -> dict[str, object]:
        path = self.job_dir(job_id) / "job.config.json"
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise InvalidRequestError(f"job config is unreadable: {exc}") from exc

    def list_media(self, *, kind: MediaKind | None = None) -> list[MediaAsset]:
        """Return registered media whose managed files are still present."""

        with self._lock:
            entries = self._read_media_index()
            assets: list[MediaAsset] = []
            for entry in entries.values():
                try:
                    asset = MediaAsset.model_validate(entry["asset"])
                    path = self._stored_media_path(entry["path"])
                except (KeyError, TypeError, ValueError) as exc:
                    raise InvalidRequestError(f"media index contains an invalid entry: {exc}") from exc
                if kind is not None and asset.kind != kind:
                    continue
                if path.is_symlink() or not path.is_file():
                    continue
                assets.append(asset)
            return sorted(assets, key=lambda asset: asset.id)

    def get_media(self, asset_id: str) -> MediaAsset:
        with self._lock:
            entry = self._read_media_index().get(asset_id)
            if entry is None:
                raise NotFoundError(f"media asset '{asset_id}' was not found")
            try:
                asset = MediaAsset.model_validate(entry["asset"])
                path = self._stored_media_path(entry["path"])
            except (KeyError, TypeError, ValueError) as exc:
                raise InvalidRequestError(f"media asset '{asset_id}' is invalid: {exc}") from exc
            if path.is_symlink() or not path.is_file():
                raise NotFoundError(f"media asset '{asset_id}' is missing from managed storage")
            return asset

    def resolve_media_reference(
        self,
        reference: str,
        *,
        expected_kind: MediaKind,
    ) -> Path:
        """Resolve an asset ID or explicitly allowed source path safely.

        Registered assets are always served from the managed assets directory.
        A raw path is accepted only when it is a regular, non-symlink file under
        one of the configured input roots.  This keeps legacy path references
        useful without allowing a job request to read arbitrary host files.
        """

        with self._lock:
            entries = self._read_media_index()
            entry = entries.get(reference)
            if entry is not None:
                try:
                    asset = MediaAsset.model_validate(entry["asset"])
                    path = self._stored_media_path(entry["path"])
                except (KeyError, TypeError, ValueError) as exc:
                    raise InvalidRequestError(f"media asset '{reference}' is invalid: {exc}") from exc
                if asset.kind != expected_kind:
                    raise InvalidRequestError(
                        f"media asset '{reference}' is {asset.kind.value}, expected {expected_kind.value}"
                    )
                if path.is_symlink() or not path.is_file():
                    raise InvalidRequestError(f"media asset '{reference}' is missing from managed storage")
                return path

        candidate = Path(reference).expanduser()
        if not candidate.is_absolute():
            candidate = Path.cwd() / candidate
        try:
            resolved = candidate.resolve(strict=True)
        except OSError as exc:
            raise InvalidRequestError(f"media file '{reference}' cannot be resolved: {exc}") from exc
        if candidate.is_symlink() or not resolved.is_file():
            raise InvalidRequestError(f"media file '{reference}' must be a regular, non-symlink file")
        if not any(_is_within(resolved, root) for root in self.media_input_roots):
            raise InvalidRequestError(
                f"media file '{reference}' is outside configured media input roots; register or upload it first"
            )
        self._validate_media_type(resolved.name, expected_kind, None)
        self._validate_media_signature(resolved, expected_kind)
        return resolved

    def register_media(self, request: MediaRegisterRequest) -> MediaAsset:
        """Copy an allowed external media file into managed storage."""

        source = Path(request.path).expanduser()
        if not source.is_absolute():
            source = Path.cwd() / source
        try:
            resolved = source.resolve(strict=True)
        except OSError as exc:
            raise InvalidRequestError(f"media path cannot be resolved: {exc}") from exc
        if source.is_symlink() or not resolved.is_file():
            raise InvalidRequestError("registered media must be a regular, non-symlink file")
        if not any(_is_within(resolved, root) for root in self.media_input_roots):
            raise InvalidRequestError(
                "registered media must be inside one of the configured media input roots"
            )
        return self._store_media(
            resolved,
            asset_id=request.id,
            kind=request.kind,
            source=request.source,
            confirmed=request.confirmed,
            description=request.description,
            tags=request.tags,
            filename=resolved.name,
            declared_media_type=None,
        )

    def register_uploaded_media(
        self,
        source_path: Path,
        *,
        asset_id: str,
        kind: MediaKind,
        source: str,
        confirmed: bool,
        description: str,
        tags: list[str],
        filename: str,
        declared_media_type: str | None,
    ) -> MediaAsset:
        """Move a bounded temporary upload into managed storage."""

        return self._store_media(
            source_path,
            asset_id=asset_id,
            kind=kind,
            source=source,
            confirmed=confirmed,
            description=description,
            tags=tags,
            filename=filename,
            declared_media_type=declared_media_type,
        )

    def _store_media(
        self,
        source_path: Path,
        *,
        asset_id: str,
        kind: MediaKind,
        source: str,
        confirmed: bool,
        description: str,
        tags: list[str],
        filename: str,
        declared_media_type: str | None,
    ) -> MediaAsset:
        from .models import MediaSource, _validate_asset_identifier

        try:
            safe_id = _validate_asset_identifier(asset_id)
            source_enum = MediaSource(source)
        except ValueError as exc:
            raise InvalidRequestError(f"invalid media registration: {exc}") from exc
        if source_path.is_symlink() or not source_path.is_file():
            raise InvalidRequestError("uploaded media must be a regular, non-symlink file")
        try:
            size = source_path.stat().st_size
        except OSError as exc:
            raise InvalidRequestError(f"cannot stat uploaded media: {exc}") from exc
        if size <= 0:
            raise InvalidRequestError("uploaded media cannot be empty")
        if size > self.max_upload_bytes:
            raise InvalidRequestError(
                f"uploaded media is {size} bytes; maximum is {self.max_upload_bytes} bytes"
            )
        clean_filename = Path(filename or source_path.name).name
        if not clean_filename or clean_filename in {".", ".."} or "\x00" in clean_filename:
            raise InvalidRequestError("uploaded media filename is invalid")
        media_type = self._validate_media_type(clean_filename, kind, declared_media_type)
        self._validate_media_signature(source_path, kind)
        suffix = Path(clean_filename).suffix.lower()
        destination = self.media_dir / safe_id
        if not suffix:
            suffix = _extension_for_media_type(media_type)
            destination = destination.with_suffix(suffix)
        destination = destination.resolve()
        if not _is_within(destination, self.media_dir.resolve()):
            raise InvalidRequestError("media asset destination is outside managed storage")

        with self._lock:
            entries = self._read_media_index()
            if safe_id in entries:
                raise ConflictError(f"media asset '{safe_id}' is already registered")
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists() or destination.is_symlink():
                raise ConflictError(f"media asset destination '{safe_id}' already exists")
            temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
            try:
                shutil.copyfile(source_path, temporary)
                os.replace(temporary, destination)
                asset = MediaAsset(
                    id=safe_id,
                    kind=kind,
                    filename=clean_filename,
                    media_type=media_type,
                    size_bytes=size,
                    created_at=utc_now(),
                    source=source_enum,
                    confirmed=confirmed,
                    description=description,
                    tags=tags,
                )
                entries[safe_id] = {
                    "asset": asset.model_dump(mode="json"),
                    "path": destination.relative_to(self.data_dir).as_posix(),
                }
                _atomic_write_json(self.media_index_path, {"assets": entries})
            except (OSError, ValueError) as exc:
                try:
                    temporary.unlink(missing_ok=True)
                    destination.unlink(missing_ok=True)
                except OSError:
                    pass
                raise InvalidRequestError(f"could not store media asset '{safe_id}': {exc}") from exc
            return asset

    def _read_media_index(self) -> dict[str, dict[str, object]]:
        try:
            stat = self.media_index_path.stat()
        except OSError:
            return {}
        signature = (stat.st_mtime_ns, stat.st_size)
        if self._media_index_cache is not None and self._media_index_cache[0] == signature:
            # Copy so callers registering media cannot mutate cached state.
            return dict(self._media_index_cache[1])
        try:
            raw = json.loads(self.media_index_path.read_text(encoding="utf-8"))
            entries = raw.get("assets", {}) if isinstance(raw, dict) else None
            if not isinstance(entries, dict):
                raise ValueError("assets must be an object")
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise InvalidRequestError(f"media index is unreadable: {exc}") from exc
        self._media_index_cache = (signature, entries)
        return dict(entries)

    def _stored_media_path(self, relative_path: object) -> Path:
        if not isinstance(relative_path, str):
            raise ValueError("stored media path must be a string")
        path = (self.data_dir / relative_path).resolve()
        if not _is_within(path, self.media_dir.resolve()):
            raise ValueError("stored media path is outside managed storage")
        return path

    @staticmethod
    def _validate_media_type(
        filename: str,
        kind: MediaKind,
        declared_media_type: str | None,
    ) -> str:
        guessed = mimetypes.guess_type(filename)[0]
        media_type = (declared_media_type or guessed or "").lower().split(";", 1)[0].strip()
        allowed_extensions = {
            MediaKind.GAMEPLAY: {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi", ".mpeg", ".mpg"},
            MediaKind.MUSIC: {".wav", ".mp3", ".m4a", ".aac", ".ogg", ".opus", ".flac"},
            MediaKind.OVERLAY: {".png", ".jpg", ".jpeg", ".webp", ".gif"},
        }
        suffix = Path(filename).suffix.lower()
        if suffix not in allowed_extensions[kind]:
            raise InvalidRequestError(
                f"{kind.value} media must use a supported media extension; got '{suffix or 'none'}'"
            )
        expected_prefix = {
            MediaKind.GAMEPLAY: "video/",
            MediaKind.MUSIC: "audio/",
            MediaKind.OVERLAY: "image/",
        }[kind]
        if not media_type or not media_type.startswith(expected_prefix):
            media_type = {
                MediaKind.GAMEPLAY: "video/mp4",
                MediaKind.MUSIC: "audio/mpeg",
                MediaKind.OVERLAY: "image/png",
            }[kind]
        return media_type

    @staticmethod
    def _validate_media_signature(path: Path, kind: MediaKind) -> None:
        try:
            with path.open("rb") as handle:
                header = handle.read(32)
        except OSError as exc:
            raise InvalidRequestError(f"cannot read uploaded media: {exc}") from exc
        is_mp4_family = len(header) >= 8 and header[4:8] == b"ftyp"
        is_ebml = header.startswith(b"\x1a\x45\xdf\xa3")
        is_riff_video = header.startswith(b"RIFF") and header[8:12] in {b"AVI ", b"AVIX"}
        is_audio = (
            (header.startswith(b"RIFF") and header[8:12] == b"WAVE")
            or header.startswith((b"ID3", b"OggS", b"fLaC"))
            or is_mp4_family
        )
        is_image = (
            header.startswith(b"\x89PNG\r\n\x1a\n")
            or header.startswith(b"\xff\xd8\xff")
            or header.startswith((b"GIF87a", b"GIF89a"))
            or (header.startswith(b"RIFF") and header[8:12] == b"WEBP")
        )
        valid = {
            MediaKind.GAMEPLAY: is_mp4_family or is_ebml or is_riff_video,
            MediaKind.MUSIC: is_audio,
            MediaKind.OVERLAY: is_image,
        }[kind]
        if not valid:
            raise InvalidRequestError(
                f"uploaded file does not have a recognized {kind.value} media signature"
            )

    def list_artifacts(self, job_id: str) -> list[ArtifactInfo]:
        directory = self.job_dir(job_id)
        artifacts: list[ArtifactInfo] = []
        for path in sorted(directory.rglob("*")):
            if not path.is_file() or path.is_symlink() or path.name == "job.json":
                continue
            relative = path.relative_to(directory).as_posix()
            media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            artifacts.append(
                ArtifactInfo(
                    name=relative,
                    exists=True,
                    size_bytes=path.stat().st_size,
                    media_type=media_type,
                )
            )
        return artifacts

    def resolve_artifact(self, job_id: str, artifact_path: str) -> Path:
        directory = self.job_dir(job_id).resolve()
        requested = (directory / artifact_path).resolve()
        if directory not in requested.parents or requested == directory:
            raise NotFoundError("artifact path is outside the video job")
        if requested.is_symlink() or not requested.is_file():
            raise NotFoundError(f"artifact '{artifact_path}' was not found")
        return requested


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_write_json(path: Path, value: object) -> None:
    _atomic_write_text(path, json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _extension_for_media_type(media_type: str) -> str:
    return {
        "video/mp4": ".mp4",
        "audio/mpeg": ".mp3",
        "image/png": ".png",
    }.get(media_type, ".bin")
