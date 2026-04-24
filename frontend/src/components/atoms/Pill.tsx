import type { CSSProperties, ReactNode } from "react";

interface Props {
  children: ReactNode;
  tone?: "neutral" | "strong" | "accent";
  mono?: boolean;
  style?: CSSProperties;
  className?: string;
  title?: string;
}

const TONES = {
  neutral: {
    c: "var(--rib-text1)",
    bg: "transparent",
    bd: "var(--rib-line2)",
  },
  strong: {
    c: "var(--rib-text0)",
    bg: "var(--rib-bg3)",
    bd: "var(--rib-line2)",
  },
  accent: {
    c: "var(--rib-agent-auditor)",
    bg: "transparent",
    bd: "rgba(90,140,217,0.33)",
  },
};

export function Pill({
  children,
  tone = "neutral",
  mono,
  style,
  className,
  title,
}: Props) {
  const t = TONES[tone];
  return (
    <span
      title={title}
      className={`inline-flex items-center gap-[6px] ${mono ? "font-mono" : "font-ui"} ${className ?? ""}`}
      style={{
        fontSize: mono ? 11.5 : 12,
        fontWeight: mono ? 400 : 500,
        color: t.c,
        background: t.bg,
        border: `1px solid ${t.bd}`,
        borderRadius: 4,
        padding: mono ? "2px 7px" : "2px 8px",
        ...style,
      }}
    >
      {children}
    </span>
  );
}
