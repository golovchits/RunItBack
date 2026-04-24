import type { DiagnosticReport, Severity } from "../../types/schemas";
import { SEVERITY_META, VERDICT_META } from "../../util/tokens";
import { formatDuration, formatIsoTimeUTC } from "../../util/format";
import { Pill } from "../atoms";

const SEV_ORDER: Severity[] = ["critical", "high", "medium", "low", "info"];

interface Props {
  report: DiagnosticReport;
  compact?: boolean;
}

export function VerdictBanner({ report, compact }: Props) {
  const v = VERDICT_META[report.verdict];
  const confidencePct = Math.round(report.confidence * 100);
  const sev = report.severity_counts ?? {};

  return (
    <div
      style={{
        position: "relative",
        background: "var(--rib-bg1)",
        borderBottom: "1px solid var(--rib-line)",
      }}
    >
      <div
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          right: 0,
          height: 3,
          background: v.fg,
          boxShadow: `0 0 24px ${v.fg}44`,
        }}
      />
      <div
        style={{
          position: "absolute",
          inset: 0,
          pointerEvents: "none",
          background: `radial-gradient(600px 180px at 10% 0%, ${v.fg}14, transparent 70%)`,
        }}
      />
      <div
        className="relative grid items-end gap-8"
        style={{
          padding: compact ? "22px 40px 26px" : "32px 48px 36px",
          gridTemplateColumns: "1fr auto",
        }}
      >
        <div className="min-w-0">
          <div className="flex items-center gap-3 mb-3">
            <div
              className="inline-flex items-center gap-[10px]"
              style={{
                padding: "5px 12px 5px 10px",
                background: `${v.fg}12`,
                border: `1px solid ${v.fg}55`,
                borderRadius: 4,
              }}
            >
              <span
                style={{
                  width: 8,
                  height: 8,
                  borderRadius: 4,
                  background: v.fg,
                  boxShadow: `0 0 0 3px ${v.fg}22`,
                }}
              />
              <span
                className="font-semibold uppercase"
                style={{
                  color: v.fg,
                  fontSize: 12,
                  letterSpacing: "0.14em",
                }}
              >
                VERDICT · {v.short}
              </span>
            </div>
            <Pill mono tone="neutral">
              <span
                className="mr-1"
                style={{ color: "var(--rib-text2)" }}
              >
                id
              </span>
              {report.audit_id}
            </Pill>
          </div>
          <h1
            className="font-semibold text-pretty"
            style={{
              fontSize: compact ? 22 : 28,
              lineHeight: compact ? "30px" : "36px",
              letterSpacing: "-0.02em",
              color: "var(--rib-text0)",
              margin: 0,
              maxWidth: 820,
            }}
          >
            {report.headline}
          </h1>
        </div>

        <div
          className="grid items-end"
          style={{
            gridTemplateColumns: "auto auto auto",
            gap: compact ? 18 : 28,
          }}
        >
          <Stat label="CONFIDENCE" value={`${confidencePct}%`} big />
          <Stat label="RUNTIME" value={formatDuration(report.runtime_ms_total)} />
          <Stat
            label="GENERATED"
            value={formatIsoTimeUTC(report.generated_at)}
            mono
          />
        </div>
      </div>

      {!compact && (
        <div
          className="flex items-stretch"
          style={{
            borderTop: "1px solid var(--rib-line)",
            background: "var(--rib-bg0)",
          }}
        >
          {SEV_ORDER.map((s) => (
            <SevCount key={s} level={s} n={sev[s] ?? 0} />
          ))}
          <div className="flex-1" />
          <div
            className="flex items-center gap-[10px] px-10 py-[10px]"
            style={{ color: "var(--rib-text2)", fontSize: 12 }}
          >
            <span>
              4 agents ·{" "}
              {report.runtime_mode_used === "managed_agents"
                ? "Managed Agents"
                : "Messages API"}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}

function Stat({
  label,
  value,
  big,
  mono,
}: {
  label: string;
  value: string;
  big?: boolean;
  mono?: boolean;
}) {
  return (
    <div>
      <div
        className="mb-[6px] font-semibold uppercase"
        style={{
          fontSize: 10.5,
          letterSpacing: "0.14em",
          color: "var(--rib-text2)",
        }}
      >
        {label}
      </div>
      <div
        className={`tabular-nums ${mono ? "font-mono" : "font-ui"}`}
        style={{
          fontSize: big ? 30 : 17,
          fontWeight: big ? 600 : 500,
          color: "var(--rib-text0)",
          letterSpacing: big ? "-0.02em" : 0,
          lineHeight: 1,
        }}
      >
        {value}
      </div>
    </div>
  );
}

function SevCount({ level, n }: { level: Severity; n: number }) {
  const m = SEVERITY_META[level];
  const zero = !n;
  return (
    <div
      className="flex items-center gap-[10px]"
      style={{
        padding: "10px 24px",
        borderRight: "1px solid var(--rib-line)",
        opacity: zero ? 0.45 : 1,
      }}
    >
      <span
        style={{
          width: 8,
          height: 8,
          borderRadius: 1,
          background: m.fg,
        }}
      />
      <span
        className="uppercase"
        style={{
          fontSize: 12,
          color: "var(--rib-text1)",
          letterSpacing: "0.02em",
          fontWeight: 500,
        }}
      >
        {m.label}
      </span>
      <span
        className="font-mono tabular-nums font-semibold"
        style={{ fontSize: 13, color: "var(--rib-text0)" }}
      >
        {n}
      </span>
    </div>
  );
}
