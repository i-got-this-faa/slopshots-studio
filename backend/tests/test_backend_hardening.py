"""Small regression tests for backend boundaries that do not need model packages."""

from __future__ import annotations

import json
import math
import shutil
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.config import SettingsManager
from app.errors import InvalidRequestError
from app.main import create_app
from app.models import (
    AppSettings,
    GameplayTrack,
    MediaKind,
    MediaRegisterRequest,
    MediaSource,
    StageName,
    StageRunRequest,
    SubtitlesTrack,
    Timeline,
    TimelineTracks,
    VoiceTrack,
    VoicePresetId,
    VideoJobCreate,
    WordTiming,
)
from app.pipeline.integrations import OpenAIPlacementAdapter
from app.pipeline.ass import generate_ass
from app.pipeline.ffmpeg import FFmpegAdapter
from app.pipeline.service import PipelineService
from app.store import JobStore


class BackendHardeningTest(unittest.TestCase):
    def test_importing_app_helpers_has_no_filesystem_side_effect(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            unused_data = Path(directory) / "unused-data"
            result = subprocess.run(
                [sys.executable, "-c", "import app.models"],
                cwd=Path(__file__).parents[1],
                env={
                    "PATH": "/usr/bin:/bin",
                    "PYTHONPATH": str(Path(__file__).parents[1]),
                    "SLOPSHOTS_DATA_DIR": str(unused_data),
                },
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(unused_data.exists())

    def test_registered_media_is_copied_and_traversal_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            input_root = tmp_path / "input"
            input_root.mkdir()
            clip = input_root / "clip.mp4"
            clip.write_bytes(b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2")
            store = JobStore(
                tmp_path / "data",
                media_input_roots=[input_root],
                max_upload_bytes=1024,
            )

            asset = store.register_media(
                MediaRegisterRequest(
                    id="gameplay/clip",
                    kind=MediaKind.GAMEPLAY,
                    path=str(clip),
                    source=MediaSource.ORIGINAL,
                    confirmed=True,
                )
            )

            managed = store.resolve_media_reference(asset.id, expected_kind=MediaKind.GAMEPLAY)
            self.assertEqual(managed.parent, store.media_dir / "gameplay")
            self.assertEqual(managed.read_bytes(), clip.read_bytes())
            with self.assertRaises(InvalidRequestError):
                store.resolve_media_reference("../etc/passwd", expected_kind=MediaKind.GAMEPLAY)

    def test_stage_cache_manifest_tracks_inputs_and_options(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            settings = AppSettings(data_dir=tmp_path / "data")
            store = JobStore(settings.data_dir)
            job = store.create(
                VideoJobCreate(name="Cache test", script="hello"),
                settings,
            )
            job_dir = store.job_dir(job.id)
            (job_dir / "script.normalized.txt").write_text("hello\n", encoding="utf-8")
            (job_dir / "intake.json").write_text("{}\n", encoding="utf-8")
            service = PipelineService(store, SettingsManager(settings))
            request = StageRunRequest()
            service._write_stage_cache(job_dir, StageName.INTAKE, job, request)
            self.assertTrue(service._is_cached(job_dir, StageName.INTAKE, job, request))

            settings_changed = AppSettings(data_dir=settings.data_dir, kokoro_language="b")
            changed_service = PipelineService(store, SettingsManager(settings_changed))
            self.assertFalse(changed_service._is_cached(job_dir, StageName.INTAKE, job, request))

    def test_openai_compatible_response_is_strictly_validated(self) -> None:
        class Response:
            def __enter__(self) -> "Response":
                return self

            def __exit__(self, *args: object) -> None:
                return None

            def read(self) -> bytes:
                return json.dumps(
                    {
                        "choices": [
                            {
                                "message": {
                                    "content": '{"placements": []}',
                                }
                            }
                        ]
                    }
                ).encode()

        with patch("urllib.request.urlopen", return_value=Response()):
            adapter = OpenAIPlacementAdapter(
                base_url="http://placement.test/v1",
                api_key=None,
                model="placement-model",
                timeout_s=1,
            )
            self.assertEqual(adapter.suggest(script="hello", words=[], assets=[]), [])

    def test_voice_presets_are_listed_and_resolve_into_jobs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = AppSettings(data_dir=Path(directory) / "data")
            with TestClient(create_app(settings)) as client:
                presets_response = client.get("/api/v1/voice-presets")
                self.assertEqual(presets_response.status_code, 200)
                presets = presets_response.json()
                self.assertEqual(len(presets), 7)
                self.assertEqual(
                    {preset["id"] for preset in presets},
                    {preset.value for preset in VoicePresetId},
                )

                created_response = client.post(
                    "/api/v1/jobs",
                    json={
                        "name": "Preset test",
                        "script": "hello",
                        "voice_preset": VoicePresetId.MAD_SCIENTIST.value,
                    },
                )
                self.assertEqual(created_response.status_code, 201)
                created = created_response.json()
                self.assertEqual(created["voice_preset"], "mad-scientist")
                self.assertEqual(created["kokoro_voice"], "am_onyx")
                self.assertEqual(created["kokoro_speed"], 1.08)

                updated_response = client.patch(
                    f"/api/v1/jobs/{created['id']}",
                    json={"voice_preset": VoicePresetId.LOUD_DAD.value},
                )
                self.assertEqual(updated_response.status_code, 200)
                updated = updated_response.json()
                self.assertEqual(updated["voice_preset"], "loud-dad")
                self.assertEqual(updated["kokoro_voice"], "am_fenrir")
                self.assertEqual(updated["kokoro_speed"], 0.94)


@unittest.skipUnless(shutil.which("ffmpeg"), "real FFmpeg is not installed")
class RealRendererTest(unittest.TestCase):
    def test_real_renderer_writes_to_writable_data_root(self) -> None:
        """Exercise the real renderer while the backend source tree stays untouched."""

        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            data_dir = tmp_path / "writable-data"
            data_dir.mkdir()
            gameplay = data_dir / "gameplay.mp4"
            voice = data_dir / "voice.wav"
            subtitles = data_dir / "subtitles.ass"
            output = data_dir / "final.mp4"

            from app.pipeline.process import run_safe

            run_safe(
                [
                    shutil.which("ffmpeg") or "ffmpeg",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    "testsrc=size=640x360:rate=30",
                    "-t",
                    "2",
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    str(gameplay),
                ],
                timeout_s=60,
            )
            with wave.open(str(voice), "wb") as handle:
                handle.setnchannels(1)
                handle.setsampwidth(2)
                handle.setframerate(24_000)
                frames = [
                    int(5000 * math.sin(2 * math.pi * 440 * i / 24_000))
                    for i in range(24_000)
                ]
                handle.writeframes(
                    b"".join(frame.to_bytes(2, "little", signed=True) for frame in frames)
                )
            subtitles.write_text(
                generate_ass([WordTiming(w="hello", start=0.1, end=0.5)]),
                encoding="utf-8",
            )
            timeline = Timeline(
                tracks=TimelineTracks(
                    gameplay=GameplayTrack(clip=str(gameplay)),
                    voice=VoiceTrack(file=str(voice)),
                    subtitles=SubtitlesTrack(ass=str(subtitles)),
                ),
                duration_s=1.3,
            )
            result = FFmpegAdapter().render(
                timeline,
                output_path=output,
                duration_s=1.3,
                timeout_s=60,
            )
            self.assertEqual(result.output_path, output)
            self.assertTrue(output.is_file() and output.stat().st_size > 0)


if __name__ == "__main__":
    unittest.main()
