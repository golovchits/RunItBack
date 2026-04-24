import { useMemo } from "react";
import { useAudit } from "../../state/audit";
import { CodeViewer } from "../atoms";

export function LiveCodeViewer() {
  const viewer = useAudit((s) => s.viewer);

  // The fetched window is wider than the finding's span (by ~80 lines on
  // each side) for context. Compute the actual highlight range here so
  // CodeViewer doesn't have to infer it from the content bounds.
  const highlightLines = useMemo(() => {
    const a = viewer.highlightStart;
    const b = viewer.highlightEnd ?? a;
    if (a == null || b == null) return undefined;
    const [lo, hi] = a <= b ? [a, b] : [b, a];
    const out: number[] = [];
    for (let i = lo; i <= hi; i++) out.push(i);
    return out;
  }, [viewer.highlightStart, viewer.highlightEnd]);

  if (!viewer.file) {
    return (
      <div
        className="flex items-center justify-center h-full"
        style={{ background: "var(--rib-bg0)" }}
      >
        <div
          className="text-center"
          style={{ color: "var(--rib-text3)", fontSize: 13 }}
        >
          <div
            className="mb-2 font-mono"
            style={{ color: "var(--rib-text2)" }}
          >
            /
          </div>
          <div>
            Code viewer opens automatically when an agent reads a file
            <br />
            or emits a finding with a code span.
          </div>
        </div>
      </div>
    );
  }

  if (viewer.loading) {
    return (
      <div
        className="flex items-center justify-center h-full"
        style={{ background: "var(--rib-bg0)", color: "var(--rib-text2)" }}
      >
        <div
          style={{
            width: 16,
            height: 16,
            borderRadius: 999,
            border: "2px solid var(--rib-text2)",
            borderRightColor: "transparent",
            animation: "spin 0.8s linear infinite",
            marginRight: 10,
          }}
        />
        Loading {viewer.file}…
        <style>{`@keyframes spin { from { transform: rotate(0) } to { transform: rotate(360deg) } }`}</style>
      </div>
    );
  }

  if (viewer.error) {
    return (
      <div
        className="flex items-center justify-center h-full"
        style={{ background: "var(--rib-bg0)", color: "var(--rib-critical)" }}
      >
        {viewer.error}
      </div>
    );
  }

  return (
    <div className="h-full overflow-auto rib-scrollbar p-4">
      <CodeViewer
        content={viewer.content ?? ""}
        filePath={viewer.file}
        lineStart={viewer.start ?? 1}
        lineEnd={viewer.end ?? undefined}
        highlightLines={highlightLines}
      />
    </div>
  );
}
