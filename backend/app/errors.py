"""Domain errors converted to useful API responses."""

from __future__ import annotations


class PipelineError(RuntimeError):
    code = "pipeline_error"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code


class NotFoundError(PipelineError):
    code = "not_found"


class InvalidRequestError(PipelineError):
    code = "invalid_request"


class ConflictError(PipelineError):
    code = "conflict"


class DependencyUnavailableError(PipelineError):
    code = "dependency_unavailable"

    def __init__(
        self,
        message: str,
        *,
        dependency: str,
        executable: str | None = None,
    ) -> None:
        super().__init__(message)
        self.dependency = dependency
        self.executable = executable


class CommandExecutionError(PipelineError):
    code = "command_failed"

    def __init__(self, message: str, *, command: list[str], returncode: int | None = None) -> None:
        super().__init__(message)
        self.command = command
        self.returncode = returncode


class StageBlockedError(PipelineError):
    code = "stage_blocked"


class ApprovalRequiredError(StageBlockedError):
    code = "approval_required"
