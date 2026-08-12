#!/usr/bin/env python3
"""Verify local media binaries and Python integrations without loading models."""

from __future__ import annotations

import argparse
import importlib
import os
import shutil
import subprocess
import sys


REQUIRED_FILTERS = ("subtitles", "loudnorm", "blackdetect", "freezedetect", "silencedetect")
REQUIRED_MODULES = ("multipart", "kokoro", "soundfile", "whisperx")


def _run(command: list[str]) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    output = (result.stdout + result.stderr).strip()
    return result.returncode == 0, output


def _check_executable(
    name: str, command: str, failures: list[str], version_flag: str = "-version"
) -> bool:
    resolved = shutil.which(command)
    if resolved is None:
        failures.append(f"{name}: executable not found ({command})")
        return False
    ok, detail = _run([resolved, version_flag])
    if not ok:
        failures.append(f"{name}: {resolved} did not pass {version_flag} ({detail})")
        return False
    print(f"PASS: {name} -> {resolved}")
    return True


def _check_ffmpeg_filters(command: str, failures: list[str]) -> None:
    resolved = shutil.which(command)
    if resolved is None:
        return
    ok, detail = _run([resolved, "-hide_banner", "-filters"])
    if not ok:
        failures.append(f"ffmpeg: could not list filters ({detail})")
        return
    missing = [name for name in REQUIRED_FILTERS if name not in detail.split()]
    if missing:
        failures.append(f"ffmpeg: required filters are missing: {', '.join(missing)}")
        return
    print(f"PASS: ffmpeg filters -> {', '.join(REQUIRED_FILTERS)}")


def _check_python_modules(failures: list[str]) -> None:
    for module_name in REQUIRED_MODULES:
        try:
            importlib.import_module(module_name)
        except (ImportError, ModuleNotFoundError) as exc:
            failures.append(f"Python package {module_name}: import failed ({exc})")
        except Exception as exc:  # pragma: no cover - environment-specific import failures
            failures.append(f"Python package {module_name}: import raised {type(exc).__name__}: {exc}")
        else:
            print(f"PASS: Python package {module_name} imports")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--binaries-only",
        action="store_true",
        help="skip multipart, Kokoro, soundfile, and WhisperX imports",
    )
    args = parser.parse_args()

    failures: list[str] = []
    ffmpeg = os.getenv("SLOPSHOTS_FFMPEG_BIN", "ffmpeg")
    ffprobe = os.getenv("SLOPSHOTS_FFPROBE_BIN", "ffprobe")
    espeak = os.getenv("SLOPSHOTS_ESPEAK_BIN", "espeak-ng")
    _check_executable("ffmpeg", ffmpeg, failures)
    _check_ffmpeg_filters(ffmpeg, failures)
    _check_executable("ffprobe", ffprobe, failures)
    _check_executable("espeak-ng", espeak, failures, version_flag="--version")
    if not args.binaries_only:
        _check_python_modules(failures)

    if failures:
        print("FAIL: local setup is incomplete", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1

    print("PASS: local setup is usable; no model weights were initialized or downloaded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
