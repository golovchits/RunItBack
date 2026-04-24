import type { Verdict } from "../../types/schemas";
import { VERDICT_META } from "../../util/tokens";

interface Props {
  verdict: Verdict;
}

export function VerdictBadge({ verdict }: Props) {
  const m = VERDICT_META[verdict];
  return (
    <span
      className="inline-flex items-center gap-[7px] font-ui font-semibold uppercase"
      style={{
        fontSize: 12,
        letterSpacing: "0.04em",
        color: m.fg,
        border: `1px solid ${m.fg}55`,
        borderRadius: 4,
        padding: "3px 9px",
      }}
    >
      <span
        style={{
          width: 7,
          height: 7,
          borderRadius: 4,
          background: m.fg,
          boxShadow: `0 0 0 3px ${m.fg}22`,
        }}
      />
      {m.label}
    </span>
  );
}
