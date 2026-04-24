import type { ReactNode } from "react";
import { Pill } from "./atoms";
import { Logo } from "./atoms/Logo";
import { useAudit } from "../state/audit";

export type HeaderView = "input" | "live" | "report";

interface Props {
  view: HeaderView;
  onSwitchView?: (view: HeaderView) => void;
  onExportJson?: () => void;
  onNewAudit?: () => void;
  onCancel?: () => void;
  right?: ReactNode;
}

/**
 * App-level chrome. Shows logo, full audit id, runtime-mode pill, and — when
 * both a live audit and a completed report are available — a tab switcher
 * between the two views. Export JSON and New audit actions live here too.
 */
export function Header({
  view,
  onSwitchView,
  onExportJson,
  onNewAudit,
  onCancel,
  right,
}: Props) {
  const auditId = useAudit((s) => s.auditId);
  const runtimeMode = useAudit((s) => s.runtimeMode);
  const report = useAudit((s) => s.report);
  const activity = useAudit((s) => s.activity);
  const phase = useAudit((s) => s.phase);

  const hasLive = activity.length > 0 || phase === "failed";
  const hasReport = report != null;
  const showTabs = (hasLive || hasReport) && view !== "input";

  return (
    <header
      className="flex items-center gap-3 px-5 py-[10px]"
      style={{
        borderBottom: "1px solid var(--rib-line)",
        background: "var(--rib-bg0)",
        flexShrink: 0,
      }}
    >
      <Logo size={22} />
      <div className="leading-none mr-2">
        <div
          className="text-[13px] font-semibold tracking-tight"
          style={{ color: "var(--rib-text0)" }}
        >
          RunItBack
        </div>
        <div
          className="mt-[3px] text-[10.5px] uppercase"
          style={{
            color: "var(--rib-text2)",
            letterSpacing: "0.08em",
          }}
        >
          ML reproducibility audits
        </div>
      </div>

      {showTabs && onSwitchView && (
        <div
          className="inline-flex items-center gap-[2px] p-[3px]"
          style={{
            background: "var(--rib-bg2)",
            border: "1px solid var(--rib-line)",
            borderRadius: 6,
          }}
        >
          <HeaderTab
            active={view === "live"}
            onClick={() => onSwitchView("live")}
            disabled={!hasLive}
          >
            Live
            {phase &&
              phase !== "done" &&
              phase !== "failed" &&
              phase !== "created" && (
                <span
                  style={{
                    width: 6,
                    height: 6,
                    borderRadius: 3,
                    background: "var(--rib-agent-auditor)",
                    animation: "ribPulse 1.6s ease-in-out infinite",
                  }}
                />
              )}
          </HeaderTab>
          <HeaderTab
            active={view === "report"}
            onClick={() => onSwitchView("report")}
            disabled={!hasReport}
          >
            Report
            {hasReport && report && (
              <span
                style={{
                  fontSize: 11,
                  color: "var(--rib-text3)",
                  fontFamily:
                    "JetBrains Mono, ui-monospace, SFMono-Regular, Menlo, monospace",
                }}
              >
                {report.findings.length}
              </span>
            )}
          </HeaderTab>
        </div>
      )}

      <div className="flex-1" />

      {auditId && (
        <div className="flex items-center gap-2 min-w-0">
          <span
            className="text-[10.5px] font-semibold uppercase"
            style={{
              color: "var(--rib-text3)",
              letterSpacing: "0.14em",
            }}
          >
            audit
          </span>
          <Pill mono tone="neutral">
            <span className="font-mono">{auditId}</span>
          </Pill>
        </div>
      )}
      {runtimeMode && (
        <Pill tone="strong">
          {runtimeMode === "managed_agents" ? "Managed Agents" : "Messages API"}
        </Pill>
      )}

      {onExportJson && (
        <HeaderButton onClick={onExportJson} primary>
          Download report
        </HeaderButton>
      )}
      {onCancel && (
        <HeaderButton onClick={onCancel}>Cancel</HeaderButton>
      )}
      {onNewAudit && (
        <HeaderButton onClick={onNewAudit}>New audit</HeaderButton>
      )}
      {right}

      <style>{`
        @keyframes ribPulse { 0%, 100% { opacity: 1 } 50% { opacity: 0.45 } }
      `}</style>
    </header>
  );
}

function HeaderTab({
  active,
  onClick,
  disabled,
  children,
}: {
  active: boolean;
  onClick: () => void;
  disabled?: boolean;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="font-ui inline-flex items-center gap-[8px]"
      style={{
        padding: "5px 12px",
        borderRadius: 4,
        fontSize: 12.5,
        fontWeight: active ? 600 : 500,
        color: active
          ? "var(--rib-text0)"
          : disabled
            ? "var(--rib-text3)"
            : "var(--rib-text2)",
        background: active ? "var(--rib-bg4)" : "transparent",
        border: `1px solid ${active ? "var(--rib-line2)" : "transparent"}`,
        cursor: disabled ? "not-allowed" : "pointer",
        transition: "all 0.15s",
        opacity: disabled ? 0.6 : 1,
      }}
    >
      {children}
    </button>
  );
}

function HeaderButton({
  onClick,
  primary,
  children,
}: {
  onClick: () => void;
  primary?: boolean;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="font-ui font-medium"
      style={{
        padding: "7px 14px",
        borderRadius: 6,
        background: primary ? "var(--rib-bg4)" : "transparent",
        color: primary ? "var(--rib-text0)" : "var(--rib-text1)",
        border: `1px solid ${primary ? "var(--rib-line2)" : "var(--rib-line)"}`,
        fontSize: 12.5,
        cursor: "pointer",
      }}
    >
      {children}
    </button>
  );
}
