import { useAudit } from "../../state/audit";
import type { Severity } from "../../types/schemas";
import { SEVERITY_META, VALIDATION_META } from "../../util/tokens";
import { SeverityBadge } from "../atoms";

const SEV_ORDER: Severity[] = ["critical", "high", "medium", "low", "info"];

export function FindingsSidebar() {
  const findings = useAudit((s) => s.findings);
  const order = useAudit((s) => s.findingOrder);
  const validations = useAudit((s) => s.validations);
  const openFile = useAudit((s) => s.openFile);

  const counts: Record<Severity, number> = {
    critical: 0,
    high: 0,
    medium: 0,
    low: 0,
    info: 0,
  };
  for (const id of order) {
    const f = findings[id];
    if (f) counts[f.severity] = (counts[f.severity] ?? 0) + 1;
  }

  return (
    <aside
      className="flex flex-col h-full"
      style={{
        width: 340,
        borderLeft: "1px solid var(--rib-line)",
        background: "var(--rib-bg1)",
      }}
    >
      <div
        className="px-4 py-3"
        style={{ borderBottom: "1px solid var(--rib-line)" }}
      >
        <div
          className="text-[11px] font-semibold uppercase mb-2"
          style={{
            color: "var(--rib-text2)",
            letterSpacing: "0.14em",
          }}
        >
          Findings
        </div>
        <div className="flex flex-wrap items-center gap-1">
          {SEV_ORDER.map((s) => {
            const m = SEVERITY_META[s];
            const n = counts[s];
            return (
              <div
                key={s}
                className="flex items-center gap-[5px] px-[6px] py-[3px]"
                style={{
                  borderRadius: 3,
                  background: n ? m.bg : "transparent",
                  border: `1px solid ${n ? m.line : "var(--rib-line)"}`,
                  opacity: n ? 1 : 0.45,
                }}
              >
                <span
                  style={{
                    width: 6,
                    height: 6,
                    borderRadius: 1,
                    background: m.fg,
                  }}
                />
                <span
                  style={{
                    fontSize: 11,
                    color: "var(--rib-text1)",
                    textTransform: "uppercase",
                    letterSpacing: "0.04em",
                  }}
                >
                  {s.slice(0, 3)}
                </span>
                <span
                  className="font-mono tabular-nums"
                  style={{
                    fontSize: 11.5,
                    color: "var(--rib-text0)",
                    fontWeight: 600,
                  }}
                >
                  {n}
                </span>
              </div>
            );
          })}
        </div>
      </div>
      <ol
        className="flex-1 overflow-auto rib-scrollbar flex flex-col"
        style={{ padding: 0 }}
      >
        {order.map((id) => {
          const f = findings[id];
          if (!f) return null;
          const v = validations[id];
          const vMeta = v ? VALIDATION_META[v.verdict] : null;
          return (
            <li
              key={id}
              className="cursor-pointer"
              onClick={() => {
                if (f.code_span)
                  void openFile(
                    f.code_span.file_path,
                    f.code_span.line_start,
                    f.code_span.line_end,
                  );
              }}
              style={{
                padding: "10px 14px",
                borderBottom: "1px solid var(--rib-line)",
                transition: "background 0.15s",
              }}
              onMouseOver={(e) => {
                (e.currentTarget as HTMLElement).style.background =
                  "var(--rib-bg2)";
              }}
              onMouseOut={(e) => {
                (e.currentTarget as HTMLElement).style.background =
                  "transparent";
              }}
            >
              <div className="flex items-center gap-2 mb-1">
                <SeverityBadge level={f.severity} size="sm" />
                {vMeta && (
                  <span
                    className="inline-flex items-center gap-1"
                    style={{
                      fontSize: 10.5,
                      color: vMeta.fg,
                      fontWeight: 600,
                      letterSpacing: "0.06em",
                      textTransform: "uppercase",
                    }}
                  >
                    <span
                      style={{
                        width: 6,
                        height: 6,
                        borderRadius: 3,
                        background: vMeta.fill ? vMeta.fg : "transparent",
                        boxShadow: vMeta.fill
                          ? undefined
                          : `inset 0 0 0 1.5px ${vMeta.fg}`,
                      }}
                    />
                    {vMeta.label}
                  </span>
                )}
              </div>
              <div
                style={{
                  color: "var(--rib-text0)",
                  fontSize: 13,
                  lineHeight: "18px",
                  fontWeight: 500,
                }}
                className="text-pretty"
              >
                {f.title}
              </div>
              {f.code_span && (
                <div
                  className="font-mono mt-1"
                  style={{
                    color: "var(--rib-text2)",
                    fontSize: 11.5,
                  }}
                >
                  {f.code_span.file_path}:{f.code_span.line_start}
                  {f.code_span.line_end !== f.code_span.line_start &&
                    `-${f.code_span.line_end}`}
                </div>
              )}
            </li>
          );
        })}
        {order.length === 0 && (
          <li
            style={{
              padding: "40px 14px",
              textAlign: "center",
              color: "var(--rib-text3)",
              fontSize: 13,
            }}
          >
            No findings yet.
          </li>
        )}
      </ol>
    </aside>
  );
}
