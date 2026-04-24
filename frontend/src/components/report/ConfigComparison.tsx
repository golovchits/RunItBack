import type { ConfigDiscrepancy } from "../../types/schemas";
import { SEVERITY_META } from "../../util/tokens";
import { SeverityBadge } from "../atoms";

interface Props {
  rows: ConfigDiscrepancy[];
}

export function ConfigComparison({ rows }: Props) {
  if (rows.length === 0) {
    return (
      <div
        className="p-6 rounded-lg text-center"
        style={{
          border: "1px dashed var(--rib-line2)",
          background: "var(--rib-bg1)",
          color: "var(--rib-text2)",
        }}
      >
        No config comparison available.
      </div>
    );
  }
  return (
    <div
      className="overflow-hidden"
      style={{
        border: "1px solid var(--rib-line)",
        borderRadius: 8,
        background: "var(--rib-bg1)",
      }}
    >
      <div
        className="grid px-4 py-[10px] font-semibold uppercase"
        style={{
          gridTemplateColumns: "1.2fr 1fr 1fr 1.2fr 86px",
          background: "var(--rib-bg2)",
          borderBottom: "1px solid var(--rib-line)",
          fontSize: 11,
          letterSpacing: "0.12em",
          color: "var(--rib-text2)",
          gap: 12,
        }}
      >
        <div>Parameter</div>
        <div>Paper value</div>
        <div>Code value</div>
        <div>Location</div>
        <div className="text-right">Severity</div>
      </div>
      {rows.map((r, i) => {
        const sev = SEVERITY_META[r.severity];
        const tint = !r.match ? `${sev.fg}0d` : "transparent";
        return (
          <div
            key={i}
            className="grid items-center gap-3"
            style={{
              gridTemplateColumns: "1.2fr 1fr 1fr 1.2fr 86px",
              padding: "12px 16px",
              borderTop: i === 0 ? "none" : "1px solid var(--rib-line)",
              background: tint,
            }}
          >
            <div
              className="font-mono flex items-center gap-2"
              style={{
                fontSize: 12.5,
                color: "var(--rib-text0)",
              }}
            >
              {!r.match && (
                <span
                  style={{
                    width: 6,
                    height: 6,
                    borderRadius: 1,
                    background: sev.fg,
                  }}
                />
              )}
              {r.match && (
                <span
                  style={{
                    width: 6,
                    height: 6,
                    borderRadius: 3,
                    border: "1px solid var(--rib-line2)",
                  }}
                />
              )}
              {r.parameter}
            </div>
            <div
              className="font-mono"
              style={{ fontSize: 12.5, color: "var(--rib-text1)" }}
            >
              {r.paper_value ?? "—"}
            </div>
            <div
              className="font-mono"
              style={{
                fontSize: 12.5,
                color: r.match ? "var(--rib-text1)" : sev.fg,
                fontWeight: r.match ? 400 : 500,
              }}
            >
              {r.code_value ?? "—"}
            </div>
            <div
              className="font-mono"
              style={{
                fontSize: 12,
                color: "var(--rib-text2)",
                wordBreak: "break-all",
              }}
            >
              {r.code_location ?? "—"}
            </div>
            <div className="text-right">
              {r.match ? (
                <span
                  className="font-ui font-medium"
                  style={{
                    fontSize: 11.5,
                    color: "var(--rib-text3)",
                    letterSpacing: "0.06em",
                  }}
                >
                  MATCH
                </span>
              ) : (
                <SeverityBadge level={r.severity} size="sm" />
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
