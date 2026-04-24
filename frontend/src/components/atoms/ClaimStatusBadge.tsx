import type { ClaimVerificationStatus } from "../../types/schemas";
import { CLAIM_META } from "../../util/tokens";

interface Props {
  status: ClaimVerificationStatus;
}

export function ClaimStatusBadge({ status }: Props) {
  const m = CLAIM_META[status] ?? CLAIM_META.unchecked;
  return (
    <span
      className="inline-flex items-center gap-[6px] font-ui font-semibold uppercase"
      style={{
        fontSize: 11.5,
        letterSpacing: "0.04em",
        color: m.fg,
      }}
    >
      <span
        style={{
          width: 6,
          height: 6,
          borderRadius: 3,
          background: m.fg,
        }}
      />
      {m.label}
    </span>
  );
}
