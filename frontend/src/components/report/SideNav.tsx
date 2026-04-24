import type { DiagnosticReport, Severity } from "../../types/schemas";
import { SEVERITY_META } from "../../util/tokens";

const SEV_ORDER: Severity[] = ["critical", "high", "medium", "low", "info"];

export interface NavSection {
  id: string;
  label: string;
  count?: number;
}

interface Props {
  report: DiagnosticReport;
  sections: NavSection[];
  active: string;
  onNavigate: (id: string) => void;
}

/**
 * Report table of contents. Lives inside the report's grid column and takes
 * the container's full height, with its own overflow. The ReportScreen's
 * main column scrolls independently, which gets us "sidenav stays put"
 * without relying on position: sticky.
 */
export function SideNav({ report, sections, active, onNavigate }: Props) {
  return (
    <nav
      className="rib-scrollbar overflow-y-auto"
      style={{
        padding: "24px 18px 24px 28px",
        borderRight: "1px solid var(--rib-line)",
        background: "var(--rib-bg0)",
        height: "100%",
      }}
    >
      <div
        className="text-[11px] font-semibold uppercase mb-4"
        style={{
          color: "var(--rib-text3)",
          letterSpacing: "0.14em",
        }}
      >
        Report
      </div>

      <ul className="m-0 p-0 list-none flex flex-col gap-[2px]">
        {sections.map((s) => {
          const isActive = s.id === active;
          return (
            <li key={s.id}>
              <a
                href={`#${s.id}`}
                onClick={(e) => {
                  e.preventDefault();
                  onNavigate(s.id);
                }}
                className="grid items-center"
                style={{
                  gridTemplateColumns: "1fr auto",
                  padding: "6px 10px",
                  borderRadius: 5,
                  textDecoration: "none",
                  color: isActive ? "var(--rib-text0)" : "var(--rib-text2)",
                  background: isActive ? "var(--rib-bg2)" : "transparent",
                  fontSize: 13,
                  fontWeight: isActive ? 500 : 400,
                  borderLeft: `2px solid ${
                    isActive ? "var(--rib-agent-auditor)" : "transparent"
                  }`,
                  marginLeft: -10,
                  paddingLeft: 10,
                }}
              >
                <span>{s.label}</span>
                {s.count != null && (
                  <span
                    className="font-mono tabular-nums"
                    style={{ fontSize: 11, color: "var(--rib-text3)" }}
                  >
                    {s.count}
                  </span>
                )}
              </a>
            </li>
          );
        })}
      </ul>

      {report.severity_counts && (
        <div
          className="mt-7 pt-5"
          style={{ borderTop: "1px solid var(--rib-line)" }}
        >
          <div
            className="mb-[10px] font-semibold uppercase"
            style={{
              fontSize: 10.5,
              letterSpacing: "0.14em",
              color: "var(--rib-text3)",
            }}
          >
            Severity
          </div>
          {SEV_ORDER.map((k) => {
            const m = SEVERITY_META[k];
            const n = report.severity_counts?.[k] ?? 0;
            return (
              <div
                key={k}
                className="flex items-center gap-2 py-[3px]"
                style={{ opacity: n ? 1 : 0.5 }}
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
                  className="flex-1"
                  style={{ fontSize: 12, color: "var(--rib-text1)" }}
                >
                  {m.label}
                </span>
                <span
                  className="font-mono tabular-nums"
                  style={{ fontSize: 12, color: "var(--rib-text0)" }}
                >
                  {n}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </nav>
  );
}
