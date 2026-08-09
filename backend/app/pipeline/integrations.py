"""Adapters for the real local Kokoro and WhisperX integrations."""

from __future__ import annotations

import gc
import importlib.util
import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from ..errors import DependencyUnavailableError, PipelineError, StageBlockedError
from ..models import MediaAsset, PlacementProposal, WordTiming


def _require_module(module_name: str, *, dependency: str) -> None:
    if importlib.util.find_spec(module_name) is None:
        raise DependencyUnavailableError(
            f"{dependency} Python package is unavailable; install the optional backend dependency before running this stage",
            dependency=dependency,
        )


def _release_model_memory() -> None:
    """Return accelerator memory to the driver after a model step finishes.

    Dropping the last Python reference only returns memory to PyTorch's
    caching allocator; the CUDA driver still sees it as in use and the next
    pipeline stage (e.g. WhisperX after Kokoro) OOMs on a small GPU.
    Cleanup is best-effort and must never mask the real stage result.
    """

    gc.collect()
    try:
        import torch  # type: ignore[import-not-found]
    except ImportError:
        return
    try:
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:  # pragma: no cover - defensive cleanup path
        pass


@dataclass(frozen=True)
class AlignmentReport:
    words: list[WordTiming]
    language: str | None
    flagged_indices: list[int]
    flagged_ratio: float


class KokoroTTSAdapter:
    """Kokoro-82M synthesis adapter; there is no placeholder audio path."""

    sample_rate = 24_000

    @staticmethod
    def availability() -> tuple[bool, str | None]:
        missing = [
            name
            for name in ("kokoro", "numpy", "soundfile")
            if importlib.util.find_spec(name) is None
        ]
        if missing:
            return False, f"missing Python package(s): {', '.join(missing)}"
        return True, None

    def synthesize(
        self,
        text: str,
        *,
        output_path: Path,
        voice: str = "af_heart",
        speed: float = 1.0,
        language: str = "a",
    ) -> None:
        _require_module("kokoro", dependency="kokoro")
        _require_module("soundfile", dependency="soundfile")
        try:
            from kokoro import KPipeline  # type: ignore[import-not-found]
            import numpy as np  # type: ignore[import-not-found]
            import soundfile as sf  # type: ignore[import-not-found]
        except ImportError as exc:
            raise DependencyUnavailableError(
                f"Kokoro adapter could not import its runtime dependencies: {exc}",
                dependency="kokoro",
            ) from exc

        pipeline: Any = None
        try:
            pipeline = KPipeline(lang_code=language)
            chunks: list[Any] = []
            for generated in pipeline(text, voice=voice, speed=speed, split_pattern=r"\n+"):
                audio = (
                    generated[2]
                    if isinstance(generated, (tuple, list)) and len(generated) >= 3
                    else getattr(generated, "audio", None)
                )
                if audio is None:
                    continue
                if hasattr(audio, "detach"):
                    audio = audio.detach().cpu().numpy()
                array = np.asarray(audio)
                if array.ndim > 1:
                    array = array.reshape(-1)
                chunks.append(array)
                # The yielded object keeps the chunk's CUDA tensors alive;
                # drop it before the next chunk instead of at function exit.
                del generated
            if not chunks:
                raise PipelineError("Kokoro returned no audio frames")
            audio_array = np.concatenate(chunks)
            if audio_array.size == 0 or not np.isfinite(audio_array).all():
                raise PipelineError("Kokoro returned empty or non-finite audio frames")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = output_path.with_name(f".{output_path.name}.tmp")
            try:
                sf.write(str(temporary), audio_array, self.sample_rate, subtype="PCM_16", format="WAV")
                if not temporary.exists() or temporary.stat().st_size <= 44:
                    raise PipelineError("Kokoro did not produce a valid WAV file")
                temporary.replace(output_path)
            finally:
                temporary.unlink(missing_ok=True)
        except DependencyUnavailableError:
            raise
        except Exception as exc:
            raise PipelineError(f"Kokoro synthesis failed: {exc}") from exc
        finally:
            # The KPipeline holds the Kokoro torch model (CUDA when
            # available); drop it so the alignment stage can allocate VRAM.
            del pipeline
            _release_model_memory()


class WhisperXAlignmentAdapter:
    """WhisperX forced-alignment adapter with a confidence gate."""

    @staticmethod
    def availability() -> tuple[bool, str | None]:
        if importlib.util.find_spec("whisperx") is None:
            return False, "missing Python package: whisperx"
        return True, None

    def __init__(
        self,
        *,
        model_name: str = "small",
        device: str = "cpu",
        compute_type: str = "int8",
        language: str | None = None,
        confidence_threshold: float = 0.6,
    ) -> None:
        self.model_name = model_name
        self.device = device
        self.compute_type = compute_type
        self.language = language
        self.confidence_threshold = confidence_threshold

    def align(self, script: str, audio_path: Path) -> AlignmentReport:
        _require_module("whisperx", dependency="whisperx")
        try:
            import whisperx  # type: ignore[import-not-found]
        except ImportError as exc:
            raise DependencyUnavailableError(
                f"WhisperX adapter could not import its runtime package: {exc}",
                dependency="whisperx",
            ) from exc

        try:
            if not audio_path.exists() or not audio_path.is_file():
                raise PipelineError(f"alignment audio does not exist: {audio_path}")
            audio = whisperx.load_audio(str(audio_path))
            audio_duration = len(audio) / 16_000
            if audio_duration <= 0:
                raise PipelineError("WhisperX loaded an empty audio file")
            # The ASR model and the wav2vec2 alignment model never need to be
            # resident at the same time; free each before loading the next so
            # peak VRAM stays at one model on small GPUs.
            model: Any = None
            try:
                model = whisperx.load_model(
                    self.model_name,
                    device=self.device,
                    compute_type=self.compute_type,
                    language=self.language,
                )
                transcription = model.transcribe(audio, language=self.language) if self.language else model.transcribe(audio)
            finally:
                del model
                _release_model_memory()
            language = self.language or transcription.get("language")
            if not language:
                raise PipelineError("WhisperX did not return a language code")
            align_model: Any = None
            try:
                align_model, metadata = whisperx.load_align_model(
                    language_code=language,
                    device=self.device,
                )
                # Keep the known normalized script as the alignment transcript.
                # The ASR output is only used to discover the language and
                # segment span.
                forced_segments = [
                    {
                        "start": 0.0,
                        "end": audio_duration,
                        "text": script,
                    }
                ]
                aligned = whisperx.align(
                    forced_segments,
                    align_model,
                    metadata,
                    audio,
                    device=self.device,
                )
            finally:
                del align_model
                _release_model_memory()
            raw_words = aligned.get("word_segments") or []
            words = []
            for index, raw in enumerate(raw_words):
                word = str(raw.get("word", "")).strip()
                start = raw.get("start")
                end = raw.get("end")
                if not word or start is None or end is None:
                    continue
                confidence = raw.get("score", raw.get("confidence", 0.0))
                start_value = float(start)
                end_value = float(end)
                confidence_value = float(confidence)
                if start_value < 0 or end_value <= start_value or end_value > audio_duration + 0.25:
                    continue
                words.append(
                    WordTiming(
                        word=word,
                        start=start_value,
                        end=min(end_value, audio_duration),
                        confidence=max(0.0, min(1.0, confidence_value)),
                        index=index,
                    )
                )
            if not words:
                raise PipelineError("WhisperX returned no word timings")
            flagged = [word.index if word.index is not None else index for index, word in enumerate(words) if word.confidence < self.confidence_threshold]
            ratio = len(flagged) / len(words)
            if ratio > 0.10:
                raise StageBlockedError(
                    f"alignment confidence gate failed: {len(flagged)}/{len(words)} words ({ratio:.1%}) are below {self.confidence_threshold:.2f}"
                )
            return AlignmentReport(
                words=words,
                language=language,
                flagged_indices=flagged,
                flagged_ratio=ratio,
            )
        except (DependencyUnavailableError, PipelineError, StageBlockedError):
            raise
        except Exception as exc:
            raise PipelineError(f"WhisperX alignment failed: {exc}") from exc


class OpenAIPlacementAdapter:
    """Optional OpenCode Zen/OpenAI-compatible placement adapter.

    It uses the standard library so the base API install does not acquire an
    OpenAI SDK or make the adapter mandatory. OpenCode Zen's DeepSeek V4 Flash
    Free model uses the same chat-completions wire format. The backend still
    validates returned JSON with ``PlacementProposal`` before it reaches the
    pipeline.
    """

    dependency = "openai-compatible-placement"

    def __init__(self, *, base_url: str | None, api_key: str | None, model: str | None, timeout_s: float) -> None:
        self.base_url = base_url.rstrip("/") if base_url else None
        self.api_key = api_key
        # OpenCode's config uses ``opencode/<model-id>`` while its direct
        # OpenAI-compatible endpoint expects the bare model ID. Accept both
        # forms so a copied OpenCode model selection works here too.
        self.model = model.removeprefix("opencode/") if model else None
        self.timeout_s = timeout_s

    def availability(self) -> tuple[bool, str | None]:
        if not self.base_url:
            return False, "SLOPSHOTS_OPENCODE_ZEN_BASE_URL is not configured"
        if not self.model:
            return False, "SLOPSHOTS_OPENCODE_ZEN_MODEL is not configured"
        if self._is_opencode_zen() and not self.api_key:
            return False, "SLOPSHOTS_OPENCODE_ZEN_API_KEY is not configured"
        return True, None

    def suggest(
        self,
        *,
        script: str,
        words: list[WordTiming],
        assets: list[MediaAsset],
    ) -> list[PlacementProposal]:
        available, detail = self.availability()
        if not available:
            raise DependencyUnavailableError(
                detail or "OpenAI-compatible placement adapter is not configured",
                dependency=self.dependency,
            )
        assert self.base_url is not None
        assert self.model is not None
        prompt = {
            "script": script,
            "words": [word.model_dump(mode="json", by_alias=True) for word in words],
            "available_overlay_assets": [asset.id for asset in assets],
            "allowed_zones": ["top-left", "top-right", "middle"],
            "rules": [
                "Return JSON only.",
                "Return an object with a placements array.",
                "Use only available_overlay_assets as asset_id values.",
                "anchor_text must exactly match one contiguous phrase in words.",
                "duration_s must be positive and no more than 90.",
                "Prefer a small number of placements and never invent media files.",
            ],
        }
        body = json.dumps(
            {
                "model": self.model,
                "temperature": 0,
                "stream": False,
                "response_format": {"type": "json_object"},
                "messages": [
                    {
                        "role": "system",
                        "content": "You propose deterministic short-form video overlay placements.",
                    },
                    {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
                ],
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            self._endpoint(),
            data=body,
            headers={
                "Content-Type": "application/json",
                **({"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}),
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                raw_response = response.read()
        except urllib.error.HTTPError as exc:
            detail_text = exc.read().decode("utf-8", errors="replace")[-1000:]
            raise PipelineError(
                f"placement provider returned HTTP {exc.code}: {detail_text}",
                code="placement_provider_failed",
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise PipelineError(
                f"placement provider request failed: {exc}",
                code="placement_provider_failed",
            ) from exc
        try:
            response_json = json.loads(raw_response.decode("utf-8"))
            content = response_json["choices"][0]["message"]["content"]
            if isinstance(content, list):
                content = "".join(
                    part.get("text", "") for part in content if isinstance(part, dict)
                )
            if not isinstance(content, str):
                raise ValueError("chat completion content is not text")
            content = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", content.strip(), flags=re.IGNORECASE)
            parsed = json.loads(content)
            if isinstance(parsed, dict):
                parsed = parsed.get("placements")
            if not isinstance(parsed, list):
                raise ValueError("response must contain a placements array")
            return [PlacementProposal.model_validate(item) for item in parsed]
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise PipelineError(
                f"placement provider returned invalid placement JSON: {exc}",
                code="placement_provider_invalid_response",
            ) from exc

    def _endpoint(self) -> str:
        assert self.base_url is not None
        if self.base_url.endswith("/chat/completions"):
            return self.base_url
        if self.base_url.endswith("/v1"):
            return self.base_url + "/chat/completions"
        return self.base_url + "/v1/chat/completions"

    def _is_opencode_zen(self) -> bool:
        assert self.base_url is not None
        parsed = urlparse(self.base_url)
        return parsed.netloc == "opencode.ai" and parsed.path.startswith("/zen/")
