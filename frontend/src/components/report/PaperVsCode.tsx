interface Props {
  paper?: string | null;
  code?: string | null;
}

export function PaperVsCode({ paper, code }: Props) {
  if (!paper && !code) return null;
  return (
    <div
      className="grid gap-[10px]"
      style={{
        gridTemplateColumns: "1fr 1fr",
        marginTop: 16,
        marginBottom: 16,
      }}
    >
      <div
        style={{
          background:
            "linear-gradient(180deg, rgba(217,128,64,0.04) 0%, transparent 60%)",
          border: "1px solid var(--rib-line2)",
          borderLeft: "3px solid var(--rib-agent-paper)",
          borderRadius: 6,
          padding: "14px 16px",
        }}
      >
        <div
          className="flex items-center gap-2 mb-[10px] font-semibold uppercase"
          style={{
            color: "var(--rib-agent-paper)",
            fontSize: 10.5,
            letterSpacing: "0.16em",
          }}
        >
          <span
            style={{
              width: 6,
              height: 6,
              borderRadius: 3,
              background: "var(--rib-agent-paper)",
            }}
          />
          PAPER SAYS
        </div>
        <div
          className="italic text-pretty"
          style={{
            color: "var(--rib-text0)",
            fontSize: 13.5,
            lineHeight: "21px",
          }}
        >
          {paper || "—"}
        </div>
      </div>
      <div
        style={{
          background:
            "linear-gradient(180deg, rgba(229,83,83,0.04) 0%, transparent 60%)",
          border: "1px solid var(--rib-line2)",
          borderLeft: "3px solid var(--rib-notrep)",
          borderRadius: 6,
          padding: "14px 16px",
        }}
      >
        <div
          className="flex items-center gap-2 mb-[10px] font-semibold uppercase"
          style={{
            color: "var(--rib-notrep)",
            fontSize: 10.5,
            letterSpacing: "0.16em",
          }}
        >
          <span
            style={{
              width: 6,
              height: 6,
              borderRadius: 3,
              background: "var(--rib-notrep)",
            }}
          />
          CODE DOES
        </div>
        <div
          className="text-pretty"
          style={{
            color: "var(--rib-text0)",
            fontSize: 13.5,
            lineHeight: "21px",
          }}
        >
          {code || "—"}
        </div>
      </div>
    </div>
  );
}
