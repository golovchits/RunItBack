import { useCallback, useEffect, useMemo, useState } from "react";
import { useAudit } from "./state/audit";
import { InputScreen } from "./components/input/InputScreen";
import { LiveAuditScreen } from "./components/live/LiveAuditScreen";
import { ReportScreen } from "./components/report/ReportScreen";
import { Header, type HeaderView } from "./components/Header";
import type { DiagnosticReport } from "./types/schemas";
import tridentSample from "./fixtures/trident_sample.json";
import nanogptSample from "./fixtures/nanogpt_sample.json";

/**
 * Single-route SPA. The audit store's `phase` drives which screen would
 * render by default, but the user can override with the Header tabs once
 * a live audit has activity AND a report is available.
 *
 * Dev-only: ?fixture=trident or ?fixture=nanogpt loads a saved report
 * fixture without touching the backend.
 */
export default function App() {
  const phase = useAudit((s) => s.phase);
  const report = useAudit((s) => s.report);
  const auditId = useAudit((s) => s.auditId);
  const activityCount = useAudit((s) => s.activity.length);
  const cancelAudit = useAudit((s) => s.cancelAudit);
  const reset = useAudit((s) => s.reset);

  const [viewOverride, setViewOverride] = useState<HeaderView | null>(null);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const fix = params.get("fixture");
    if (fix === "trident") {
      useAudit
        .getState()
        .loadFixtureReport(tridentSample as unknown as DiagnosticReport);
      return;
    }
    if (fix === "nanogpt") {
      useAudit
        .getState()
        .loadFixtureReport(nanogptSample as unknown as DiagnosticReport);
      return;
    }
    const match = window.location.pathname.match(/^\/audit\/([\w-]+)/);
    if (match && !auditId) {
      void useAudit.getState().resumeAudit(match[1]);
    }
  }, [auditId]);

  // Default view is derived from phase; user can override via tabs.
  const defaultView: HeaderView = useMemo(() => {
    if (!auditId) return "input";
    if (phase === "done" && report) return "report";
    return "live";
  }, [auditId, phase, report]);

  const view = viewOverride ?? defaultView;

  // Whenever a new report arrives, auto-switch to it — but only if we were
  // passively following phase (no manual override) or already on live.
  useEffect(() => {
    if (report && defaultView === "report" && viewOverride === "live") {
      // Respect user's explicit Live choice even after report arrives.
      // (No auto-switch here.)
    }
  }, [report, defaultView, viewOverride]);

  // If the user hits "New audit", clear everything.
  const onNewAudit = useCallback(() => {
    reset();
    setViewOverride(null);
    window.history.replaceState({}, "", "/");
  }, [reset]);

  const onCancel = useCallback(() => {
    void cancelAudit();
  }, [cancelAudit]);

  // Reset overrides when user starts a new audit from input screen.
  useEffect(() => {
    if (!auditId) setViewOverride(null);
  }, [auditId]);

  const onExportJson = useCallback(() => {
    if (!report) return;
    const blob = new Blob([JSON.stringify(report, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `runitback-${report.audit_id}.json`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }, [report]);

  const onSwitchView = (v: HeaderView) => {
    // Ignore transitions into views without data.
    if (v === "report" && !report) return;
    if (v === "live" && activityCount === 0 && phase !== "failed") return;
    setViewOverride(v);
  };

  const showCancel =
    view === "live" &&
    phase !== "done" &&
    phase !== "failed" &&
    phase !== null &&
    phase !== "created";

  return (
    <div className="h-full flex flex-col" style={{ background: "var(--rib-bg0)" }}>
      <Header
        view={view}
        onSwitchView={onSwitchView}
        onExportJson={report ? onExportJson : undefined}
        onNewAudit={view !== "input" ? onNewAudit : undefined}
        onCancel={showCancel ? onCancel : undefined}
      />
      <div className="flex-1 min-h-0">
        {view === "input" && <InputScreen />}
        {view === "live" && <LiveAuditScreen />}
        {view === "report" && report && <ReportScreen report={report} />}
      </div>
    </div>
  );
}
