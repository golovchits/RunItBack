from __future__ import annotations

from backend.errors import (
    ConflictError,
    DataTooLargeError,
    InputError,
    NonRecoverableAPIError,
    NotFoundError,
    RateLimitedError,
    RunItBackError,
    SandboxError,
    TurnLimitExceeded,
    UnavailableError,
    ValidationFailedError,
)


def test_input_error_payload_shape():
    err = InputError("bad", details={"field": "paper"})
    assert err.status_code == 400
    assert err.error_type == "input_error"
    assert err.to_payload() == {
        "error": {
            "type": "input_error",
            "message": "bad",
            "details": {"field": "paper"},
        }
    }


def test_http_status_codes():
    assert InputError("x").status_code == 400
    assert NotFoundError("x").status_code == 404
    assert ConflictError("x").status_code == 409
    assert DataTooLargeError("x").status_code == 413
    assert RateLimitedError("x").status_code == 429
    assert NonRecoverableAPIError("x").status_code == 502
    assert UnavailableError("x").status_code == 503


def test_all_subclass_base():
    for cls in (
        InputError,
        NotFoundError,
        ConflictError,
        DataTooLargeError,
        RateLimitedError,
        NonRecoverableAPIError,
        UnavailableError,
        SandboxError,
        ValidationFailedError,
    ):
        assert issubclass(cls, RunItBackError)


def test_turn_limit_details():
    err = TurnLimitExceeded(role="code_auditor", turns=81)
    assert err.details == {"role": "code_auditor", "turns": 81}
    assert "code_auditor" in err.message
    assert "81" in err.message
    assert err.to_payload()["error"]["details"]["turns"] == 81


def test_empty_details_default():
    err = UnavailableError("down")
    assert err.details == {}
    assert err.to_payload()["error"]["details"] == {}
