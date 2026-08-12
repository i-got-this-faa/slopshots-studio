"""Pydantic contracts used by the SlopShots API and pipeline.

The models deliberately mirror the file contracts in ``docs/12-orchestration-state.md``.
They are also used at the boundaries of the integrations so malformed external
data cannot silently become a timeline or a render command.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
    SecretStr,
)


class SlopShotsModel(BaseModel):
    """Base model with predictable JSON behavior and strict input fields."""

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        use_enum_values=False,
    )


class JobStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    COMPLETED = "completed"
    FAILED = "failed"


class StageName(StrEnum):
    INTAKE = "intake"
    TTS = "tts"
    ALIGN = "align"
    PLACEMENTS = "placements"
    SUBTITLES = "subtitles"
    TIMELINE = "timeline"
    RENDER = "render"
    VALIDATE = "validate"


class StageStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    CACHED = "cached"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    BLOCKED = "blocked"
    AWAITING_APPROVAL = "awaiting_approval"


class MediaKind(StrEnum):
    GAMEPLAY = "gameplay"
    MUSIC = "music"
    OVERLAY = "overlay"


class MediaSource(StrEnum):
    ORIGINAL = "original"
    LICENSED = "licensed"
    COMMUNITY = "community"


class Zone(StrEnum):
    TOP_LEFT = "top-left"
    TOP_RIGHT = "top-right"
    MIDDLE = "middle"


class Animation(StrEnum):
    POP_IN = "pop-in"
    BOUNCE = "bounce"
    SLIDE_UP = "slide-up"


class KaraokeMode(StrEnum):
    KF = "kf"
    K = "k"

class VoicePresetId(StrEnum):
    MAD_SCIENTIST = "mad-scientist"
    NERVOUS_SIDEKICK = "nervous-sidekick"
    SLEAZY_CHARMER = "sleazy-charmer"
    LOUD_DAD = "loud-dad"
    SCHEMING_PRODIGY = "scheming-prodigy"
    WARM_STORYTELLER = "warm-storyteller"
    SHARP_COMMENTATOR = "sharp-commentator"


class VoicePreset(SlopShotsModel):
    """Natural Kokoro voice and pacing selected as one reusable style."""

    model_config = ConfigDict(frozen=True)

    id: VoicePresetId
    name: str
    description: str
    kokoro_voice: str
    kokoro_speed: float = Field(ge=0.5, le=1.5)


VOICE_PRESETS: tuple[VoicePreset, ...] = (
    VoicePreset(
        id=VoicePresetId.MAD_SCIENTIST,
        name="Mad Scientist",
        description="Fast, intense, lower delivery with chaotic scientist energy.",
        kokoro_voice="am_onyx",
        kokoro_speed=1.08,
    ),
    VoicePreset(
        id=VoicePresetId.NERVOUS_SIDEKICK,
        name="Nervous Sidekick",
        description="Quick, youthful delivery with restless sidekick energy.",
        kokoro_voice="am_puck",
        kokoro_speed=1.14,
    ),
    VoicePreset(
        id=VoicePresetId.SLEAZY_CHARMER,
        name="Sleazy Charmer",
        description="Smooth, upbeat delivery for an overconfident neighbor.",
        kokoro_voice="am_liam",
        kokoro_speed=1.04,
    ),
    VoicePreset(
        id=VoicePresetId.LOUD_DAD,
        name="Loud Sitcom Dad",
        description="Big, blunt delivery with heavyweight sitcom-dad energy.",
        kokoro_voice="am_fenrir",
        kokoro_speed=0.94,
    ),
    VoicePreset(
        id=VoicePresetId.SCHEMING_PRODIGY,
        name="Scheming Prodigy",
        description="Precise, clipped delivery with smug child-genius energy.",
        kokoro_voice="am_echo",
        kokoro_speed=1.10,
    ),
    VoicePreset(
        id=VoicePresetId.WARM_STORYTELLER,
        name="Warm Storyteller",
        description="Natural, friendly delivery for relaxed narration.",
        kokoro_voice="af_heart",
        kokoro_speed=0.98,
    ),
    VoicePreset(
        id=VoicePresetId.SHARP_COMMENTATOR,
        name="Sharp Commentator",
        description="Clear, assertive delivery for punchy commentary.",
        kokoro_voice="af_bella",
        kokoro_speed=1.03,
    ),
)


def get_voice_preset(preset_id: VoicePresetId) -> VoicePreset:
    return next(preset for preset in VOICE_PRESETS if preset.id == preset_id)


class CropMode(StrEnum):
    CENTER_9X16 = "center-9x16"


class EffectType(StrEnum):
    ZOOM_PUNCH = "zoom-punch"
    SHAKE = "shake"
    FLASH = "flash"
    FADE = "fade"


class IntegrationAvailability(SlopShotsModel):
    available: bool
    dependency: str
    required: bool = True
    executable: str | None = None
    detail: str | None = None


class HealthResponse(SlopShotsModel):
    status: str
    service: str
    version: str
    integrations: dict[str, IntegrationAvailability]
    data_directory: str
    data_directory_writable: bool
    job_count: int = Field(ge=0)


class AppSettings(SlopShotsModel):
    """Runtime settings.

    Heavy integrations are intentionally configured as strings and imported
    lazily by their adapters. Constructing the API therefore does not load a
    TTS or alignment model.
    """

    data_dir: Path = Field(default_factory=lambda: Path("backend/data"))
    ffmpeg_bin: str = "ffmpeg"
    ffprobe_bin: str = "ffprobe"
    kokoro_voice: str = "af_heart"
    kokoro_language: str = Field(default="a", min_length=1, max_length=8)
    kokoro_speed: float = Field(default=1.0, ge=0.5, le=1.5)
    whisperx_model: str = "small"
    whisperx_device: str = "cpu"
    whisperx_compute_type: str = "int8"
    whisperx_language: str | None = None
    alignment_confidence_threshold: float = Field(default=0.6, ge=0, le=1)
    karaoke_mode: KaraokeMode = KaraokeMode.KF
    stage_timeout_s: float = Field(default=60 * 60, gt=0)
    openai_base_url: str | None = "https://opencode.ai/zen/v1"
    openai_api_key: SecretStr | None = None
    openai_model: str | None = "deepseek-v4-flash-free"
    openai_timeout_s: float = Field(default=60, gt=0, le=600)
    media_input_roots: list[Path] = Field(default_factory=list)
    max_upload_bytes: int = Field(default=2 * 1024 * 1024 * 1024, gt=0)


class SettingsUpdate(SlopShotsModel):
    ffmpeg_bin: str | None = None
    ffprobe_bin: str | None = None
    kokoro_voice: str | None = None
    kokoro_language: str | None = Field(default=None, min_length=1, max_length=8)
    kokoro_speed: float | None = Field(default=None, ge=0.5, le=1.5)
    whisperx_model: str | None = None
    whisperx_device: str | None = None
    whisperx_compute_type: str | None = None
    whisperx_language: str | None = None
    alignment_confidence_threshold: float | None = Field(default=None, ge=0, le=1)
    karaoke_mode: KaraokeMode | None = None
    stage_timeout_s: float | None = Field(default=None, gt=0)
    openai_base_url: str | None = None
    openai_api_key: SecretStr | None = None
    openai_model: str | None = None
    openai_timeout_s: float | None = Field(default=None, gt=0, le=600)


class VideoJobCreate(SlopShotsModel):
    name: str = Field(min_length=1, max_length=120)
    script: str = Field(min_length=1)
    gameplay_file: str | None = None
    music_file: str | None = None
    voice_preset: VoicePresetId | None = None
    kokoro_voice: str | None = None
    kokoro_speed: float | None = Field(default=None, ge=0.5, le=1.5)
    karaoke_mode: KaraokeMode | None = None


class VideoJobUpdate(SlopShotsModel):
    gameplay_file: str | None = None
    music_file: str | None = None
    voice_preset: VoicePresetId | None = None
    kokoro_voice: str | None = None
    kokoro_speed: float | None = Field(default=None, ge=0.5, le=1.5)
    karaoke_mode: KaraokeMode | None = None


class ScriptIntakeRequest(SlopShotsModel):
    script: str = Field(min_length=1)


class LintIssue(SlopShotsModel):
    level: str
    code: str
    message: str


class NormalizationResult(SlopShotsModel):
    original: str
    normalized: str
    word_count: int = Field(ge=0)
    estimated_duration_s: float = Field(ge=0)
    hard_fail: bool
    issues: list[LintIssue] = Field(default_factory=list)


class ValidationCheck(SlopShotsModel):
    name: str
    passed: bool
    detail: str


class ValidationResult(SlopShotsModel):
    passed: bool
    checks: list[ValidationCheck] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    measured_duration_s: float | None = None
    measured_lufs: float | None = None
    measured_true_peak_db: float | None = None


class WordTiming(SlopShotsModel):
    word: str = Field(
        min_length=1,
        validation_alias=AliasChoices("w", "word"),
        serialization_alias="w",
    )
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    confidence: float = Field(
        default=1.0,
        ge=0,
        le=1,
        validation_alias=AliasChoices("conf", "confidence"),
        serialization_alias="conf",
    )
    index: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def end_after_start(self) -> WordTiming:
        if self.end <= self.start:
            raise ValueError("word end must be greater than start")
        return self


class PlacementProposal(SlopShotsModel):
    asset_id: str = Field(
        min_length=1,
        max_length=240,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_./-]*$",
        validation_alias=AliasChoices("asset_id", "asset"),
        serialization_alias="asset_id",
    )
    anchor_text: str = Field(min_length=1, max_length=200)
    zone: Zone
    duration_s: float = Field(gt=0, le=90)
    animation: Animation = Animation.POP_IN
    reason: str = Field(default="", max_length=500)
    scale: float = Field(default=0.35, gt=0, le=1.0)

    @field_validator("asset_id")
    @classmethod
    def safe_asset_id(cls, value: str) -> str:
        return _validate_asset_identifier(value)


class ResolvedPlacement(SlopShotsModel):
    asset_id: str = Field(
        min_length=1,
        validation_alias=AliasChoices("asset_id", "asset"),
        serialization_alias="asset_id",
    )
    anchor_text: str
    anchor_index: int = Field(ge=0)
    t_start: float = Field(ge=0)
    duration_s: float = Field(gt=0)
    zone: Zone
    animation: Animation
    reason: str = ""
    scale: float = Field(gt=0, le=1)
    warnings: list[str] = Field(default_factory=list)

    @field_validator("asset_id")
    @classmethod
    def safe_asset_id(cls, value: str) -> str:
        return _validate_asset_identifier(value)

    @property
    def t_end(self) -> float:
        return self.t_start + self.duration_s


class PlacementResolutionResult(SlopShotsModel):
    placements: list[ResolvedPlacement] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    dropped: list[PlacementProposal] = Field(default_factory=list)


class Canvas(SlopShotsModel):
    w: int = Field(default=1080, gt=0)
    h: int = Field(default=1920, gt=0)
    fps: int = Field(default=30, gt=0)


class GameplayTrack(SlopShotsModel):
    clip: str = Field(min_length=1)
    start_offset_s: float = Field(default=0, ge=0)
    crop: CropMode = CropMode.CENTER_9X16


class VoiceTrack(SlopShotsModel):
    file: str = Field(min_length=1)
    gain_db: float = 0


class SubtitlesTrack(SlopShotsModel):
    ass: str = Field(min_length=1)


class MusicTrack(SlopShotsModel):
    file: str = Field(min_length=1)
    gain_db: float = -22
    duck: bool = True


class OverlayTrack(SlopShotsModel):
    asset: str = Field(min_length=1)
    t: float = Field(ge=0)
    duration_s: float = Field(gt=0)
    zone: Zone
    animation: Animation = Animation.POP_IN
    scale: float = Field(default=0.35, gt=0, le=1)

    @model_validator(mode="after")
    def duration_is_positive(self) -> OverlayTrack:
        if self.duration_s <= 0:
            raise ValueError("overlay duration must be positive")
        return self


class ZoomPunchEffect(SlopShotsModel):
    type: EffectType = EffectType.ZOOM_PUNCH
    t: float = Field(ge=0)
    amount: float = Field(default=1.08, gt=1, le=1.15)
    in_s: float = Field(default=0.12, gt=0, le=0.4)
    out_s: float = Field(default=0.25, gt=0, le=0.4)


class ShakeEffect(SlopShotsModel):
    type: EffectType = EffectType.SHAKE
    t: float = Field(ge=0)
    amp_px: int = Field(default=6, ge=0, le=10)
    duration_s: float = Field(default=0.4, gt=0, le=0.5)


class FlashEffect(SlopShotsModel):
    type: EffectType = EffectType.FLASH
    t: float = Field(ge=0)


class FadeEffect(SlopShotsModel):
    type: EffectType = EffectType.FADE
    t: float = Field(ge=0)
    in_s: float | None = Field(default=None, gt=0)
    out_s: float | None = Field(default=None, gt=0)


Effect = ZoomPunchEffect | ShakeEffect | FlashEffect | FadeEffect


class TimelineTracks(SlopShotsModel):
    gameplay: GameplayTrack
    voice: VoiceTrack
    subtitles: SubtitlesTrack
    overlays: list[OverlayTrack] = Field(default_factory=list)
    effects: list[Effect] = Field(default_factory=list)
    music: MusicTrack | None = None


class Timeline(SlopShotsModel):
    version: int = Field(default=1, ge=1)
    canvas: Canvas = Field(default_factory=Canvas)
    tracks: TimelineTracks
    duration_s: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def version_is_supported(self) -> Timeline:
        if self.version != 1:
            raise ValueError("only timeline version 1 is supported")
        return self


class ArtifactInfo(SlopShotsModel):
    name: str
    exists: bool
    size_bytes: int = Field(ge=0)
    media_type: str
    download_path: str | None = None


class StageRecord(SlopShotsModel):
    stage: StageName
    status: StageStatus = StageStatus.PENDING
    started_at: datetime | None = None
    finished_at: datetime | None = None
    outputs: list[str] = Field(default_factory=list)
    cache_hit: bool = False
    message: str | None = None
    error_code: str | None = None
    error: str | None = None


class ApprovalRecord(SlopShotsModel):
    decision: Literal["approved", "rejected"]
    decided_at: datetime
    decided_by: str | None = None
    comment: str | None = None


class ApprovalRequest(SlopShotsModel):
    decided_by: str | None = Field(default=None, max_length=120)
    comment: str | None = Field(default=None, max_length=2000)


class StageRunRequest(SlopShotsModel):
    force: bool = False
    placements: list[PlacementProposal] | None = None
    use_opencode_zen: bool = False
    # Kept for clients using the original generic field name.
    use_openai: bool = False
    gameplay_file: str | None = None
    music_file: str | None = None
    draft: bool = False
    segment_from_s: float | None = Field(default=None, ge=0)
    segment_to_s: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def valid_segment(self) -> StageRunRequest:
        if (self.segment_from_s is None) != (self.segment_to_s is None):
            raise ValueError("segment_from_s and segment_to_s must be provided together")
        if (
            self.segment_from_s is not None
            and self.segment_to_s is not None
            and self.segment_to_s <= self.segment_from_s
        ):
            raise ValueError("segment_to_s must be greater than segment_from_s")
        return self


class PipelineRunRequest(StageRunRequest):
    target: StageName = StageName.VALIDATE


class PlacementApprovalRequest(SlopShotsModel):
    placements: list[PlacementProposal] | None = None
    decided_by: str | None = Field(default=None, max_length=120)
    comment: str | None = Field(default=None, max_length=2000)


class PlacementReviewResponse(SlopShotsModel):
    job: VideoJob
    proposals: list[PlacementProposal]
    resolved: PlacementResolutionResult | None = None
    approved: bool


class MediaAsset(SlopShotsModel):
    id: str = Field(min_length=1, max_length=240, pattern=r"^[A-Za-z0-9][A-Za-z0-9_./-]*$")
    kind: MediaKind
    filename: str
    media_type: str
    size_bytes: int = Field(ge=0)
    created_at: datetime
    source: MediaSource
    confirmed: bool = False
    description: str = Field(default="", max_length=500)
    tags: list[str] = Field(default_factory=list)
    duration_s: float | None = Field(default=None, gt=0)
    width: int | None = Field(default=None, gt=0)
    height: int | None = Field(default=None, gt=0)

    @field_validator("id")
    @classmethod
    def safe_id(cls, value: str) -> str:
        return _validate_asset_identifier(value)


class MediaRegisterRequest(SlopShotsModel):
    id: str = Field(min_length=1, max_length=240, pattern=r"^[A-Za-z0-9][A-Za-z0-9_./-]*$")
    kind: MediaKind
    path: str = Field(min_length=1)
    source: MediaSource
    confirmed: bool = False
    description: str = Field(default="", max_length=500)
    tags: list[str] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def safe_id(cls, value: str) -> str:
        return _validate_asset_identifier(value)


class MediaListResponse(SlopShotsModel):
    assets: list[MediaAsset]


class VideoJob(SlopShotsModel):
    id: str
    name: str
    status: JobStatus
    created_at: datetime
    updated_at: datetime
    directory: str
    gameplay_file: str | None = None
    music_file: str | None = None
    voice_preset: VoicePresetId | None = None
    kokoro_voice: str
    kokoro_speed: float
    karaoke_mode: KaraokeMode
    stages: list[StageRecord] = Field(default_factory=list)
    artifacts: list[ArtifactInfo] = Field(default_factory=list)
    approval: ApprovalRecord | None = None
    last_error: str | None = None


class StageRunResponse(SlopShotsModel):
    job: VideoJob
    stage: StageRecord


class ScriptIntakeResponse(SlopShotsModel):
    job: VideoJob
    result: NormalizationResult


class StageStatusResponse(SlopShotsModel):
    job_id: str
    stages: list[StageRecord]


class ArtifactListResponse(SlopShotsModel):
    job_id: str
    artifacts: list[ArtifactInfo]


class ApprovalResponse(SlopShotsModel):
    job: VideoJob
    approval: ApprovalRecord


class DependencyErrorResponse(SlopShotsModel):
    code: str
    message: str
    dependency: str
    executable: str | None = None


def model_to_jsonable(model: BaseModel) -> dict[str, Any]:
    """Serialize a model for the file-backed state store."""

    return model.model_dump(mode="json", by_alias=True)


def _validate_asset_identifier(value: str) -> str:
    """Reject path traversal while retaining useful namespaced asset IDs."""

    if "\\" in value or "\x00" in value or value.startswith("/"):
        raise ValueError("asset id must be a relative POSIX path")
    parts = value.split("/")
    if any(not part or part in {".", ".."} for part in parts):
        raise ValueError("asset id contains an unsafe path component")
    if any(
        not part[0].isalnum()
        or part[-1] in {".", " "}
        or any(not (char.isalnum() or char in "._-") for char in part)
        for part in parts
    ):
        raise ValueError("asset id contains unsupported characters")
    return value
