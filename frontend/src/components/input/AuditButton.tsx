interface Props {
  disabled?: boolean;
  loading?: boolean;
  onClick: () => void;
  children?: React.ReactNode;
}

export function AuditButton({ disabled, loading, onClick, children }: Props) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled || loading}
      className="font-ui font-semibold relative overflow-hidden"
      style={{
        padding: "12px 28px",
        borderRadius: 8,
        background:
          disabled || loading
            ? "var(--rib-bg3)"
            : "linear-gradient(135deg, var(--rib-agent-auditor) 0%, var(--rib-agent-reviewer) 100%)",
        border: "1px solid var(--rib-line2)",
        color: disabled || loading ? "var(--rib-text2)" : "var(--rib-text0)",
        fontSize: 14,
        letterSpacing: "-0.005em",
        cursor: disabled || loading ? "not-allowed" : "pointer",
        boxShadow:
          disabled || loading
            ? "none"
            : "0 1px 0 rgba(0,0,0,0.3), 0 6px 24px rgba(90,140,217,0.18)",
        transition: "transform 0.08s",
      }}
    >
      {loading ? (
        <span className="flex items-center gap-2">
          <span
            style={{
              width: 12,
              height: 12,
              borderRadius: 999,
              border: "2px solid currentColor",
              borderRightColor: "transparent",
              animation: "spin 0.8s linear infinite",
            }}
          />
          Starting audit…
        </span>
      ) : (
        (children ?? "Run audit")
      )}
      <style>{`
        @keyframes spin { from { transform: rotate(0) } to { transform: rotate(360deg) } }
      `}</style>
    </button>
  );
}
