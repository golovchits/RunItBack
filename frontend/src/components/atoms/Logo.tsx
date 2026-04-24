interface Props {
  size?: number;
}

/** Gradient "R" mark, mirrors the handoff SideNav logo treatment. */
export function Logo({ size = 24 }: Props) {
  return (
    <div
      style={{
        width: size,
        height: size,
        borderRadius: size * 0.2,
        background:
          "linear-gradient(135deg, var(--rib-agent-paper) 0%, var(--rib-agent-reviewer) 100%)",
        position: "relative",
        overflow: "hidden",
        flexShrink: 0,
      }}
    >
      <div
        style={{
          position: "absolute",
          inset: 0,
          background: "var(--rib-bg0)",
          margin: size * 0.12,
          borderRadius: size * 0.12,
        }}
      />
      <div
        style={{
          position: "absolute",
          inset: 0,
          display: "grid",
          placeItems: "center",
          color: "var(--rib-text0)",
          fontSize: Math.round(size * 0.5),
          fontWeight: 700,
          letterSpacing: "-0.04em",
        }}
      >
        R
      </div>
    </div>
  );
}
