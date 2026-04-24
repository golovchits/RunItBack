import type { Disagreement } from "../../types/schemas";
import { AGENT_META } from "../../util/tokens";
import { Pill } from "../atoms";

interface Props {
  items: Disagreement[];
}

export function DisagreementsPanel({ items }: Props) {
  if (!items || items.length === 0) return null;
  return (
    <div className="flex flex-col gap-3">
      {items.map((d, i) => (
        <div
          key={i}
          className="grid gap-4"
          style={{
            background: "var(--rib-bg1)",
            border: "1px solid var(--rib-line)",
            borderRadius: 8,
            padding: "16px 20px",
            gridTemplateColumns: "1fr 1fr 1fr",
          }}
        >
          <div
            className="flex items-center gap-[10px] mb-1"
            style={{ gridColumn: "1 / -1" }}
          >
            <span
              className="font-semibold uppercase"
              style={{
                fontSize: 11,
                letterSpacing: "0.14em",
                color: "var(--rib-text2)",
              }}
            >
              Disagreement
            </span>
            <Pill mono>{d.finding_id}</Pill>
          </div>
          <DisagreeCol
            role="code_auditor"
            label="Auditor"
            text={d.auditor_verdict}
          />
          <DisagreeCol
            role="validator"
            label="Validator"
            text={d.validator_verdict}
          />
          <DisagreeCol
            role="reviewer"
            label="Reviewer · resolution"
            text={d.reviewer_resolution}
          />
        </div>
      ))}
    </div>
  );
}

function DisagreeCol({
  role,
  label,
  text,
}: {
  role: "code_auditor" | "validator" | "reviewer";
  label: string;
  text: string;
}) {
  const m = AGENT_META[role];
  return (
    <div
      style={{
        borderLeft: `3px solid ${m.fg}`,
        paddingLeft: 12,
      }}
    >
      <div
        className="mb-[6px] font-semibold uppercase"
        style={{
          fontSize: 10.5,
          letterSpacing: "0.14em",
          color: m.fg,
        }}
      >
        {label}
      </div>
      <div
        className="text-pretty"
        style={{
          fontSize: 13,
          lineHeight: "20px",
          color: "var(--rib-text1)",
        }}
      >
        {text}
      </div>
    </div>
  );
}
