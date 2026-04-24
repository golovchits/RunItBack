import type { ReactNode } from "react";

interface Props {
  eyebrow: string;
  title: string;
  subtitle?: string;
  accent?: "paper" | "auditor" | "validator" | "reviewer";
  children: ReactNode;
  right?: ReactNode;
}

const ACCENTS = {
  paper: "var(--rib-agent-paper)",
  auditor: "var(--rib-agent-auditor)",
  validator: "var(--rib-agent-validator)",
  reviewer: "var(--rib-agent-reviewer)",
};

export function SectionCard({
  eyebrow,
  title,
  subtitle,
  accent,
  children,
  right,
}: Props) {
  return (
    <section
      style={{
        background: "var(--rib-bg1)",
        border: "1px solid var(--rib-line)",
        borderRadius: 8,
        overflow: "hidden",
      }}
    >
      <header
        className="flex items-start gap-4 px-5 py-4"
        style={{
          borderBottom: "1px solid var(--rib-line)",
          background: "var(--rib-bg1)",
        }}
      >
        <div className="flex-1 min-w-0">
          <div
            className="flex items-center gap-2 mb-1 text-[11px] font-semibold uppercase"
            style={{
              color: accent ? ACCENTS[accent] : "var(--rib-text2)",
              letterSpacing: "0.14em",
            }}
          >
            {accent && (
              <span
                style={{
                  width: 6,
                  height: 6,
                  borderRadius: 3,
                  background: ACCENTS[accent],
                }}
              />
            )}
            {eyebrow}
          </div>
          <h2
            className="font-semibold"
            style={{
              color: "var(--rib-text0)",
              fontSize: 15,
              letterSpacing: "-0.01em",
            }}
          >
            {title}
          </h2>
          {subtitle && (
            <div
              className="mt-1"
              style={{ color: "var(--rib-text2)", fontSize: 12.5 }}
            >
              {subtitle}
            </div>
          )}
        </div>
        {right}
      </header>
      <div className="p-5">{children}</div>
    </section>
  );
}
