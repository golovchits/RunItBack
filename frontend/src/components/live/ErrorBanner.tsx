import { useAudit } from "../../state/audit";

export function ErrorBanner() {
  const error = useAudit((s) => s.error);
  if (!error) return null;
  return (
    <div
      className="flex items-center gap-3 px-5 py-3"
      style={{
        borderBottom: "1px solid rgba(229,83,83,0.35)",
        background: "rgba(229,83,83,0.10)",
        color: "var(--rib-text0)",
      }}
    >
      <span style={{ color: "var(--rib-critical)", fontWeight: 700 }}>!</span>
      <div className="flex-1 min-w-0">
        <span
          className="font-semibold uppercase mr-3"
          style={{
            fontSize: 11,
            color: "var(--rib-critical)",
            letterSpacing: "0.14em",
          }}
        >
          {error.errorType ?? "error"}
          {error.agent ? ` · ${error.agent}` : ""}
        </span>
        <span style={{ fontSize: 13 }}>{error.message}</span>
      </div>
      {error.recoverable === false && (
        <span
          className="font-semibold uppercase"
          style={{
            fontSize: 11,
            color: "var(--rib-critical)",
            letterSpacing: "0.14em",
          }}
        >
          Fatal
        </span>
      )}
    </div>
  );
}
