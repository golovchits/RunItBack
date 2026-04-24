interface Props {
  diff: string;
  label?: string;
}

/** Unified-diff renderer: `+` green, `-` red, hunks purple. */
export function DiffBlock({ diff, label = "SUGGESTED FIX · UNIFIED DIFF" }: Props) {
  const lines = diff.split("\n");
  return (
    <div
      style={{
        background: "var(--rib-bg0)",
        border: "1px solid var(--rib-line)",
        borderLeft: "3px solid var(--rib-reproducible)",
        borderRadius: 6,
        fontFamily:
          '"JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, monospace',
        fontSize: 12.5,
        lineHeight: "20px",
        overflow: "hidden",
      }}
    >
      <div
        style={{
          padding: "8px 12px",
          borderBottom: "1px solid var(--rib-line)",
          background: "var(--rib-bg2)",
          display: "flex",
          alignItems: "center",
          gap: 8,
        }}
      >
        <span
          className="font-ui"
          style={{
            color: "var(--rib-reproducible)",
            fontSize: 11.5,
            fontWeight: 600,
            letterSpacing: "0.08em",
          }}
        >
          {label}
        </span>
      </div>
      <pre
        className="rib-scrollbar"
        style={{
          margin: 0,
          padding: "8px 0",
          overflowX: "auto",
        }}
      >
        {lines.map((l, i) => {
          let color: string = "var(--rib-mono)";
          let bg: string = "transparent";
          if (l.startsWith("+++") || l.startsWith("---")) {
            color = "var(--rib-text2)";
          } else if (l.startsWith("@@")) {
            color = "#b28cd9";
          } else if (l.startsWith("+")) {
            color = "#6fbf95";
            bg = "rgba(79,165,121,0.12)";
          } else if (l.startsWith("-")) {
            color = "#f07a7a";
            bg = "rgba(229,83,83,0.12)";
          }
          return (
            <div
              key={i}
              style={{
                padding: "0 14px",
                color,
                background: bg,
                whiteSpace: "pre",
                minHeight: 20,
              }}
            >
              {l || " "}
            </div>
          );
        })}
      </pre>
    </div>
  );
}
