from __future__ import annotations

from typing import Annotated, Literal, Optional, Union

from pydantic import Field

from .claims import PaperClaims
from .common import Strict
from .findings import AuditFinding
from .inputs import AuditPhase, RuntimeMode
from .report import DiagnosticReport
from .validation import ValidationResult


class _EventBase(Strict):
    # These are required fields semantically, but carry defaults so the
    # pipeline can construct events via `emit(cls, phase=...)` and fill
    # audit_id/seq/ts in a single place. Roundtrip tests explicitly set
    # all three, so the wire format is unaffected.
    audit_id: str = ""
    seq: int = 0
    ts: str = ""


AgentName = Literal["paper_analyst", "code_auditor", "validator", "reviewer"]


class EvtAuditStatus(_EventBase):
    type: Literal["audit.status"] = "audit.status"
    phase: AuditPhase
    eta_seconds: Optional[int] = None
    message: Optional[str] = None


class EvtAgentStarted(_EventBase):
    type: Literal["agent.started"] = "agent.started"
    agent: AgentName
    session_id: str
    runtime_mode: RuntimeMode


class EvtAgentThinking(_EventBase):
    type: Literal["agent.thinking"] = "agent.thinking"
    agent: AgentName
    delta: str


class EvtAgentMessage(_EventBase):
    type: Literal["agent.message"] = "agent.message"
    agent: AgentName
    text: str
    is_final: bool


class EvtAgentToolUse(_EventBase):
    type: Literal["agent.tool_use"] = "agent.tool_use"
    agent: AgentName
    tool: str
    input_summary: str = Field(max_length=400)


class EvtAgentToolResult(_EventBase):
    type: Literal["agent.tool_result"] = "agent.tool_result"
    agent: AgentName
    tool: str
    success: bool
    output_excerpt: str = Field(max_length=2000)


class EvtAgentFileOpened(_EventBase):
    type: Literal["agent.file_opened"] = "agent.file_opened"
    agent: AgentName
    file_path: str
    line_start: Optional[int] = None
    line_end: Optional[int] = None


class EvtFindingEmitted(_EventBase):
    type: Literal["agent.finding_emitted"] = "agent.finding_emitted"
    agent: AgentName
    finding: AuditFinding


class EvtValidationCompleted(_EventBase):
    type: Literal["validation.completed"] = "validation.completed"
    result: ValidationResult


class EvtClaimsExtracted(_EventBase):
    type: Literal["claims.extracted"] = "claims.extracted"
    claims: PaperClaims


class EvtAgentFinished(_EventBase):
    type: Literal["agent.finished"] = "agent.finished"
    agent: AgentName
    duration_ms: int
    output_tokens: Optional[int] = None
    input_tokens: Optional[int] = None


class EvtReportChunk(_EventBase):
    type: Literal["report.chunk"] = "report.chunk"
    delta: dict[str, object]


class EvtReportFinal(_EventBase):
    type: Literal["report.final"] = "report.final"
    report: DiagnosticReport


class EvtAuditError(_EventBase):
    type: Literal["audit.error"] = "audit.error"
    agent: Optional[AgentName] = None
    error_type: Literal[
        "timeout",
        "api_error",
        "validation_error",
        "sandbox_error",
        "input_error",
        "internal_error",
    ]
    message: str
    recoverable: bool


class EvtFallbackTriggered(_EventBase):
    type: Literal["audit.fallback_triggered"] = "audit.fallback_triggered"
    reason: str
    target_mode: Literal["messages_api"]


SSEEvent = Annotated[
    Union[
        EvtAuditStatus,
        EvtAgentStarted,
        EvtAgentThinking,
        EvtAgentMessage,
        EvtAgentToolUse,
        EvtAgentToolResult,
        EvtAgentFileOpened,
        EvtFindingEmitted,
        EvtValidationCompleted,
        EvtClaimsExtracted,
        EvtAgentFinished,
        EvtReportChunk,
        EvtReportFinal,
        EvtAuditError,
        EvtFallbackTriggered,
    ],
    Field(discriminator="type"),
]
