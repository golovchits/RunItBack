from __future__ import annotations

from typing import Any, Optional


class RunItBackError(Exception):
    """Base for all application errors that map to HTTP responses.

    Subclasses set ``status_code`` and ``error_type`` to the values
    defined in ARCHITECTURE.md §4.
    """

    status_code: int = 500
    error_type: str = "internal_error"

    def __init__(
        self, message: str, *, details: Optional[dict[str, Any]] = None
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_payload(self) -> dict[str, Any]:
        return {
            "error": {
                "type": self.error_type,
                "message": self.message,
                "details": self.details,
            }
        }


class InputError(RunItBackError):
    status_code = 400
    error_type = "input_error"


class NotFoundError(RunItBackError):
    status_code = 404
    error_type = "not_found"


class ConflictError(RunItBackError):
    status_code = 409
    error_type = "conflict"


class DataTooLargeError(RunItBackError):
    status_code = 413
    error_type = "data_too_large"


class RateLimitedError(RunItBackError):
    status_code = 429
    error_type = "rate_limited"


class UnavailableError(RunItBackError):
    status_code = 503
    error_type = "unavailable"


class NonRecoverableAPIError(RunItBackError):
    status_code = 502
    error_type = "api_error"


class ValidationFailedError(RunItBackError):
    status_code = 500
    error_type = "validation_error"


class SandboxError(RunItBackError):
    status_code = 500
    error_type = "sandbox_error"


class TurnLimitExceeded(RunItBackError):
    status_code = 500
    error_type = "internal_error"

    def __init__(self, role: str, turns: int) -> None:
        super().__init__(
            f"agent {role!r} exceeded turn limit ({turns} turns)",
            details={"role": role, "turns": turns},
        )
