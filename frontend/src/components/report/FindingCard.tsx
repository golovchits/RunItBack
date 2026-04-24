import { useState } from "react";
import type {
  AuditFinding,
  ClaimVerification,
  Evidence,
  ValidationResult,
} from "../../types/schemas";
import { SEVERITY_META } from "../../util/tokens";
import {
  AgentBadge,
  Chev,
  CodeViewer,
  DiffBlock,
  Markdown,
  Pill,
  SeverityBadge,
  StatusDot,
} from "../atoms";
import { PaperVsCode } from "./PaperVsCode";

interface Props {
  finding: AuditFinding;
  validation?: ValidationResult;
  /** claim_id → verification record, for resolving paper_claim_refs to text. */
  claimsById?: Record<string, ClaimVerification>;
  defaultOpen?: boolean;
}

export function FindingCard({
  finding,
  validation,
  claimsById,
  defaultOpen,
}: Props) {
  const [open, setOpen] = useState(defaultOpen ?? false);
  const sev = SEVERITY_META[finding.severity];
  const confidencePct = Math.round(finding.confidence * 100);

  const agent =
    finding.detector === "validator"
      ? "validator"
      : finding.detector === "reviewer"
        ? "reviewer"
        : "code_auditor";

  const validationVerdict = validation?.verdict ?? finding.validation_verdict;

  return (
    <div
      id={finding.id}
      style={{
        background: "var(--rib-bg1)",
        border: "1px solid var(--rib-line)",
        borderRadius: 8,
        overflow: "hidden",
        transition: "border-color 0.15s",
      }}
    >
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="w-full font-ui text-left grid items-center gap-[14px]"
        style={{
          background: "transparent",
          border: "none",
          color: "inherit",
          padding: "16px 20px",
          gridTemplateColumns: "auto 10px 1fr auto auto auto auto auto",
          cursor: "pointer",
        }}
      >
        <div
          style={{
            width: 3,
            alignSelf: "stretch",
            background: sev.fg,
            borderRadius: 2,
            marginLeft: -4,
          }}
        />
        <Chev open={open} />
        <div className="min-w-0">
          <div className="flex items-center gap-[10px] mb-[3px]">
            <span
              className="font-mono"
              style={{ fontSize: 11, color: "var(--rib-text3)" }}
            >
              {finding.id}
            </span>
            <span style={{ fontSize: 11, color: "var(--rib-text3)" }}>·</span>
            <span
              className="font-mono"
              style={{ fontSize: 11, color: "var(--rib-text2)" }}
            >
              {finding.category}
            </span>
          </div>
          <div
            className="font-semibold text-pretty"
            style={{
              fontSize: 15,
              color: "var(--rib-text0)",
              lineHeight: "22px",
              letterSpacing: "-0.005em",
            }}
          >
            {finding.title}
          </div>
        </div>
        <SeverityBadge level={finding.severity} />
        <StatusDot status={validationVerdict} />
        <div
          className="flex items-center gap-[6px]"
          style={{ fontSize: 12, color: "var(--rib-text2)" }}
        >
          <span style={{ color: "var(--rib-text3)" }}>conf</span>
          <span
            className="font-mono tabular-nums"
            style={{ fontSize: 12.5, color: "var(--rib-text0)" }}
          >
            {confidencePct}%
          </span>
        </div>
        <AgentBadge agent={agent} size="sm" />
        <div />
      </button>

      {open && (
        <div
          style={{
            padding: "6px 20px 22px 36px",
            borderTop: "1px solid var(--rib-line)",
            background: "var(--rib-bg0)",
          }}
        >
          <div style={{ paddingTop: 16, maxWidth: 880 }}>
            <div
              className="text-pretty"
              style={{
                fontSize: 14,
                lineHeight: "22px",
                color: "var(--rib-text1)",
              }}
            >
              <Markdown src={finding.description} />
            </div>

            {(finding.paper_says || finding.code_does) && (
              <PaperVsCode
                paper={finding.paper_says}
                code={finding.code_does}
              />
            )}

            {finding.code_span && (
              <div style={{ marginTop: 4, marginBottom: 16 }}>
                <CodeViewer span={finding.code_span} />
              </div>
            )}

            {finding.suggested_fix_diff && (
              <div style={{ marginBottom: 16 }}>
                <DiffBlock diff={finding.suggested_fix_diff} />
              </div>
            )}
            {!finding.suggested_fix_diff && finding.suggested_fix_prose && (
              <div
                style={{
                  marginBottom: 16,
                  background: "var(--rib-bg2)",
                  border: "1px solid var(--rib-line)",
                  borderLeft: "3px solid var(--rib-reproducible)",
                  borderRadius: 6,
                  padding: "12px 16px",
                }}
              >
                <div
                  className="mb-[6px] font-semibold uppercase"
                  style={{
                    fontSize: 10.5,
                    letterSpacing: "0.14em",
                    color: "var(--rib-reproducible)",
                  }}
                >
                  Suggested fix
                </div>
                <div
                  className="text-pretty"
                  style={{
                    fontSize: 13.5,
                    lineHeight: "21px",
                    color: "var(--rib-text1)",
                  }}
                >
                  {finding.suggested_fix_prose}
                </div>
              </div>
            )}

            {finding.evidence && finding.evidence.length > 0 && (
              <EvidenceBlock items={finding.evidence} />
            )}

            {((finding.paper_claim_refs?.length ?? 0) > 0 ||
              (finding.cross_refs?.length ?? 0) > 0) && (
              <div
                className="flex flex-wrap gap-4 mt-[14px]"
                style={{ fontSize: 12, color: "var(--rib-text2)" }}
              >
                {(finding.paper_claim_refs?.length ?? 0) > 0 && (
                  <div className="flex items-center gap-[6px] flex-wrap">
                    <span
                      style={{
                        fontSize: 11,
                        letterSpacing: "0.08em",
                        color: "var(--rib-text3)",
                        textTransform: "uppercase",
                      }}
                    >
                      Claims
                    </span>
                    {finding.paper_claim_refs!.map((r, i) => {
                      const claim = claimsById?.[r];
                      const summary = claim?.claim_summary?.trim();
                      // Prefer the human claim text; keep the id available
                      // as a tooltip and as a fallback when the lookup
                      // misses (e.g. partial reports).
                      const label = summary
                        ? truncate(summary, 80)
                        : r;
                      const tooltip = summary ? `${r} — ${summary}` : r;
                      return (
                        <Pill
                          key={`${r}-${i}`}
                          mono={!summary}
                          title={tooltip}
                        >
                          {label}
                        </Pill>
                      );
                    })}
                  </div>
                )}
                {(finding.cross_refs?.length ?? 0) > 0 && (
                  <div className="flex items-center gap-[6px]">
                    <span
                      style={{
                        fontSize: 11,
                        letterSpacing: "0.08em",
                        color: "var(--rib-text3)",
                        textTransform: "uppercase",
                      }}
                    >
                      Related
                    </span>
                    {finding.cross_refs!.map((r, i) => (
                      <Pill key={`${r}-${i}`} mono>
                        {r}
                      </Pill>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function EvidenceBlock({ items }: { items: Evidence[] }) {
  const [open, setOpen] = useState(false);
  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="inline-flex items-center gap-[6px] font-ui"
        style={{
          background: "transparent",
          border: "none",
          color: "var(--rib-text2)",
          cursor: "pointer",
          padding: 0,
          fontSize: 12,
        }}
      >
        <Chev open={open} />
        <span
          className="font-semibold uppercase"
          style={{ letterSpacing: "0.08em" }}
        >
          Evidence
        </span>
        <span
          className="font-mono"
          style={{ color: "var(--rib-text3)" }}
        >
          {items.length}
        </span>
      </button>
      {open && (
        <div className="mt-[10px] flex flex-col gap-2">
          {items.map((ev, i) => (
            <div
              key={i}
              style={{
                background: "var(--rib-bg0)",
                border: "1px solid var(--rib-line)",
                borderRadius: 6,
              }}
            >
              <div
                className="flex items-center gap-[10px] px-3 py-2"
                style={{
                  borderBottom: "1px solid var(--rib-line)",
                  background: "var(--rib-bg2)",
                }}
              >
                <Pill mono>{ev.kind}</Pill>
                <span style={{ fontSize: 12.5, color: "var(--rib-text1)" }}>
                  {ev.description}
                </span>
              </div>
              <pre
                className="font-mono rib-scrollbar"
                style={{
                  margin: 0,
                  padding: "10px 14px",
                  fontSize: 12,
                  lineHeight: "18px",
                  color: "var(--rib-mono)",
                  overflow: "auto",
                  maxHeight: 180,
                  whiteSpace: "pre",
                }}
              >
                {ev.raw}
              </pre>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function truncate(s: string, n: number): string {
  if (s.length <= n) return s;
  return s.slice(0, n - 1).trimEnd() + "…";
}
