import type { ReactNode } from "react";

interface Props {
  eyebrow: string;
  title: string;
  count?: string | number;
  right?: ReactNode;
}

export function SectionHeader({ eyebrow, title, count, right }: Props) {
  return (
    <div
      className="flex items-baseline gap-[14px] mb-5 pb-[14px]"
      style={{ borderBottom: "1px solid var(--rib-line)" }}
    >
      <div
        className="text-[11px] font-semibold uppercase"
        style={{
          color: "var(--rib-text2)",
          letterSpacing: "0.14em",
        }}
      >
        {eyebrow}
      </div>
      <div
        className="font-semibold"
        style={{
          fontSize: 20,
          color: "var(--rib-text0)",
          letterSpacing: "-0.01em",
        }}
      >
        {title}
      </div>
      {count != null && (
        <div
          className="tabular-nums"
          style={{ fontSize: 13, color: "var(--rib-text2)" }}
        >
          {count}
        </div>
      )}
      <div className="flex-1" />
      {right}
    </div>
  );
}
