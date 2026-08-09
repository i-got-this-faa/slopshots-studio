"""Configuration loading for the file-backed service."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from .models import AppSettings, SettingsUpdate


_DEFAULT_DATA_DIR = Path(__file__).resolve().parents[1] / "data"
_OPENCODE_ZEN_BASE_URL = "https://opencode.ai/zen/v1"
_OPENCODE_ZEN_MODEL = "deepseek-v4-flash-free"


def _env(name: str, default: str) -> str:
    value = os.getenv(name)
    return value if value is not None and value != "" else default


def _optional_env(name: str) -> str | None:
    value = os.getenv(name)
    return value if value is not None and value.strip() else None


def _first_optional_env(*names: str) -> str | None:
    """Return the first configured value, allowing provider-specific aliases."""

    for name in names:
        value = _optional_env(name)
        if value is not None:
            return value
    return None


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    """Build settings without importing any optional integration package."""

    return AppSettings(
        data_dir=Path(_env("SLOPSHOTS_DATA_DIR", str(_DEFAULT_DATA_DIR))),
        ffmpeg_bin=_env("SLOPSHOTS_FFMPEG_BIN", "ffmpeg"),
        ffprobe_bin=_env("SLOPSHOTS_FFPROBE_BIN", "ffprobe"),
        kokoro_voice=_env("SLOPSHOTS_KOKORO_VOICE", "af_heart"),
        kokoro_language=_env("SLOPSHOTS_KOKORO_LANGUAGE", "a"),
        kokoro_speed=float(_env("SLOPSHOTS_KOKORO_SPEED", "1.0")),
        whisperx_model=_env("SLOPSHOTS_WHISPERX_MODEL", "small"),
        whisperx_device=_env("SLOPSHOTS_WHISPERX_DEVICE", "cpu"),
        whisperx_compute_type=_env("SLOPSHOTS_WHISPERX_COMPUTE_TYPE", "int8"),
        whisperx_language=os.getenv("SLOPSHOTS_WHISPERX_LANGUAGE"),
        alignment_confidence_threshold=float(
            _env("SLOPSHOTS_ALIGNMENT_CONFIDENCE", "0.6")
        ),
        # OpenCode Zen exposes DeepSeek V4 Flash Free through the standard
        # OpenAI-compatible chat-completions contract. Keep the old variable
        # names as fallbacks so existing deployments do not break.
        openai_base_url=(
            _first_optional_env(
                "SLOPSHOTS_OPENCODE_ZEN_BASE_URL",
                "SLOPSHOTS_OPENAI_BASE_URL",
            )
            or _OPENCODE_ZEN_BASE_URL
        ),
        openai_api_key=_first_optional_env(
            "SLOPSHOTS_OPENCODE_ZEN_API_KEY",
            "OPENCODE_API_KEY",
            "SLOPSHOTS_OPENAI_API_KEY",
        ),
        openai_model=(
            _first_optional_env(
                "SLOPSHOTS_OPENCODE_ZEN_MODEL",
                "SLOPSHOTS_OPENAI_MODEL",
            )
            or _OPENCODE_ZEN_MODEL
        ),
        openai_timeout_s=float(
            _first_optional_env(
                "SLOPSHOTS_OPENCODE_ZEN_TIMEOUT_S",
                "SLOPSHOTS_OPENAI_TIMEOUT_S",
            )
            or "60"
        ),
        media_input_roots=[
            Path(item).expanduser()
            for item in _env("SLOPSHOTS_MEDIA_INPUT_ROOTS", "").split(os.pathsep)
            if item.strip()
        ],
        max_upload_bytes=int(_env("SLOPSHOTS_MAX_UPLOAD_BYTES", str(2 * 1024 * 1024 * 1024))),
    )


class SettingsManager:
    """Small in-process settings holder used by the API and pipeline."""

    def __init__(self, settings: AppSettings | None = None) -> None:
        self._settings = settings or get_settings()

    @property
    def value(self) -> AppSettings:
        return self._settings

    def update(self, update: SettingsUpdate) -> AppSettings:
        changes = {
            key: value
            for key, value in update.model_dump(exclude_unset=True).items()
            if value is not None
        }
        if changes:
            # ``model_copy(update=...)`` skips validation in Pydantic v2.
            # Re-validate the merged object so API updates preserve enum and
            # numeric bounds before the next stage consumes them.
            current = self._settings.model_dump(mode="python")
            self._settings = AppSettings.model_validate({**current, **changes})
        return self._settings
