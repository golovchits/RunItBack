import type { ValidationVerdict } from "../../types/schemas";
import { VALIDATION_META } from "../../util/tokens";

interface Props {
  status?: ValidationVerdict;
  labeled?: boolean;
}

export function StatusDot({ status = "unvalidated", labeled = true }: Props) {
  const m = VALIDATION_META[status] ?? VALIDATION_META.unvalidated;
  return (
    <span
      className="inline-flex items-center gap-[7px] font-ui"
      style={{
        fontSize: 12,
        fontWeight: 500,
        color: "var(--rib-text1)",
      }}
    >
      <span
        style={{
          width: 8,
          height: 8,
          borderRadius: 4,
          background: m.fill ? m.fg : "transparent",
          boxShadow: m.fill
            ? `0 0 0 3px ${m.fg}22`
            : `inset 0 0 0 1.5px ${m.fg}`,
        }}
      />
      {labeled && <span style={{ color: m.fg }}>{m.label}</span>}
    </span>
  );
}
