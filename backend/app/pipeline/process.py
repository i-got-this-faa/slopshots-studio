"""Safe subprocess execution shared by FFmpeg and FFprobe adapters."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from ..errors import CommandExecutionError, DependencyUnavailableError


@dataclass(frozen=True)
class ProcessResult:
    args: list[str]
    returncode: int
    stdout: str
    stderr: str


def require_executable(executable: str, *, dependency: str) -> str:
    """Resolve an executable or raise a user-actionable dependency error."""

    resolved = shutil.which(executable)
    if not resolved:
        raise DependencyUnavailableError(
            f"{dependency} executable '{executable}' is unavailable; install it or configure the corresponding *_bin setting",
            dependency=dependency,
            executable=executable,
        )
    return resolved


def run_safe(
    args: list[str],
    *,
    cwd: Path | None = None,
    timeout_s: float = 3600,
    env: dict[str, str] | None = None,
    check: bool = True,
) -> ProcessResult:
    """Run a command with an argv list and no shell interpolation."""

    if not args or any(not isinstance(arg, str) for arg in args):
        raise ValueError("safe subprocess execution requires a non-empty list[str]")
    try:
        completed = subprocess.run(
            args,
            cwd=str(cwd) if cwd else None,
            env={**os.environ, **env} if env else None,
            check=False,
            shell=False,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except FileNotFoundError as exc:
        raise DependencyUnavailableError(
            f"executable '{args[0]}' could not be started",
            dependency=args[0],
            executable=args[0],
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise CommandExecutionError(
            f"command timed out after {timeout_s:.0f}s: {args[0]}",
            command=args,
        ) from exc

    result = ProcessResult(
        args=args,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )
    if check and result.returncode != 0:
        tail = result.stderr.strip()[-2000:]
        raise CommandExecutionError(
            f"command failed with exit code {result.returncode}: {args[0]}\n{tail}",
            command=args,
            returncode=result.returncode,
        )
    return result

