import { useEffect, useState } from "react";

/**
 * Shown between reviewer.finished and report.final. The gap can be
 * minutes on real audits (reviewer thinking + parse + repair), not
 * the "few seconds" the overlay used to claim. Renders as a small
 * bottom-right pill so the user can still browse findings, the
 * activity feed, and the pipeline sidebar while the reviewer works.
 */
export function FinalizingOverlay() {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    const start = Date.now();
    const id = window.setInterval(
      () => setElapsed(Math.floor((Date.now() - start) / 1000)),
      500,
    );
    return () => window.clearInterval(id);
  }, []);

  const minutes = Math.floor(elapsed / 60);
  const seconds = elapsed % 60;
  const elapsedLabel =
    minutes > 0 ? `${minutes}m ${seconds}s` : `${seconds}s`;

  return (
    <div
      role="status"
      aria-live="polite"
      className="fixed flex items-center gap-3 px-4 py-3 rounded-lg"
      style={{
        right: 24,
        bottom: 24,
        background: "var(--rib-bg1)",
        border: "1px solid var(--rib-line)",
        boxShadow: "0 6px 20px rgba(0,0,0,0.45)",
        zIndex: 20,
        maxWidth: 320,
        pointerEvents: "none",
      }}
    >
      <div
        style={{
          width: 16,
          height: 16,
          flexShrink: 0,
          borderRadius: 999,
          border: "2px solid var(--rib-agent-reviewer)",
          borderRightColor: "transparent",
          animation: "spin 1s linear infinite",
        }}
      />
      <div className="flex flex-col min-w-0">
        <div
          className="font-medium"
          style={{
            fontSize: 13,
            color: "var(--rib-text0)",
            lineHeight: "18px",
          }}
        >
          Reviewer assembling report
        </div>
        <div
          className="font-mono tabular-nums"
          style={{
            fontSize: 11,
            color: "var(--rib-text3)",
            lineHeight: "16px",
          }}
        >
          {elapsedLabel}
        </div>
      </div>
      <style>{`
        @keyframes spin { from { transform: rotate(0) } to { transform: rotate(360deg) } }
      `}</style>
    </div>
  );
}
