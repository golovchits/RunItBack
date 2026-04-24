from __future__ import annotations

import logging
from contextvars import ContextVar
from typing import Any, Optional

import structlog

_audit_id_ctx: ContextVar[Optional[str]] = ContextVar("audit_id", default=None)


def _inject_audit_id(_logger, _name, event_dict: dict[str, Any]) -> dict[str, Any]:
    audit_id = _audit_id_ctx.get()
    if audit_id is not None:
        event_dict.setdefault("audit_id", audit_id)
    return event_dict


def configure_logging(level: str = "info") -> None:
    level_num = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(level=level_num, format="%(message)s")

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            _inject_audit_id,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level_num),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def bind_audit_id(audit_id: Optional[str]) -> None:
    _audit_id_ctx.set(audit_id)


def get_logger(name: Optional[str] = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
