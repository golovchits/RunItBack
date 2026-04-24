import { useAudit } from "../../state/audit";
import { ActivityFeed } from "./ActivityFeed";
import { ErrorBanner } from "./ErrorBanner";
import { FindingsSidebar } from "./FindingsSidebar";
import { FinalizingOverlay } from "./FinalizingOverlay";
import { LiveCodeViewer } from "./LiveCodeViewer";
import { PipelineSidebar } from "./PipelineSidebar";

export function LiveAuditScreen() {
  const reviewerDone = useAudit((s) => s.agents.reviewer.status === "done");
  const reportReady = useAudit((s) => s.report != null);

  // Show the "assembling report" pill once the reviewer agent itself has
  // finished — the remaining gap is parse + repair + report.final, which
  // is the window the overlay is meant to cover.
  const finalizing = !reportReady && reviewerDone;

  return (
    <div
      className="flex flex-col h-full"
      style={{ background: "var(--rib-bg0)" }}
    >
      <ErrorBanner />
      <div
        className="flex flex-1 min-h-0 relative"
        style={{ background: "var(--rib-bg0)" }}
      >
        <PipelineSidebar />
        <div className="flex flex-col flex-1 min-w-0">
          <div className="flex flex-1 min-h-0">
            <div
              className="flex-1 min-w-0 flex flex-col"
              style={{ borderRight: "1px solid var(--rib-line)" }}
            >
              <div
                className="flex-1 min-h-0"
                style={{
                  borderBottom: "1px solid var(--rib-line)",
                  minHeight: "50%",
                }}
              >
                <ActivityFeed />
              </div>
              <div className="flex-1 min-h-0" style={{ minHeight: "40%" }}>
                <LiveCodeViewer />
              </div>
            </div>
          </div>
        </div>
        <FindingsSidebar />
        {finalizing && <FinalizingOverlay />}
      </div>
    </div>
  );
}
