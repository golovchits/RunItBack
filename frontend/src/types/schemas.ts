// TypeScript mirror of backend/schemas/*.py.
// Kept lenient (fields that are agent-produced use Optional / looseness)
// because the corresponding Pydantic models are ConfigDict(extra="ignore").

export type AgentName =
  | "paper_analyst"
  | "code_auditor"
  | "validator"
  | "reviewer";

export type RuntimeMode = "managed_agents" | "messages_api";

export type AuditPhase =
  | "created"
  | "normalizing"
  | "paper_analyst"
  | "code_auditor"
  | "validator"
  | "reviewer"
  | "done"
  | "failed";

export type Severity = "critical" | "high" | "medium" | "low" | "info";

export type Verdict =
  | "reproducible"
  | "likely_reproducible"
  | "questionable"
  | "not_reproducible"
  | "inconclusive";

export type ClaimVerificationStatus =
  | "verified"
  | "partial"
  | "not_verified"
  | "unchecked";

export type DetectorRole = "auditor" | "validator" | "reviewer";

export type ValidationVerdict =
  | "confirmed"
  | "denied"
  | "inconclusive"
  | "unvalidated";

// ── inputs ────────────────────────────────────────────────────
export type PaperSource =
  | { kind: "arxiv"; arxiv_url: string }
  | { kind: "pdf_url"; url: string }
  | { kind: "upload"; upload_id: string }
  | { kind: "raw_text"; text: string; title_hint?: string | null }
  | { kind: "none"; title_hint?: string | null };

export type CodeSource =
  | { kind: "git"; url: string; ref?: string | null }
  | { kind: "local"; path: string };

export type DataSource =
  | { kind: "local"; path: string }
  | { kind: "url"; url: string; expected_size_gb?: number | null }
  | { kind: "bundled"; subpath?: string | null }
  | { kind: "skip" };

export interface AuditRequest {
  paper: PaperSource;
  code: CodeSource;
  data: DataSource;
  timeout_minutes?: number;
  force_fallback?: boolean;
  include_eda?: boolean;
  include_suggested_fixes?: boolean;
  user_notes?: string | null;
  data_structure_text?: string | null;
}

export interface AuditCreatedResponse {
  audit_id: string;
  status_url: string;
  stream_url: string;
  report_url: string;
  runtime_mode: RuntimeMode;
  phase: AuditPhase;
}

export interface AuditStatus {
  audit_id: string;
  phase: AuditPhase;
  runtime_mode: RuntimeMode;
  created_at: string;
  updated_at: string;
  findings_so_far: number;
  error: string | null;
  report_ready: boolean;
}

// ── code + evidence ───────────────────────────────────────────
export interface CodeSpan {
  file_path: string;
  line_start: number;
  line_end: number;
  snippet?: string;
  context_before?: number;
  context_after?: number;
  // handoff fixture adds this to pre-compute highlight lines; real
  // agent output computes these from [line_start, line_end].
  highlight_lines?: number[];
}

export interface Evidence {
  kind: string;
  description: string;
  raw: string;
}

// ── finding ───────────────────────────────────────────────────
export interface AuditFinding {
  id: string;
  category: string;
  severity: Severity;
  title: string;
  description: string;
  paper_claim_refs?: string[];
  code_span?: CodeSpan | null;
  data_path?: string | null;
  evidence?: Evidence[];
  paper_says?: string | null;
  code_does?: string | null;
  suggested_fix_diff?: string | null;
  suggested_fix_prose?: string | null;
  confidence: number;
  detector: DetectorRole;
  cross_refs?: string[];
  // report-side enrichment (validator match glued onto the finding)
  validation_verdict?: ValidationVerdict;
}

// ── validation ────────────────────────────────────────────────
export interface ValidationResult {
  id: string;
  finding_id: string;
  verdict: ValidationVerdict;
  method: string;
  command?: string | null;
  stdout_excerpt?: string | null;
  stderr_excerpt?: string | null;
  exit_code?: number | null;
  runtime_seconds?: number | null;
  numerical_evidence?: Record<string, number | string>;
  error?: string | null;
  confidence: number;
}

// ── EDA / claims ──────────────────────────────────────────────
export interface DataEDA {
  splits_observed: Record<string, number>;
  class_distribution?: Record<string, Record<string, number>>;
  file_format_stats?: Record<string, number>;
  sample_dimensions_summary?: string | null;
  corrupt_files?: string[];
  duplicate_hashes?: string[][];
}

export interface PaperClaims {
  paper_title: string;
  authors: string[];
  arxiv_id?: string | null;
  year?: number | null;
  abstract_summary: string;
  metrics: unknown[];
  datasets: unknown[];
  architectures: unknown[];
  training_config: unknown[];
  evaluation_protocol: unknown[];
  ablations?: unknown[];
  red_flags?: unknown[];
  extraction_confidence: number;
  unresolved_questions?: string[];
}

export interface ClaimVerification {
  claim_id: string;
  claim_summary?: string | null;
  status: ClaimVerificationStatus;
  code_location?: string | null;
  notes?: string | null;
  linked_finding_ids: string[];
}

export interface ConfigDiscrepancy {
  parameter: string;
  paper_value?: string | null;
  code_value?: string | null;
  code_location?: string | null;
  match: boolean;
  severity: Severity;
}

export interface Recommendation {
  rank: number;
  title: string;
  rationale: string;
  linked_finding_ids: string[];
}

export interface Disagreement {
  finding_id: string;
  auditor_verdict: string;
  validator_verdict: string;
  reviewer_resolution: string;
  exposed_in_report: boolean;
}

export interface DiagnosticReport {
  audit_id: string;
  generated_at: string;
  verdict: Verdict;
  confidence: number;
  headline: string;
  executive_summary: string;
  claim_verifications: ClaimVerification[];
  findings: AuditFinding[];
  config_comparison: ConfigDiscrepancy[];
  eda_summary?: DataEDA | null;
  recommendations: Recommendation[];
  unresolved_disagreements?: Disagreement[];
  severity_counts?: Record<string, number>;
  runtime_mode_used: RuntimeMode;
  runtime_ms_total: number;
  cost_usd_estimate?: number | null;
}

// ── SSE events ────────────────────────────────────────────────
interface EventBase {
  audit_id: string;
  seq: number;
  ts: string;
}

export type SSEEvent =
  | (EventBase & {
      type: "audit.status";
      phase: AuditPhase;
      eta_seconds?: number | null;
      message?: string | null;
    })
  | (EventBase & {
      type: "agent.started";
      agent: AgentName;
      session_id: string;
      runtime_mode: RuntimeMode;
    })
  | (EventBase & { type: "agent.thinking"; agent: AgentName; delta: string })
  | (EventBase & {
      type: "agent.message";
      agent: AgentName;
      text: string;
      is_final: boolean;
    })
  | (EventBase & {
      type: "agent.tool_use";
      agent: AgentName;
      tool: string;
      input_summary: string;
    })
  | (EventBase & {
      type: "agent.tool_result";
      agent: AgentName;
      tool: string;
      success: boolean;
      output_excerpt: string;
    })
  | (EventBase & {
      type: "agent.file_opened";
      agent: AgentName;
      file_path: string;
      line_start?: number | null;
      line_end?: number | null;
    })
  | (EventBase & {
      type: "agent.finding_emitted";
      agent: AgentName;
      finding: AuditFinding;
    })
  | (EventBase & {
      type: "validation.completed";
      result: ValidationResult;
    })
  | (EventBase & {
      type: "claims.extracted";
      claims: PaperClaims;
    })
  | (EventBase & {
      type: "agent.finished";
      agent: AgentName;
      duration_ms: number;
      output_tokens?: number | null;
      input_tokens?: number | null;
    })
  | (EventBase & {
      type: "report.chunk";
      delta: Record<string, unknown>;
    })
  | (EventBase & {
      type: "report.final";
      report: DiagnosticReport;
    })
  | (EventBase & {
      type: "audit.error";
      agent?: AgentName | null;
      error_type:
        | "timeout"
        | "api_error"
        | "validation_error"
        | "sandbox_error"
        | "input_error"
        | "internal_error";
      message: string;
      recoverable: boolean;
    })
  | (EventBase & {
      type: "audit.fallback_triggered";
      reason: string;
      target_mode: "messages_api";
    });

export type SSEEventType = SSEEvent["type"];

// Event list for bulk-subscription (matches backend's SSE `event:` field)
export const SSE_EVENT_TYPES: SSEEventType[] = [
  "audit.status",
  "agent.started",
  "agent.thinking",
  "agent.message",
  "agent.tool_use",
  "agent.tool_result",
  "agent.file_opened",
  "agent.finding_emitted",
  "validation.completed",
  "claims.extracted",
  "agent.finished",
  "report.chunk",
  "report.final",
  "audit.error",
  "audit.fallback_triggered",
];
