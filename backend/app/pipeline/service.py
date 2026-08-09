"""Stage-cached orchestration for one-directory-per-video jobs."""

from __future__ import annotations

import json
import shlex
import threading
import uuid
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from ..config import SettingsManager
from ..errors import (
    ApprovalRequiredError,
    DependencyUnavailableError,
    InvalidRequestError,
    PipelineError,
    StageBlockedError,
)
from ..models import (
    ApprovalRecord,
    JobStatus,
    MediaKind,
    NormalizationResult,
    PlacementProposal,
    PlacementResolutionResult,
    StageName,
    StageRecord,
    StageRunRequest,
    StageStatus,
    Timeline,
    VideoJob,
    VideoJobUpdate,
    WordTiming,
)
from ..store import JobStore, utc_now
from .ass import generate_ass, validate_ass_bounds
from .ffmpeg import FFmpegAdapter, FFprobeValidationAdapter
from .integrations import (
    KokoroTTSAdapter,
    OpenAIPlacementAdapter,
    WhisperXAlignmentAdapter,
)
from .intake import normalize_and_lint
from .placement import resolve_placements
from .timeline import build_timeline, read_placement_result, validate_timeline_files


STAGE_DEPENDENCIES: dict[StageName, tuple[StageName, ...]] = {
    StageName.INTAKE: (),
    StageName.TTS: (StageName.INTAKE,),
    StageName.ALIGN: (StageName.INTAKE, StageName.TTS),
    StageName.PLACEMENTS: (StageName.INTAKE, StageName.TTS, StageName.ALIGN),
    StageName.SUBTITLES: (StageName.ALIGN,),
    StageName.TIMELINE: (StageName.PLACEMENTS, StageName.SUBTITLES, StageName.TTS),
    StageName.RENDER: (StageName.TIMELINE,),
    StageName.VALIDATE: (StageName.RENDER,),
}

STAGE_OUTPUTS: dict[StageName, tuple[str, ...]] = {
    StageName.INTAKE: ("script.normalized.txt", "intake.json"),
    StageName.TTS: ("voice.wav", "tts.json"),
    StageName.ALIGN: ("words.json", "alignment.json"),
    StageName.PLACEMENTS: ("placements.raw.json", "placements.json"),
    StageName.SUBTITLES: ("subtitles.ass",),
    StageName.TIMELINE: ("timeline.json",),
    StageName.RENDER: ("render/filtergraph.txt", "render/cmd.sh", "final.mp4"),
    StageName.VALIDATE: ("validation.json",),
}
CACHE_DIR = ".stage-cache"


class PipelineService:
    def __init__(self, store: JobStore, settings: SettingsManager) -> None:
        self.store = store
        self.settings = settings
        # Stage runs are serialized process-wide: the box has one small GPU
        # and concurrent TTS/align/render runs would OOM each other.
        self._stage_lock = threading.Lock()

    def intake(self, text: str, *, job_id: str | None = None) -> NormalizationResult:
        lexicon = self.settings.value.data_dir / "lexicon.yml"
        return normalize_and_lint(text, lexicon)

    def intake_job(self, job_id: str, text: str) -> tuple[VideoJob, NormalizationResult]:
        with self.store.lock(job_id):
            job = self.store.get(job_id)
            directory = self.store.job_dir(job_id)
            self._write_text(directory / "script.txt", text)
            result = self.intake(text, job_id=job_id)
            self._write_text(directory / "script.normalized.txt", result.normalized)
            self._write_json(directory / "intake.json", result.model_dump(mode="json"))
            record = self._record(job, StageName.INTAKE)
            record.started_at = utc_now()
            record.finished_at = utc_now()
            record.outputs = list(STAGE_OUTPUTS[StageName.INTAKE])
            record.cache_hit = False
            record.status = StageStatus.BLOCKED if result.hard_fail else StageStatus.SUCCEEDED
            record.error_code = "duration_lint_failed" if result.hard_fail else None
            record.error = "; ".join(issue.message for issue in result.issues if issue.level == "error") or None
            job.status = JobStatus.FAILED if result.hard_fail else JobStatus.CREATED
            job.last_error = record.error
            if not result.hard_fail:
                for downstream in job.stages:
                    if downstream.stage != StageName.INTAKE:
                        downstream.status = StageStatus.PENDING
                        downstream.started_at = None
                        downstream.finished_at = None
                        downstream.outputs = []
                        downstream.cache_hit = False
                        downstream.message = None
                        downstream.error_code = None
                        downstream.error = None
            self.store.save(job)
            return self.store.get(job_id), result

    def run_stage(
        self,
        job_id: str,
        stage: StageName,
        request: StageRunRequest | None = None,
    ) -> tuple[VideoJob, StageRecord]:
        request = request or StageRunRequest()
        with self.store.lock(job_id):
            job = self.store.get(job_id)
            if job.status == JobStatus.REJECTED:
                raise InvalidRequestError("rejected jobs cannot run more stages")
            if request.gameplay_file is not None or request.music_file is not None:
                self.store.update(
                    job_id,
                    VideoJobUpdate(
                        gameplay_file=request.gameplay_file,
                        music_file=request.music_file,
                    ),
                )
            if request.placements is not None:
                self._write_json(
                    self.store.job_dir(job_id) / "placements.raw.json",
                    [proposal.model_dump(mode="json", by_alias=True) for proposal in request.placements],
                )
            with self._stage_lock:
                self._run_with_dependencies(job_id, stage, request, force=request.force, stack=set())
            refreshed = self.store.get(job_id)
            return refreshed, self._record(refreshed, stage)

    def _run_with_dependencies(
        self,
        job_id: str,
        stage: StageName,
        request: StageRunRequest,
        *,
        force: bool,
        stack: set[StageName],
    ) -> None:
        if stage in stack:
            raise PipelineError(f"stage dependency cycle at {stage.value}")
        stack.add(stage)
        for dependency in STAGE_DEPENDENCIES[stage]:
            self._run_with_dependencies(job_id, dependency, request, force=False, stack=stack)
        self._run_one(job_id, stage, request, force=force)
        stack.remove(stage)

    def _run_one(self, job_id: str, stage: StageName, request: StageRunRequest, *, force: bool) -> None:
        job = self.store.get(job_id)
        directory = self.store.job_dir(job_id)
        record = self._record(job, stage)
        if (
            not force
            and record.status not in {StageStatus.FAILED, StageStatus.BLOCKED}
            and self._is_cached(directory, stage, job, request)
        ):
            record.status = StageStatus.CACHED
            record.cache_hit = True
            record.outputs = list(STAGE_OUTPUTS[stage])
            record.message = "all declared outputs are newer than stage inputs"
            record.error = None
            record.error_code = None
            if stage == StageName.VALIDATE:
                job.status = JobStatus.AWAITING_APPROVAL
            self.store.save(job)
            return

        record.status = StageStatus.RUNNING
        record.started_at = utc_now()
        record.finished_at = None
        record.error = None
        record.error_code = None
        record.cache_hit = False
        job.status = JobStatus.RUNNING
        job.last_error = None
        self._clear_stage_cache(directory, stage)
        self._clear_stage_outputs(directory, stage)
        self.store.save(job)
        try:
            message = self._dispatch(job, stage, request)
            self._assert_stage_outputs(directory, stage)
            self._write_stage_cache(directory, stage, job, request)
            record.status = StageStatus.SUCCEEDED
            record.finished_at = utc_now()
            record.outputs = list(STAGE_OUTPUTS[stage])
            record.message = message
            record.error = None
            record.error_code = None
            if stage == StageName.VALIDATE:
                job.status = JobStatus.AWAITING_APPROVAL
            else:
                job.status = JobStatus.CREATED
            self.store.save(job)
        except Exception as exc:
            self._clear_stage_cache(directory, stage)
            self._clear_stage_outputs(directory, stage)
            record.status = StageStatus.BLOCKED if isinstance(exc, StageBlockedError) else StageStatus.FAILED
            record.finished_at = utc_now()
            record.error_code = getattr(exc, "code", "stage_failed")
            record.error = str(exc)
            record.message = None
            job.status = JobStatus.FAILED
            job.last_error = str(exc)
            self.store.save(job)
            raise

    def _dispatch(self, job: VideoJob, stage: StageName, request: StageRunRequest) -> str:
        handlers: dict[StageName, Callable[[VideoJob, StageRunRequest], str]] = {
            StageName.INTAKE: self._stage_intake,
            StageName.TTS: self._stage_tts,
            StageName.ALIGN: self._stage_align,
            StageName.PLACEMENTS: self._stage_placements,
            StageName.SUBTITLES: self._stage_subtitles,
            StageName.TIMELINE: self._stage_timeline,
            StageName.RENDER: self._stage_render,
            StageName.VALIDATE: self._stage_validate,
        }
        return handlers[stage](job, request)

    def _stage_intake(self, job: VideoJob, request: StageRunRequest) -> str:
        directory = self.store.job_dir(job.id)
        script_path = directory / "script.txt"
        try:
            script = script_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise InvalidRequestError(f"cannot read script.txt: {exc}") from exc
        result = self.intake(script, job_id=job.id)
        self._write_text(directory / "script.normalized.txt", result.normalized)
        self._write_json(directory / "intake.json", result.model_dump(mode="json"))
        if result.hard_fail:
            raise StageBlockedError("script intake failed duration lint: " + "; ".join(issue.message for issue in result.issues if issue.level == "error"))
        return f"normalized {result.word_count} words; estimated {result.estimated_duration_s:.1f}s"

    def _stage_tts(self, job: VideoJob, request: StageRunRequest) -> str:
        directory = self.store.job_dir(job.id)
        text = self._read_text(directory / "script.normalized.txt")
        adapter = KokoroTTSAdapter()
        output = directory / "voice.wav"
        adapter.synthesize(
            text,
            output_path=output,
            voice=job.kokoro_voice,
            speed=job.kokoro_speed,
            language=self.settings.value.kokoro_language,
        )
        duration = _wav_duration(output)
        self._write_json(
            directory / "tts.json",
            {
                "voice": job.kokoro_voice,
                "speed": job.kokoro_speed,
                "language": self.settings.value.kokoro_language,
                "sample_rate": KokoroTTSAdapter.sample_rate,
                "duration_s": duration,
            },
        )
        return f"generated {duration:.3f}s of Kokoro audio"

    def _stage_align(self, job: VideoJob, request: StageRunRequest) -> str:
        directory = self.store.job_dir(job.id)
        script = self._read_text(directory / "script.normalized.txt")
        adapter = WhisperXAlignmentAdapter(
            model_name=self.settings.value.whisperx_model,
            device=self.settings.value.whisperx_device,
            compute_type=self.settings.value.whisperx_compute_type,
            language=self.settings.value.whisperx_language,
            confidence_threshold=self.settings.value.alignment_confidence_threshold,
        )
        report = adapter.align(script, directory / "voice.wav")
        self._write_json(
            directory / "words.json",
            [word.model_dump(mode="json", by_alias=True) for word in report.words],
        )
        self._write_json(
            directory / "alignment.json",
            {
                "language": report.language,
                "flagged_indices": report.flagged_indices,
                "flagged_ratio": report.flagged_ratio,
                "confidence_threshold": self.settings.value.alignment_confidence_threshold,
            },
        )
        return f"aligned {len(report.words)} words; flagged ratio {report.flagged_ratio:.1%}"

    def _stage_placements(self, job: VideoJob, request: StageRunRequest) -> str:
        directory = self.store.job_dir(job.id)
        raw_path = directory / "placements.raw.json"
        if not raw_path.exists():
            if not (request.use_opencode_zen or request.use_openai):
                raise InvalidRequestError(
                    "placements stage requires manual placements or use_opencode_zen=true with an OpenCode Zen adapter configured"
                )
            try:
                script = self._read_text(directory / "script.normalized.txt")
                words = [
                    WordTiming.model_validate(item)
                    for item in json.loads((directory / "words.json").read_text(encoding="utf-8"))
                ]
                api_key = self.settings.value.openai_api_key
                proposals = OpenAIPlacementAdapter(
                    base_url=self.settings.value.openai_base_url,
                    api_key=api_key.get_secret_value() if api_key else None,
                    model=self.settings.value.openai_model,
                    timeout_s=self.settings.value.openai_timeout_s,
                ).suggest(
                    script=script,
                    words=words,
                    assets=self.store.list_media(kind=MediaKind.OVERLAY),
                )
                self._write_json(
                    raw_path,
                    [proposal.model_dump(mode="json", by_alias=True) for proposal in proposals],
                )
            except (OSError, json.JSONDecodeError, ValueError) as exc:
                raise InvalidRequestError(f"invalid placement/alignment input: {exc}") from exc
        try:
            raw = json.loads(raw_path.read_text(encoding="utf-8"))
            proposals = [PlacementProposal.model_validate(item) for item in raw]
            words = [WordTiming.model_validate(item) for item in json.loads((directory / "words.json").read_text(encoding="utf-8"))]
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise InvalidRequestError(f"invalid placement/alignment input: {exc}") from exc
        duration = self._voice_duration(job.id)
        result = resolve_placements(proposals, words, voice_duration_s=duration)
        for proposal in result.placements:
            self.store.resolve_media_reference(proposal.asset_id, expected_kind=MediaKind.OVERLAY)
        self._write_json(directory / "placements.json", result.model_dump(mode="json", by_alias=True))
        return f"resolved {len(result.placements)} placements; {len(result.dropped)} dropped"

    def _stage_subtitles(self, job: VideoJob, request: StageRunRequest) -> str:
        directory = self.store.job_dir(job.id)
        try:
            raw_words = json.loads((directory / "words.json").read_text(encoding="utf-8"))
            words = [WordTiming.model_validate(item) for item in raw_words]
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise InvalidRequestError(f"invalid words.json: {exc}") from exc
        ass = generate_ass(words, mode=job.karaoke_mode)
        errors = validate_ass_bounds(ass)
        if errors:
            raise InvalidRequestError("generated ASS failed bounds validation: " + "; ".join(errors))
        self._write_text(directory / "subtitles.ass", ass)
        return f"generated {len(words)} word timings as ASS karaoke cards"

    def _stage_timeline(self, job: VideoJob, request: StageRunRequest) -> str:
        directory = self.store.job_dir(job.id)
        placements = read_placement_result(directory / "placements.json")
        duration = self._voice_duration(job.id)
        gameplay = (
            self.store.resolve_media_reference(job.gameplay_file, expected_kind=MediaKind.GAMEPLAY)
            if job.gameplay_file
            else None
        )
        music = (
            self.store.resolve_media_reference(job.music_file, expected_kind=MediaKind.MUSIC)
            if job.music_file
            else None
        )
        timeline = build_timeline(
            job_dir=directory,
            gameplay_file=str(gameplay) if gameplay else None,
            music_file=str(music) if music else None,
            voice_duration_s=duration,
            placements=placements,
        )
        timeline = self._resolve_timeline_assets(timeline, directory)
        file_errors = validate_timeline_files(timeline)
        if file_errors:
            raise InvalidRequestError("timeline inputs are invalid: " + "; ".join(file_errors))
        self._write_json(directory / "timeline.json", timeline.model_dump(mode="json", by_alias=True))
        return f"assembled timeline v{timeline.version} with {len(timeline.tracks.overlays)} overlays"

    def _stage_render(self, job: VideoJob, request: StageRunRequest) -> str:
        directory = self.store.job_dir(job.id)
        try:
            timeline = Timeline.model_validate(json.loads((directory / "timeline.json").read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise InvalidRequestError(f"invalid timeline.json: {exc}") from exc
        file_errors = validate_timeline_files(timeline)
        if file_errors:
            raise InvalidRequestError("render inputs are invalid: " + "; ".join(file_errors))
        duration = timeline.duration_s or (self._voice_duration(job.id) + 0.3)
        result = FFmpegAdapter(
            self.settings.value.ffmpeg_bin,
            self.settings.value.ffprobe_bin,
        ).render(
            timeline,
            output_path=directory / "final.mp4",
            duration_s=duration,
            timeout_s=self.settings.value.stage_timeout_s,
            draft=request.draft,
            segment_from_s=request.segment_from_s,
            segment_to_s=request.segment_to_s,
        )
        self._write_text(directory / "render" / "filtergraph.txt", result.filtergraph)
        self._write_text(directory / "render" / "cmd.sh", "#!/usr/bin/env sh\nset -eu\n" + shlex.join(result.command) + "\n")
        (directory / "render" / "cmd.sh").chmod(0o750)
        return f"rendered {duration:.3f}s to final.mp4"

    def _stage_validate(self, job: VideoJob, request: StageRunRequest) -> str:
        directory = self.store.job_dir(job.id)
        try:
            duration = Timeline.model_validate(
                json.loads((directory / "timeline.json").read_text(encoding="utf-8"))
            ).duration_s
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise InvalidRequestError(f"invalid timeline.json: {exc}") from exc
        if duration is None:
            raise InvalidRequestError("timeline duration is required before validation")
        result = FFprobeValidationAdapter(
            self.settings.value.ffmpeg_bin,
            self.settings.value.ffprobe_bin,
        ).validate(
            directory / "final.mp4",
            expected_duration_s=duration,
            subtitle_path=directory / "subtitles.ass",
            timeout_s=self.settings.value.stage_timeout_s,
        )
        self._write_json(directory / "validation.json", result.model_dump(mode="json"))
        if not result.passed:
            raise StageBlockedError("validation gate failed: " + "; ".join(result.errors))
        return "validation gate passed"

    def approve(self, job_id: str, *, decided_by: str | None, comment: str | None) -> tuple[VideoJob, ApprovalRecord]:
        with self.store.lock(job_id):
            job = self.store.get(job_id)
            validation_path = self.store.job_dir(job_id) / "validation.json"
            if job.status != JobStatus.AWAITING_APPROVAL or not _validation_passed(validation_path):
                raise ApprovalRequiredError(
                    "job must pass the validation stage before it can be approved"
                )
            record = ApprovalRecord(
                decision="approved",
                decided_at=utc_now(),
                decided_by=decided_by,
                comment=comment,
            )
            job.status = JobStatus.APPROVED
            job.approval = record
            job.last_error = None
            directory = self.store.job_dir(job_id)
            self._write_json(directory / "approval.json", record.model_dump(mode="json"))
            self._write_text(directory / "approval.md", _approval_markdown(record))
            self.store.save(job)
            return self.store.get(job_id), record

    def reject(self, job_id: str, *, decided_by: str | None, comment: str | None) -> tuple[VideoJob, ApprovalRecord]:
        with self.store.lock(job_id):
            job = self.store.get(job_id)
            validation_path = self.store.job_dir(job_id) / "validation.json"
            if job.status != JobStatus.AWAITING_APPROVAL or not _validation_passed(validation_path):
                raise ApprovalRequiredError(
                    "job must pass the validation stage before it can be rejected"
                )
            record = ApprovalRecord(
                decision="rejected",
                decided_at=utc_now(),
                decided_by=decided_by,
                comment=comment,
            )
            job.status = JobStatus.REJECTED
            job.approval = record
            job.last_error = comment or "rejected by reviewer"
            directory = self.store.job_dir(job_id)
            self._write_json(directory / "approval.json", record.model_dump(mode="json"))
            self._write_text(directory / "approval.md", _approval_markdown(record))
            self.store.save(job)
            return self.store.get(job_id), record

    def revise(self, job_id: str, *, comment: str | None) -> VideoJob:
        """Reset generated artifacts so a revised job cannot reuse stale media."""

        with self.store.lock(job_id):
            job = self.store.get(job_id)
            if job.status == JobStatus.RUNNING:
                raise InvalidRequestError("running jobs cannot be revised")
            directory = self.store.job_dir(job_id)
            for stage in StageName:
                record = self._record(job, stage)
                record.status = StageStatus.PENDING
                record.started_at = None
                record.finished_at = None
                record.outputs = []
                record.cache_hit = False
                record.message = None
                record.error_code = None
                record.error = None
                self._clear_stage_cache(directory, stage)
                self._clear_stage_outputs(directory, stage)
            (directory / "placements.raw.json").unlink(missing_ok=True)
            job.status = JobStatus.CREATED
            job.approval = None
            job.last_error = comment or "revision requested by operator"
            self.store.save(job)
            return self.store.get(job_id)

    def _record(self, job: VideoJob, stage: StageName) -> StageRecord:
        for record in job.stages:
            if record.stage == stage:
                return record
        record = StageRecord(stage=stage)
        job.stages.append(record)
        return record

    def _is_cached(
        self,
        directory: Path,
        stage: StageName,
        job: VideoJob,
        request: StageRunRequest,
    ) -> bool:
        outputs = [directory / output for output in STAGE_OUTPUTS[stage]]
        if not all(path.exists() and path.is_file() and path.stat().st_size > 0 for path in outputs):
            return False
        inputs = self._stage_inputs(directory, stage)
        if not inputs or not all(path.exists() and path.is_file() for path in inputs):
            return False
        cache_path = self._stage_cache_path(directory, stage)
        try:
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
            expected_inputs = self._path_signatures(inputs)
            expected_outputs = self._path_signatures(outputs)
            return (
                cache.get("options") == self._stage_cache_options(job, stage, request)
                and cache.get("inputs") == expected_inputs
                and cache.get("outputs") == expected_outputs
            )
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            return False

    def _write_stage_cache(
        self,
        directory: Path,
        stage: StageName,
        job: VideoJob,
        request: StageRunRequest,
    ) -> None:
        outputs = [directory / output for output in STAGE_OUTPUTS[stage]]
        inputs = self._stage_inputs(directory, stage)
        self._write_json(
            self._stage_cache_path(directory, stage),
            {
                "stage": stage.value,
                "options": self._stage_cache_options(job, stage, request),
                "inputs": self._path_signatures(inputs),
                "outputs": self._path_signatures(outputs),
            },
        )

    @staticmethod
    def _stage_cache_path(directory: Path, stage: StageName) -> Path:
        return directory / CACHE_DIR / f"{stage.value}.json"

    def _stage_cache_options(
        self,
        job: VideoJob,
        stage: StageName,
        request: StageRunRequest,
    ) -> dict[str, object]:
        settings = self.settings.value
        options: dict[str, object] = {
            "job": {
                "gameplay_file": job.gameplay_file,
                "music_file": job.music_file,
                "kokoro_voice": job.kokoro_voice,
                "kokoro_speed": job.kokoro_speed,
                "karaoke_mode": job.karaoke_mode.value,
            },
            "settings": {
                "kokoro_language": settings.kokoro_language,
                "whisperx_model": settings.whisperx_model,
                "whisperx_device": settings.whisperx_device,
                "whisperx_compute_type": settings.whisperx_compute_type,
                "whisperx_language": settings.whisperx_language,
                "alignment_confidence_threshold": settings.alignment_confidence_threshold,
                "ffmpeg_bin": settings.ffmpeg_bin,
                "ffprobe_bin": settings.ffprobe_bin,
            },
        }
        request_values = request.model_dump(exclude={"force"}, mode="json", by_alias=True)
        if stage in {StageName.PLACEMENTS, StageName.RENDER}:
            options["request"] = request_values
        if stage == StageName.INTAKE:
            lexicon = settings.data_dir / "lexicon.yml"
            options["lexicon"] = self._path_signatures([lexicon])
        return options

    @staticmethod
    def _path_signatures(paths: list[Path]) -> list[dict[str, object]]:
        signatures: list[dict[str, object]] = []
        for path in paths:
            resolved = path.expanduser().resolve()
            if not resolved.exists():
                signatures.append({"path": str(resolved), "exists": False})
                continue
            stat = resolved.stat()
            signatures.append(
                {
                    "path": str(resolved),
                    "exists": True,
                    "size": stat.st_size,
                    "mtime_ns": stat.st_mtime_ns,
                }
            )
        return signatures

    @staticmethod
    def _clear_stage_cache(directory: Path, stage: StageName) -> None:
        (directory / CACHE_DIR / f"{stage.value}.json").unlink(missing_ok=True)

    @staticmethod
    def _clear_stage_outputs(directory: Path, stage: StageName) -> None:
        for output in STAGE_OUTPUTS[stage]:
            # placements.raw.json is a caller/provider input and must survive a
            # rerun of the resolver; placements.json is the generated output.
            if stage == StageName.PLACEMENTS and output == "placements.raw.json":
                continue
            (directory / output).unlink(missing_ok=True)

    @staticmethod
    def _assert_stage_outputs(directory: Path, stage: StageName) -> None:
        missing = [
            output
            for output in STAGE_OUTPUTS[stage]
            if not (directory / output).is_file() or (directory / output).stat().st_size <= 0
        ]
        if missing:
            raise PipelineError(
                f"stage {stage.value} did not produce declared outputs: {', '.join(missing)}",
                code="stage_output_missing",
            )

    def _stage_inputs(self, directory: Path, stage: StageName) -> list[Path]:
        common: dict[StageName, list[Path]] = {
            StageName.INTAKE: [directory / "script.txt"],
            StageName.TTS: [directory / "script.normalized.txt", directory / "job.config.json"],
            StageName.ALIGN: [directory / "script.normalized.txt", directory / "voice.wav"],
            StageName.PLACEMENTS: [directory / "script.normalized.txt", directory / "words.json", directory / "placements.raw.json"],
            StageName.SUBTITLES: [directory / "words.json"],
            StageName.TIMELINE: [directory / "placements.json", directory / "subtitles.ass", directory / "voice.wav", directory / "job.config.json"],
            StageName.RENDER: [directory / "timeline.json", directory / "job.config.json"],
            StageName.VALIDATE: [directory / "final.mp4", directory / "subtitles.ass"],
        }
        inputs = list(common[stage])
        if stage == StageName.RENDER and (directory / "timeline.json").exists():
            try:
                timeline = Timeline.model_validate(
                    json.loads((directory / "timeline.json").read_text(encoding="utf-8"))
                )
                referenced = [
                    timeline.tracks.gameplay.clip,
                    timeline.tracks.voice.file,
                    timeline.tracks.subtitles.ass,
                ]
                if timeline.tracks.music:
                    referenced.append(timeline.tracks.music.file)
                referenced.extend(overlay.asset for overlay in timeline.tracks.overlays)
                inputs.extend(Path(reference) for reference in referenced)
            except (OSError, json.JSONDecodeError, ValueError):
                pass
        return inputs

    def _voice_duration(self, job_id: str) -> float:
        directory = self.store.job_dir(job_id)
        metadata_path = directory / "tts.json"
        if metadata_path.exists():
            try:
                value = json.loads(metadata_path.read_text(encoding="utf-8")).get("duration_s")
                if value is not None:
                    return float(value)
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                pass
        return _wav_duration(directory / "voice.wav")

    def _resolve_timeline_assets(self, timeline: Timeline, directory: Path) -> Timeline:
        overlays = []
        for overlay in timeline.tracks.overlays:
            resolved = self.store.resolve_media_reference(
                overlay.asset,
                expected_kind=MediaKind.OVERLAY,
            )
            overlays.append(overlay.model_copy(update={"asset": str(resolved)}))
        return timeline.model_copy(
            update={
                "tracks": timeline.tracks.model_copy(update={"overlays": overlays}),
            }
        )

    @staticmethod
    def _read_text(path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8")
        except OSError as exc:
            raise InvalidRequestError(f"cannot read {path.name}: {exc}") from exc

    @staticmethod
    def _write_text(path: Path, value: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            temporary.write_text(value, encoding="utf-8")
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _write_json(path: Path, value: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            temporary.write_text(
                json.dumps(value, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


def _wav_duration(path: Path) -> float:
    try:
        with wave.open(str(path), "rb") as wav:
            rate = wav.getframerate()
            return wav.getnframes() / rate if rate else 0.0
    except (OSError, wave.Error) as exc:
        raise InvalidRequestError(f"cannot read WAV duration from {path.name}: {exc}") from exc


def _approval_markdown(record: ApprovalRecord) -> str:
    lines = [f"# {record.decision.title()}", "", f"- Decided at: {record.decided_at.isoformat()}"]
    if record.decided_by:
        lines.append(f"- Decided by: {record.decided_by}")
    if record.comment:
        lines.extend(["", record.comment])
    return "\n".join(lines) + "\n"


def _validation_passed(path: Path) -> bool:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw.get("passed") is True
    except (OSError, json.JSONDecodeError, AttributeError):
        return False
