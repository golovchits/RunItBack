import { useEffect, useState } from "react";
import { AGENT_LIST, useAudit } from "../../state/audit";
import type { AgentName } from "../../types/schemas";
import { AGENT_META } from "../../util/tokens";
import { formatDurationShort } from "../../util/format";

export function PipelineSidebar() {
  const current = useAudit((s) => s.currentAgent);
  const phase = useAudit((s) => s.phase);
  const findings = useAudit((s) => s.findingOrder);

  return (
    <aside
      className="flex flex-col h-full"
      style={{
        width: 260,
        borderRight: "1px solid var(--rib-line)",
        background: "var(--rib-bg1)",
      }}
    >
      <div
        className="px-5 py-4"
        style={{ borderBottom: "1px solid var(--rib-line)" }}
      >
        <div
          className="text-[11px] font-semibold uppercase mb-2"
          style={{
            color: "var(--rib-text2)",
            letterSpacing: "0.14em",
          }}
        >
          Pipeline
        </div>
        <div
          className="text-[13px]"
          style={{ color: "var(--rib-text1)" }}
        >
          {phase === "normalizing" && "Resolving inputs…"}
          {phase === "paper_analyst" && "Extracting paper claims…"}
          {phase === "code_auditor" && "Reading the code & data…"}
          {phase === "validator" && "Running targeted checks…"}
          {phase === "reviewer" && "Assembling report…"}
          {phase === "done" && "Complete."}
          {phase === "failed" && (
            <span style={{ color: "var(--rib-critical)" }}>Failed.</span>
          )}
        </div>
      </div>
      <ol className="flex flex-col gap-[2px] p-3">
        {AGENT_LIST.map((name, i) => (
          <AgentStatusRow
            key={name}
            agent={name}
            isCurrent={current === name}
            index={i}
          />
        ))}
      </ol>
      <div
        className="mt-auto px-5 py-4 flex items-center gap-4"
        style={{
          borderTop: "1px solid var(--rib-line)",
          color: "var(--rib-text2)",
          fontSize: 12,
        }}
      >
        <div className="flex items-center gap-2">
          <span
            style={{
              width: 6,
              height: 6,
              borderRadius: 3,
              background: "var(--rib-critical)",
            }}
          />
          <span className="font-mono tabular-nums" style={{ color: "var(--rib-text0)" }}>
            {findings.length}
          </span>
          <span>findings</span>
        </div>
      </div>
    </aside>
  );
}

function AgentStatusRow({
  agent,
  isCurrent,
}: {
  agent: AgentName;
  isCurrent: boolean;
  index: number;
}) {
  const state = useAudit((s) => s.agents[agent]);
  const meta = AGENT_META[agent];
  const [now, setNow] = useState(() => Date.now());

  // tick once per second while running so the timer updates live
  useEffect(() => {
    if (state.status !== "running") return;
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [state.status]);

  const elapsed =
    state.status === "running" && state.startedAt
      ? Math.max(0, now - new Date(state.startedAt).getTime())
      : state.durationMs ?? 0;

  const dot =
    state.status === "done"
      ? meta.fg
      : state.status === "running"
        ? meta.fg
        : state.status === "failed"
          ? "var(--rib-critical)"
          : "var(--rib-text3)";

  return (
    <li
      className="flex items-center gap-3 p-3 rounded-md"
      style={{
        background: isCurrent ? "var(--rib-bg2)" : "transparent",
        border: `1px solid ${isCurrent ? "var(--rib-line2)" : "transparent"}`,
        transition: "all 0.15s",
      }}
    >
      <span
        style={{
          width: 10,
          height: 10,
          borderRadius: 5,
          background: state.status === "idle" ? "transparent" : dot,
          boxShadow:
            state.status === "idle"
              ? `inset 0 0 0 1.5px ${dot}`
              : `0 0 0 3px ${meta.fg}22`,
          animation:
            state.status === "running"
              ? "ribPulse 1.6s ease-in-out infinite"
              : undefined,
          flexShrink: 0,
        }}
      />
      <div className="flex-1 min-w-0">
        <div
          className="text-[13px] font-ui"
          style={{
            color: isCurrent ? "var(--rib-text0)" : "var(--rib-text1)",
            fontWeight: isCurrent ? 600 : 500,
          }}
        >
          {meta.label}
        </div>
        <div
          className="mt-[2px] text-[11.5px] font-mono tabular-nums"
          style={{ color: "var(--rib-text2)" }}
        >
          {state.status === "idle" && "waiting"}
          {state.status === "running" && `running · ${formatDurationShort(elapsed)}`}
          {state.status === "done" &&
            `done · ${formatDurationShort(elapsed)}`}
          {state.status === "failed" && "failed"}
        </div>
      </div>
      <style>{`
        @keyframes ribPulse { 0%, 100% { opacity: 1 } 50% { opacity: 0.45 } }
      `}</style>
    </li>
  );
}
