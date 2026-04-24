import { useEffect, useMemo, useRef, useState } from "react";
import type {
  ClaimVerification,
  DiagnosticReport,
  Severity,
  ValidationResult,
} from "../../types/schemas";
import { useAudit } from "../../state/audit";
import { ClaimsTable } from "./ClaimsTable";
import { ConfigComparison } from "./ConfigComparison";
import { DisagreementsPanel } from "./DisagreementsPanel";
import { EDASummary } from "./EDASummary";
import { FindingCard } from "./FindingCard";
import { Markdown } from "../atoms/Markdown";
import { PipelineDiagram } from "./PipelineDiagram";
import { RecommendationsList } from "./RecommendationsList";
import { ReportFooter } from "./ReportFooter";
import { SectionHeader } from "./SectionHeader";
import { SideNav, type NavSection } from "./SideNav";
import { VerdictBanner } from "./VerdictBanner";

interface Props {
  report: DiagnosticReport;
}

type FilterKey = "all" | Severity;

const SEV_ORDER: Record<Severity, number> = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
  info: 4,
};

export function ReportScreen({ report }: Props) {
  const [filter, setFilter] = useState<FilterKey>("all");
  const [active, setActive] = useState<string>("summary");
  const validations = useAudit((s) => s.validations);
  const mainRef = useRef<HTMLElement | null>(null);

  const sections: NavSection[] = useMemo(
    () => [
      { id: "summary", label: "Executive summary" },
      { id: "pipeline", label: "ML pipeline" },
      {
        id: "claims",
        label: "Claims",
        count: report.claim_verifications.length,
      },
      { id: "findings", label: "Findings", count: report.findings.length },
      {
        id: "config",
        label: "Config comparison",
        count: report.config_comparison.length,
      },
      { id: "eda", label: "Data (EDA)" },
      {
        id: "recs",
        label: "Recommendations",
        count: report.recommendations.length,
      },
      ...((report.unresolved_disagreements?.length ?? 0) > 0
        ? [
            {
              id: "disagreements",
              label: "Disagreements",
              count: report.unresolved_disagreements!.length,
            },
          ]
        : []),
    ],
    [report],
  );

  const sortedFindings = useMemo(() => {
    return [...report.findings].sort((a, b) => {
      const da = SEV_ORDER[a.severity] ?? 9;
      const db = SEV_ORDER[b.severity] ?? 9;
      if (da !== db) return da - db;
      return b.confidence - a.confidence;
    });
  }, [report.findings]);

  const computedCounts = useMemo(() => {
    const have =
      report.severity_counts && Object.keys(report.severity_counts).length > 0;
    if (have) return report.severity_counts ?? {};
    const out: Record<string, number> = {
      critical: 0,
      high: 0,
      medium: 0,
      low: 0,
      info: 0,
    };
    for (const f of report.findings)
      out[f.severity] = (out[f.severity] ?? 0) + 1;
    return out;
  }, [report.severity_counts, report.findings]);

  const reportWithCounts = useMemo(
    () => ({ ...report, severity_counts: computedCounts }),
    [report, computedCounts],
  );

  const filteredFindings = useMemo(() => {
    if (filter === "all") return sortedFindings;
    return sortedFindings.filter((f) => f.severity === filter);
  }, [filter, sortedFindings]);

  // Lets FindingCard render a finding's paper_claim_refs as the human
  // readable claim text instead of the bare "claim_001" id.
  const claimsById = useMemo(() => {
    const out: Record<string, ClaimVerification> = {};
    for (const c of report.claim_verifications) out[c.claim_id] = c;
    return out;
  }, [report.claim_verifications]);

  const scrollTo = (id: string) => {
    setActive(id);
    const el = document.getElementById(id);
    const container = mainRef.current;
    if (el && container) {
      // Scroll within the report's own scrollable main, not the viewport.
      const y = el.offsetTop - 12;
      container.scrollTo({ top: y, behavior: "smooth" });
    } else if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  };

  // Track which section is in view to light up the side nav.
  useEffect(() => {
    const container = mainRef.current;
    if (!container) return;
    const ids = sections.map((s) => s.id);
    const onScroll = () => {
      let best = ids[0];
      let bestOffset = -Infinity;
      for (const id of ids) {
        const el = document.getElementById(id);
        if (!el) continue;
        const top = el.offsetTop - container.scrollTop;
        if (top <= 80 && top > bestOffset) {
          best = id;
          bestOffset = top;
        }
      }
      if (best && best !== active) setActive(best);
    };
    container.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
    return () => container.removeEventListener("scroll", onScroll);
  }, [sections, active]);

  return (
    <div
      className="h-full"
      style={{
        display: "grid",
        gridTemplateColumns: "232px 1fr",
        background: "var(--rib-bg0)",
      }}
    >
      <SideNav
        report={reportWithCounts}
        sections={sections}
        active={active}
        onNavigate={scrollTo}
      />
      <main
        ref={mainRef}
        className="overflow-y-auto rib-scrollbar"
        style={{ minWidth: 0, height: "100%" }}
      >
        <VerdictBanner report={reportWithCounts} />

        <section id="summary" style={{ padding: "36px 48px 36px" }}>
          <SectionHeader eyebrow="§ 1" title="Executive summary" />
          <div
            className="text-pretty"
            style={{
              maxWidth: 720,
              fontSize: 15,
              lineHeight: "26px",
              color: "var(--rib-text1)",
            }}
          >
            <Markdown src={report.executive_summary} />
          </div>
        </section>

        <section id="pipeline" style={{ padding: "10px 48px 36px" }}>
          <SectionHeader
            eyebrow="§ 2"
            title="ML pipeline"
            count="findings bucketed by stage"
          />
          <PipelineDiagram findings={report.findings} onJumpToFinding={scrollTo} />
        </section>

        <section id="claims" style={{ padding: "10px 48px 36px" }}>
          <SectionHeader
            eyebrow="§ 3"
            title="Claim verifications"
            count={`${report.claim_verifications.length} claims`}
          />
          <ClaimsTable claims={report.claim_verifications} />
        </section>

        <section id="findings" style={{ padding: "10px 48px 36px" }}>
          <SectionHeader
            eyebrow="§ 4"
            title="Findings"
            count={`${report.findings.length} total · sorted by severity`}
            right={
              <FilterRow
                value={filter}
                onChange={setFilter}
                counts={computedCounts}
              />
            }
          />
          <div className="flex flex-col gap-[10px]">
            {filteredFindings.map((f) => (
              <FindingCard
                key={f.id}
                finding={f}
                validation={lookupValidation(validations, f.id)}
                claimsById={claimsById}
                defaultOpen={false}
              />
            ))}
            {filteredFindings.length === 0 && (
              <div
                className="p-6 rounded-lg text-center"
                style={{
                  border: "1px dashed var(--rib-line2)",
                  background: "var(--rib-bg1)",
                  color: "var(--rib-text2)",
                }}
              >
                No findings match this filter.
              </div>
            )}
          </div>
        </section>

        <section id="config" style={{ padding: "10px 48px 36px" }}>
          <SectionHeader
            eyebrow="§ 5"
            title="Config comparison"
            count={`${report.config_comparison.filter((r) => !r.match).length} mismatches / ${report.config_comparison.length}`}
          />
          <ConfigComparison rows={report.config_comparison} />
        </section>

        <section id="eda" style={{ padding: "10px 48px 36px" }}>
          <SectionHeader eyebrow="§ 6" title="Data (EDA)" />
          <EDASummary eda={report.eda_summary} empty={!report.eda_summary} />
        </section>

        <section id="recs" style={{ padding: "10px 48px 36px" }}>
          <SectionHeader
            eyebrow="§ 7"
            title="Recommendations"
            count={`${report.recommendations.length} ranked`}
          />
          <RecommendationsList items={report.recommendations} />
        </section>

        {(report.unresolved_disagreements?.length ?? 0) > 0 && (
          <section id="disagreements" style={{ padding: "10px 48px 36px" }}>
            <SectionHeader
              eyebrow="§ 8"
              title="Unresolved disagreements"
              count={`${report.unresolved_disagreements!.length} surfaced`}
            />
            <DisagreementsPanel items={report.unresolved_disagreements!} />
          </section>
        )}

        <ReportFooter report={report} />
      </main>
    </div>
  );
}

function FilterRow({
  value,
  onChange,
  counts,
}: {
  value: FilterKey;
  onChange: (v: FilterKey) => void;
  counts: Record<string, number>;
}) {
  const keys: FilterKey[] = [
    "all",
    "critical",
    "high",
    "medium",
    "low",
    "info",
  ];
  return (
    <div className="flex items-center gap-[6px]" style={{ fontSize: 12 }}>
      {keys.map((k) => {
        const active = value === k;
        return (
          <button
            key={k}
            type="button"
            onClick={() => onChange(k)}
            className="font-ui capitalize"
            style={{
              padding: "4px 10px",
              borderRadius: 4,
              cursor: "pointer",
              color: active ? "var(--rib-text0)" : "var(--rib-text2)",
              background: active ? "var(--rib-bg3)" : "transparent",
              border: `1px solid ${active ? "var(--rib-line2)" : "transparent"}`,
              fontSize: 12,
            }}
          >
            {k}
            {k !== "all" && counts[k] != null && (
              <span style={{ color: "var(--rib-text3)", marginLeft: 6 }}>
                {counts[k]}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

function lookupValidation(
  vals: Record<string, ValidationResult>,
  findingId: string,
): ValidationResult | undefined {
  return vals[findingId];
}
