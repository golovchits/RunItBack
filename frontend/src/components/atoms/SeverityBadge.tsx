import type { Severity } from "../../types/schemas";
import { SEVERITY_META } from "../../util/tokens";

interface Props {
  level: Severity;
  size?: "sm" | "md";
}

export function SeverityBadge({ level, size = "md" }: Props) {
  const m = SEVERITY_META[level] ?? SEVERITY_META.info;
  const pad = size === "sm" ? "2px 7px" : "3px 9px";
  const fz = size === "sm" ? 11 : 12;
  return (
    <span
      className="inline-flex items-center gap-[6px] font-ui font-semibold uppercase"
      style={{
        fontSize: fz,
        letterSpacing: "0.02em",
        color: m.fg,
        background: m.bg,
        border: `1px solid ${m.line}`,
        borderRadius: 4,
        padding: pad,
      }}
    >
      <span
        className="inline-block"
        style={{
          width: 6,
          height: 6,
          borderRadius: 1,
          background: m.fg,
        }}
      />
      {m.label}
    </span>
  );
}
