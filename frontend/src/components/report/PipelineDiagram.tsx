import { useMemo, useState } from "react";
import type { AuditFinding, Severity } from "../../types/schemas";
import { SEVERITY_META } from "../../util/tokens";
import { Chev, SeverityBadge } from "../atoms";

/**
 * Buckets AuditFinding.category → one of seven ML pipeline stages. The
 * mapping mirrors `backend/schemas/findings.py:FindingCategory`. This is a
 * purely derived view — no backend change needed — so the pipeline section
 * reflects whatever findings the Reviewer emitted.
 */

interface Stage {
  id: string;
  label: string;
  short: string;
  matches: (category: string) => boolean;
}

const STAGES: Stage[] = [
  {
    id: "environment",
    label: "Environment",
    short: "ENV",
    matches: (c) => c.startsWith("environment.") || c === "environment",
  },
  {
    id: "data",
    label: "Data",
    short: "DATA",
    matches: (c) =>
      c.startsWith("data.") ||
      c.startsWith("dataloader.") ||
      c.startsWith("data_leakage."),
  },
  {
    id: "preprocessing",
    label: "Preprocessing",
    short: "PREPROC",
    matches: (c) => c.startsWith("preprocessing."),
  },
  {
    id: "model",
    label: "Model",
    short: "MODEL",
    matches: (c) =>
      c.startsWith("architecture.") ||
      c === "api.default_value_drift" ||
      c === "state.checkpoint_incomplete",
  },
  {
    id: "training",
    label: "Training",
    short: "TRAINING",
    matches: (c) =>
      c.startsWith("determinism.") ||
      c.startsWith("distributed.") ||
      c.startsWith("training.") ||
      c === "state.eval_mode_not_toggled" ||
      c === "config.value_mismatch_with_paper",
  },
  {
    id: "evaluation",
    label: "Evaluation",
    short: "EVAL",
    matches: (c) => c.startsWith("eval."),
  },
  {
    id: "quality",
    label: "Code quality",
    short: "QUALITY",
    matches: (c) =>
      c.startsWith("code_quality.") || c === "other" || c === "OTHER",
  },
];

const SEV_RANK: Record<Severity, number> = {
  critical: 4,
  high: 3,
  medium: 2,
  low: 1,
  info: 0,
};

interface Props {
  findings: AuditFinding[];
  onJumpToFinding?: (id: string) => void;
}

export function PipelineDiagram({ findings, onJumpToFinding }: Props) {
  const buckets = useMemo(() => {
    const out = new Map<string, AuditFinding[]>();
    for (const s of STAGES) out.set(s.id, []);
    for (const f of findings) {
      const stage = STAGES.find((s) => s.matches(f.category ?? "")) ?? STAGES[6];
      out.get(stage.id)!.push(f);
    }
    // Sort each bucket by severity desc, then confidence desc.
    for (const [, list] of out) {
      list.sort((a, b) => {
        const ra = SEV_RANK[a.severity] ?? 0;
        const rb = SEV_RANK[b.severity] ?? 0;
        if (ra !== rb) return rb - ra;
        return b.confidence - a.confidence;
      });
    }
    return out;
  }, [findings]);

  const [openStage, setOpenStage] = useState<string | null>(() => {
    // Auto-open the first stage with a critical/high finding, else nothing.
    for (const s of STAGES) {
      const list = buckets.get(s.id) ?? [];
      if (list.some((f) => f.severity === "critical" || f.severity === "high"))
        return s.id;
    }
    return null;
  });

  return (
    <div className="flex flex-col gap-4">
      {/* Horizontal chain of stage chips */}
      <div
        className="rib-scrollbar overflow-x-auto"
        style={{
          background: "var(--rib-bg1)",
          border: "1px solid var(--rib-line)",
          borderRadius: 8,
          padding: "18px 20px",
        }}
      >
        <div
          className="flex items-stretch gap-2"
          style={{ minWidth: "fit-content" }}
        >
          {STAGES.map((s, i) => {
            const list = buckets.get(s.id) ?? [];
            const maxSev = list.reduce<Severity | null>((acc, f) => {
              if (!acc) return f.severity;
              return SEV_RANK[f.severity] > SEV_RANK[acc] ? f.severity : acc;
            }, null);
            const isOpen = openStage === s.id;
            // Code quality isn't a pipeline step, it's a cross-cutting
            // bucket — suppress the arrow before it and the arrow that
            // would otherwise flow out of Evaluation into it.
            const isLast = i === STAGES.length - 1;
            const nextIsQuality = STAGES[i + 1]?.id === "quality";
            return (
              <StageChip
                key={s.id}
                stage={s}
                findings={list}
                maxSeverity={maxSev}
                isOpen={isOpen}
                showArrow={!isLast && !nextIsQuality}
                onToggle={() => setOpenStage((cur) => (cur === s.id ? null : s.id))}
              />
            );
          })}
        </div>
      </div>

      {/* Stage detail panel */}
      {openStage && (
        <StageDetail
          stage={STAGES.find((s) => s.id === openStage)!}
          findings={buckets.get(openStage) ?? []}
          onJump={(f) => onJumpToFinding?.(f.id)}
        />
      )}
    </div>
  );
}

function StageChip({
  stage,
  findings,
  maxSeverity,
  isOpen,
  showArrow,
  onToggle,
}: {
  stage: Stage;
  findings: AuditFinding[];
  maxSeverity: Severity | null;
  isOpen: boolean;
  showArrow: boolean;
  onToggle: () => void;
}) {
  const sev = maxSeverity ? SEVERITY_META[maxSeverity] : null;
  const count = findings.length;
  const empty = count === 0;

  return (
    <div className="flex items-center gap-2 shrink-0">
      <button
        type="button"
        onClick={onToggle}
        className="font-ui text-left"
        style={{
          minWidth: 140,
          background: isOpen
            ? "var(--rib-bg3)"
            : empty
              ? "transparent"
              : sev
                ? sev.bg
                : "var(--rib-bg2)",
          border: `1px solid ${
            isOpen
              ? "var(--rib-line2)"
              : sev
                ? sev.line
                : "var(--rib-line)"
          }`,
          borderRadius: 6,
          padding: "12px 14px",
          cursor: "pointer",
          transition: "all 0.15s",
          opacity: empty ? 0.55 : 1,
        }}
      >
        <div className="flex items-center gap-[8px] mb-2">
          <span
            style={{
              width: 8,
              height: 8,
              borderRadius: 2,
              background: sev ? sev.fg : "var(--rib-text3)",
              boxShadow: sev ? `0 0 0 3px ${sev.fg}22` : undefined,
            }}
          />
          <span
            className="font-semibold uppercase"
            style={{
              fontSize: 10.5,
              letterSpacing: "0.14em",
              color: sev ? sev.fg : "var(--rib-text2)",
            }}
          >
            {stage.short}
          </span>
        </div>
        <div
          className="font-semibold"
          style={{
            color: "var(--rib-text0)",
            fontSize: 14,
            letterSpacing: "-0.005em",
          }}
        >
          {stage.label}
        </div>
        <div
          className="mt-1 flex items-center gap-2"
          style={{ color: "var(--rib-text2)", fontSize: 12 }}
        >
          <span
            className="font-mono tabular-nums"
            style={{
              fontSize: 13,
              color: empty ? "var(--rib-text3)" : "var(--rib-text0)",
              fontWeight: 600,
            }}
          >
            {count}
          </span>
          <span>{count === 1 ? "finding" : "findings"}</span>
        </div>
      </button>
      {showArrow && (
        <div
          aria-hidden="true"
          style={{ color: "var(--rib-text3)", fontSize: 18 }}
        >
          →
        </div>
      )}
    </div>
  );
}

function StageDetail({
  stage,
  findings,
  onJump,
}: {
  stage: Stage;
  findings: AuditFinding[];
  onJump: (f: AuditFinding) => void;
}) {
  return (
    <div
      style={{
        background: "var(--rib-bg1)",
        border: "1px solid var(--rib-line)",
        borderRadius: 8,
        overflow: "hidden",
      }}
    >
      <div
        className="flex items-center gap-3 px-5 py-[12px]"
        style={{
          borderBottom: "1px solid var(--rib-line)",
          background: "var(--rib-bg2)",
        }}
      >
        <span
          className="font-semibold uppercase"
          style={{
            fontSize: 11,
            color: "var(--rib-text2)",
            letterSpacing: "0.14em",
          }}
        >
          Stage · {stage.label}
        </span>
        <span
          className="font-mono tabular-nums"
          style={{ fontSize: 12.5, color: "var(--rib-text0)" }}
        >
          {findings.length}
        </span>
      </div>
      {findings.length === 0 ? (
        <div
          className="px-5 py-6 text-center"
          style={{ color: "var(--rib-text3)", fontSize: 13 }}
        >
          No findings at this stage.
        </div>
      ) : (
        <ol className="m-0 p-0 list-none">
          {findings.map((f, i) => (
            <StageFindingRow
              key={f.id}
              finding={f}
              first={i === 0}
              onClick={() => onJump(f)}
            />
          ))}
        </ol>
      )}
    </div>
  );
}

function StageFindingRow({
  finding,
  first,
  onClick,
}: {
  finding: AuditFinding;
  first: boolean;
  onClick: () => void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <li
      style={{
        borderTop: first ? "none" : "1px solid var(--rib-line)",
      }}
    >
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="w-full text-left font-ui grid items-start gap-3"
        style={{
          gridTemplateColumns: "12px auto 1fr auto",
          padding: "12px 16px",
          background: "transparent",
          border: "none",
          cursor: "pointer",
          color: "inherit",
        }}
      >
        <Chev open={open} />
        <SeverityBadge level={finding.severity} size="sm" />
        <div className="min-w-0">
          <div
            style={{
              fontSize: 13.5,
              lineHeight: "20px",
              color: "var(--rib-text0)",
              fontWeight: 500,
            }}
            className="text-pretty"
          >
            {finding.title}
          </div>
          <div
            className="mt-[3px] font-mono"
            style={{ fontSize: 11.5, color: "var(--rib-text3)" }}
          >
            {finding.id} · {finding.category}
          </div>
        </div>
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onClick();
          }}
          className="font-ui"
          style={{
            padding: "4px 10px",
            borderRadius: 4,
            background: "transparent",
            border: "1px solid var(--rib-line2)",
            color: "var(--rib-text2)",
            fontSize: 11.5,
            cursor: "pointer",
            whiteSpace: "nowrap",
          }}
        >
          Open finding →
        </button>
      </button>
      {open && (
        <div
          style={{
            padding: "0 16px 14px 40px",
            color: "var(--rib-text1)",
            fontSize: 13,
            lineHeight: "20px",
          }}
          className="text-pretty"
        >
          {finding.description}
          {finding.code_span && (
            <div
              className="font-mono mt-2"
              style={{ fontSize: 12, color: "var(--rib-text2)" }}
            >
              {finding.code_span.file_path}:{finding.code_span.line_start}
              {finding.code_span.line_end !== finding.code_span.line_start &&
                `-${finding.code_span.line_end}`}
            </div>
          )}
        </div>
      )}
    </li>
  );
}
