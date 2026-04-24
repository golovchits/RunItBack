import type { AgentName } from "../../types/schemas";
import { AGENT_META } from "../../util/tokens";

interface Props {
  agent: AgentName | "paper" | "auditor";
  subtle?: boolean;
  size?: "sm" | "md";
}

export function AgentBadge({ agent, subtle = true, size = "md" }: Props) {
  const m = AGENT_META[agent] ?? AGENT_META.code_auditor;
  const fz = size === "sm" ? 11 : 12;
  const pad = size === "sm" ? "2px 7px 2px 6px" : "3px 9px 3px 7px";
  return (
    <span
      className="inline-flex items-center gap-[6px] font-ui"
      style={{
        fontSize: fz,
        fontWeight: 500,
        color: subtle ? "var(--rib-text1)" : m.fg,
        background: subtle ? "transparent" : m.bg,
        border: subtle ? `1px solid var(--rib-line2)` : `1px solid ${m.fg}33`,
        borderRadius: 4,
        padding: pad,
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
