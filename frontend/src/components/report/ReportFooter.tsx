import type { DiagnosticReport } from "../../types/schemas";
import { formatDuration, formatIsoTimeUTC } from "../../util/format";
import { Pill } from "../atoms";

interface Props {
  report: DiagnosticReport;
}

export function ReportFooter({ report }: Props) {
  return (
    <div
      className="flex items-center gap-[14px] flex-wrap px-12 py-[18px]"
      style={{
        borderTop: "1px solid var(--rib-line)",
        background: "var(--rib-bg1)",
        color: "var(--rib-text2)",
        fontSize: 12.5,
      }}
    >
      <Pill tone="strong">
        {report.runtime_mode_used === "managed_agents"
          ? "Managed Agents"
          : "Messages API"}
      </Pill>
      <span>
        duration{" "}
        <span className="font-mono" style={{ color: "var(--rib-text0)" }}>
          {formatDuration(report.runtime_ms_total)}
        </span>
      </span>
      <span style={{ color: "var(--rib-text3)" }}>·</span>
      <span>
        generated{" "}
        <span className="font-mono" style={{ color: "var(--rib-text0)" }}>
          {formatIsoTimeUTC(report.generated_at)}
        </span>
      </span>
      <span style={{ color: "var(--rib-text3)" }}>·</span>
      <span className="font-mono">{report.audit_id}</span>
    </div>
  );
}
