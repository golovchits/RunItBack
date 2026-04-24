import { create } from "zustand";
import type {
  AgentName,
  AuditFinding,
  AuditPhase,
  AuditRequest,
  ClaimVerification,
  DiagnosticReport,
  PaperClaims,
  RuntimeMode,
  SSEEvent,
  ValidationResult,
} from "../types/schemas";
import { api } from "../api/client";
import { subscribeAudit, type StreamHandle } from "../api/stream";

type AgentStatus = "idle" | "starting" | "running" | "done" | "failed";

export type ActivityMessageKind =
  | "status"
  | "thinking"
  | "message"
  | "tool_use"
  | "tool_result"
  | "file_opened"
  | "finding"
  | "validation"
  | "claims"
  | "finished"
  | "fallback"
  | "error";

export interface ActivityMessage {
  id: string;
  ts: string;
  seq: number;
  agent: AgentName | null;
  kind: ActivityMessageKind;
  text: string;
  // Optional supplementary payload, rendered collapsibly.
  detail?: string;
  tool?: string;
  success?: boolean;
  severity?: "info" | "warn" | "error";
}

export interface AgentState {
  status: AgentStatus;
  startedAt?: string;
  finishedAt?: string;
  durationMs?: number;
  inputTokens?: number;
  outputTokens?: number;
  thinkingBuffer: string;
}

const AGENTS: AgentName[] = [
  "paper_analyst",
  "code_auditor",
  "validator",
  "reviewer",
];

function emptyAgents(): Record<AgentName, AgentState> {
  const out = {} as Record<AgentName, AgentState>;
  for (const a of AGENTS) out[a] = { status: "idle", thinkingBuffer: "" };
  return out;
}

export interface ViewerState {
  file: string | null;
  start: number | null;
  end: number | null;
  // The lines the caller asked us to highlight. Kept separate from
  // start/end (which the file fetch overwrites with the wider context
  // window so the snippet has surrounding lines for orientation).
  highlightStart: number | null;
  highlightEnd: number | null;
  content: string | null;
  totalLines: number | null;
  loading: boolean;
  error: string | null;
}

export interface AuditError {
  message: string;
  agent?: AgentName | null;
  recoverable?: boolean;
  errorType?: string;
}

export interface AuditState {
  auditId: string | null;
  phase: AuditPhase | null;
  runtimeMode: RuntimeMode | null;
  agents: Record<AgentName, AgentState>;
  currentAgent: AgentName | null;
  findings: Record<string, AuditFinding>;
  findingOrder: string[];
  claims: PaperClaims | null;
  claimVerifications: ClaimVerification[];
  validations: Record<string, ValidationResult>;
  activity: ActivityMessage[];
  viewer: ViewerState;
  report: DiagnosticReport | null;
  error: AuditError | null;
  submitting: boolean;
  streamHandle: StreamHandle | null;
  lastEventSeq: number;

  // mutators
  startAudit: (req: AuditRequest) => Promise<void>;
  resumeAudit: (id: string) => Promise<void>;
  cancelAudit: () => Promise<void>;
  reset: () => void;
  openFile: (file: string, start?: number, end?: number) => Promise<void>;
  handleEvent: (ev: SSEEvent) => void;
  loadFixtureReport: (report: DiagnosticReport) => void;
}

const initial = {
  auditId: null as string | null,
  phase: null as AuditPhase | null,
  runtimeMode: null as RuntimeMode | null,
  currentAgent: null as AgentName | null,
  claims: null as PaperClaims | null,
  report: null as DiagnosticReport | null,
  error: null as AuditError | null,
  submitting: false,
  streamHandle: null as StreamHandle | null,
  lastEventSeq: -1,
};

function makeActivity(
  ev: SSEEvent,
  kind: ActivityMessageKind,
  text: string,
  extra?: Partial<ActivityMessage>,
): ActivityMessage {
  return {
    id: `${ev.seq}-${kind}-${Math.random().toString(36).slice(2, 8)}`,
    // Stamp with the device clock so the feed always shows the user's
    // local wall time, regardless of server clock drift or timezone.
    ts: new Date().toISOString(),
    seq: ev.seq,
    agent: "agent" in ev ? (ev.agent as AgentName) : null,
    kind,
    text,
    ...extra,
  };
}

const MAX_ACTIVITY = 400;
const MAX_THINKING_BUFFER = 2000;

export const useAudit = create<AuditState>((set, get) => ({
  ...initial,
  agents: emptyAgents(),
  findings: {},
  findingOrder: [],
  claimVerifications: [],
  validations: {},
  activity: [],
  viewer: {
    file: null,
    start: null,
    end: null,
    highlightStart: null,
    highlightEnd: null,
    content: null,
    totalLines: null,
    loading: false,
    error: null,
  },

  reset: () => {
    const { streamHandle } = get();
    if (streamHandle) streamHandle.close();
    set({
      ...initial,
      agents: emptyAgents(),
      findings: {},
      findingOrder: [],
      claimVerifications: [],
      validations: {},
      activity: [],
      viewer: {
        file: null,
        start: null,
        end: null,
        highlightStart: null,
        highlightEnd: null,
        content: null,
        totalLines: null,
        loading: false,
        error: null,
      },
    });
  },

  startAudit: async (req) => {
    get().reset();
    set({ submitting: true, error: null });
    try {
      const resp = await api.createAudit(req);
      set({
        auditId: resp.audit_id,
        phase: resp.phase,
        runtimeMode: resp.runtime_mode,
        submitting: false,
      });
      // Pin the audit id into the URL so a refresh, tab-share, or
      // navigate-back pulls this audit's saved report from disk via
      // the resume path, instead of the live-stream's in-memory
      // state (which may hold a stale fallback report if live
      // validation hit a schema error and was later re-parsed
      // against an updated schema).
      window.history.replaceState({}, "", `/audit/${resp.audit_id}`);
      const handle = subscribeAudit(
        resp.audit_id,
        (ev) => get().handleEvent(ev),
        () => {
          // Transient drops are tolerable; EventSource auto-reconnects.
        },
      );
      set({ streamHandle: handle });
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      set({ submitting: false, error: { message: msg } });
      throw e;
    }
  },

  resumeAudit: async (id) => {
    get().reset();
    try {
      const status = await api.getStatus(id);
      set({
        auditId: status.audit_id,
        phase: status.phase,
        runtimeMode: status.runtime_mode,
      });
      if (status.phase === "done" && status.report_ready) {
        const report = await api.getReport(id);
        set({ report, phase: "done" });
        return;
      }
      const handle = subscribeAudit(id, (ev) => get().handleEvent(ev));
      set({ streamHandle: handle });
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      set({ error: { message: msg } });
    }
  },

  cancelAudit: async () => {
    const { auditId, streamHandle } = get();
    if (!auditId) return;
    if (streamHandle) streamHandle.close();
    try {
      await api.cancelAudit(auditId);
    } finally {
      set({ streamHandle: null, phase: "failed" });
    }
  },

  openFile: async (file, start, end) => {
    const { auditId } = get();
    // Remember what the caller wanted highlighted. start/end below get
    // overwritten with the wider context window once the file fetch
    // returns; without this we'd lose the original range and the viewer
    // would highlight the top of the window instead of the actual span.
    const highlightStart = start ?? null;
    const highlightEnd = end ?? start ?? null;
    set((s) => ({
      viewer: {
        ...s.viewer,
        file,
        start: start ?? null,
        end: end ?? null,
        highlightStart,
        highlightEnd,
        loading: !!auditId,
        error: null,
      },
    }));
    if (!auditId) return;
    // Fetch a reasonable window around the span so decorations have
    // context without pulling the whole file for huge sources.
    const context = 80;
    const fetchStart = start != null ? Math.max(1, start - context) : undefined;
    const fetchEnd = end != null ? end + context : undefined;
    try {
      const data = await api.getFile(auditId, file, fetchStart, fetchEnd);
      set((s) => ({
        viewer: {
          ...s.viewer,
          content: data.content,
          totalLines: data.total_lines,
          start: data.start,
          end: data.end,
          loading: false,
        },
      }));
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      set((s) => ({
        viewer: { ...s.viewer, loading: false, error: msg },
      }));
    }
  },

  loadFixtureReport: (report) => {
    set({
      auditId: report.audit_id,
      phase: "done",
      runtimeMode: report.runtime_mode_used,
      report,
    });
  },

  handleEvent: (ev) => {
    // Drop duplicates: SSE reconnects replay from the last seq and the
    // backend occasionally emits a heartbeat twice under load. seq is
    // monotonic per audit, so anything we've already seen is safe to skip.
    if (ev.seq <= get().lastEventSeq) return;
    set({ lastEventSeq: ev.seq });

    // Append to activity feed (cap length).
    const pushActivity = (msg: ActivityMessage) =>
      set((s) => {
        const next = [...s.activity, msg];
        if (next.length > MAX_ACTIVITY) next.splice(0, next.length - MAX_ACTIVITY);
        return { activity: next };
      });

    switch (ev.type) {
      case "audit.status": {
        set({ phase: ev.phase });
        pushActivity(
          makeActivity(ev, "status", `Phase → ${ev.phase}`, {
            detail: ev.message ?? undefined,
          }),
        );
        break;
      }

      case "agent.started": {
        set((s) => ({
          currentAgent: ev.agent,
          runtimeMode: ev.runtime_mode,
          agents: {
            ...s.agents,
            [ev.agent]: {
              ...s.agents[ev.agent],
              status: "running",
              startedAt: ev.ts,
            },
          },
        }));
        pushActivity(makeActivity(ev, "status", `${ev.agent} started`));
        break;
      }

      case "agent.thinking": {
        set((s) => {
          const prev = s.agents[ev.agent];
          const buffer = (prev.thinkingBuffer + ev.delta).slice(
            -MAX_THINKING_BUFFER,
          );
          return {
            agents: {
              ...s.agents,
              [ev.agent]: { ...prev, thinkingBuffer: buffer },
            },
          };
        });
        // Coalesce streamed thinking deltas into the last thinking entry
        // from the same agent so the feed doesn't get a row per token.
        set((s) => {
          const last = s.activity[s.activity.length - 1];
          if (
            last &&
            last.kind === "thinking" &&
            last.agent === ev.agent &&
            ev.seq - last.seq < 100
          ) {
            const updated = [...s.activity];
            updated[updated.length - 1] = {
              ...last,
              text: (last.text + ev.delta).slice(-1000),
              ts: ev.ts,
            };
            return { activity: updated };
          }
          const next: ActivityMessage[] = [
            ...s.activity,
            makeActivity(ev, "thinking", ev.delta),
          ];
          if (next.length > MAX_ACTIVITY)
            next.splice(0, next.length - MAX_ACTIVITY);
          return { activity: next };
        });
        break;
      }

      case "agent.message": {
        pushActivity(
          makeActivity(ev, "message", ev.text, {
            detail: ev.is_final ? "final" : undefined,
          }),
        );
        break;
      }

      case "agent.tool_use": {
        pushActivity(
          makeActivity(ev, "tool_use", ev.input_summary, { tool: ev.tool }),
        );
        break;
      }

      case "agent.tool_result": {
        pushActivity(
          makeActivity(ev, "tool_result", ev.output_excerpt, {
            tool: ev.tool,
            success: ev.success,
          }),
        );
        break;
      }

      case "agent.file_opened": {
        pushActivity(
          makeActivity(
            ev,
            "file_opened",
            `${ev.file_path}${
              ev.line_start ? `:${ev.line_start}-${ev.line_end ?? ev.line_start}` : ""
            }`,
          ),
        );
        // Drive the viewer.
        void get().openFile(
          ev.file_path,
          ev.line_start ?? undefined,
          ev.line_end ?? undefined,
        );
        break;
      }

      case "agent.finding_emitted": {
        const f = ev.finding;
        set((s) => ({
          findings: { ...s.findings, [f.id]: f },
          findingOrder: s.findingOrder.includes(f.id)
            ? s.findingOrder
            : [...s.findingOrder, f.id],
        }));
        pushActivity(
          makeActivity(ev, "finding", f.title, {
            severity: f.severity === "critical" ? "error" : "warn",
            detail: f.category,
          }),
        );
        if (f.code_span?.file_path) {
          void get().openFile(
            f.code_span.file_path,
            f.code_span.line_start,
            f.code_span.line_end,
          );
        }
        break;
      }

      case "validation.completed": {
        const r = ev.result;
        set((s) => ({
          validations: { ...s.validations, [r.finding_id]: r },
        }));
        pushActivity(
          makeActivity(
            ev,
            "validation",
            `${r.finding_id} → ${r.verdict}`,
            { detail: r.method },
          ),
        );
        break;
      }

      case "claims.extracted": {
        set({ claims: ev.claims });
        pushActivity(
          makeActivity(ev, "claims", `${ev.claims.metrics.length} metrics extracted`),
        );
        break;
      }

      case "agent.finished": {
        set((s) => ({
          agents: {
            ...s.agents,
            [ev.agent]: {
              ...s.agents[ev.agent],
              status: "done",
              finishedAt: ev.ts,
              durationMs: ev.duration_ms,
              inputTokens: ev.input_tokens ?? undefined,
              outputTokens: ev.output_tokens ?? undefined,
            },
          },
        }));
        pushActivity(
          makeActivity(ev, "finished", `${ev.agent} finished (${Math.round(
            ev.duration_ms / 1000,
          )}s)`),
        );
        break;
      }

      case "report.chunk": {
        // Partial updates — we just buffer them for now; the final report
        // arrives in report.final. This is a hook for a future streaming
        // report renderer.
        break;
      }

      case "report.final": {
        set({
          report: ev.report,
          phase: "done",
          claimVerifications: ev.report.claim_verifications,
        });
        pushActivity(
          makeActivity(ev, "status", "Report generated", {
            severity: "info",
          }),
        );
        break;
      }

      case "audit.error": {
        set((s) => {
          const err = {
            message: ev.message,
            agent: ev.agent,
            recoverable: ev.recoverable,
            errorType: ev.error_type,
          };
          if (ev.recoverable) return { error: err };
          // Non-recoverable: freeze any still-running agents so their
          // per-agent timer stops ticking in the sidebar. We'd otherwise
          // leave the offender (or everyone, on a pipeline-level error)
          // stuck at status "running" forever.
          const evMs = new Date(ev.ts).getTime();
          const agents = { ...s.agents };
          for (const name of AGENTS) {
            const a = agents[name];
            if (a.status === "running" || a.status === "starting") {
              const startedMs = a.startedAt
                ? new Date(a.startedAt).getTime()
                : null;
              const durationMs =
                startedMs != null
                  ? Math.max(0, evMs - startedMs)
                  : a.durationMs ?? 0;
              agents[name] = {
                ...a,
                status: "failed",
                finishedAt: ev.ts,
                durationMs,
              };
            }
          }
          return {
            error: err,
            phase: "failed" as AuditPhase,
            agents,
          };
        });
        pushActivity(
          makeActivity(ev, "error", ev.message, {
            detail: ev.error_type,
            severity: "error",
          }),
        );
        break;
      }

      case "audit.fallback_triggered": {
        set({ runtimeMode: ev.target_mode });
        pushActivity(
          makeActivity(ev, "fallback", `Fallback → ${ev.target_mode}`, {
            detail: ev.reason,
          }),
        );
        break;
      }
    }
  },
}));

export const AGENT_LIST: AgentName[] = AGENTS;
