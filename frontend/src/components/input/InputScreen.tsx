import { useMemo, useState } from "react";
import type { AuditRequest, PaperSource } from "../../types/schemas";
import { useAudit } from "../../state/audit";
import { PaperInputPanel } from "./PaperInputPanel";
import { CodeInputPanel } from "./CodeInputPanel";
import { DataInputPanel } from "./DataInputPanel";
import { AuditOptions } from "./AuditOptions";
import { AuditButton } from "./AuditButton";

const INITIAL: AuditRequest = {
  paper: { kind: "arxiv", arxiv_url: "" },
  code: { kind: "git", url: "" },
  data: { kind: "skip" },
  timeout_minutes: 45,
  include_eda: true,
  include_suggested_fixes: true,
  user_notes: "",
  data_structure_text: "",
};

export function InputScreen() {
  const [req, setReq] = useState<AuditRequest>(INITIAL);
  const submitting = useAudit((s) => s.submitting);
  const error = useAudit((s) => s.error);
  const startAudit = useAudit((s) => s.startAudit);

  const validation = useMemo(() => validate(req), [req]);

  const submit = async () => {
    if (!validation.ok) return;
    const cleaned: AuditRequest = {
      ...req,
      user_notes: req.user_notes?.trim() ? req.user_notes : null,
      data_structure_text: req.data_structure_text?.trim()
        ? req.data_structure_text
        : null,
      paper: normalizePaper(req.paper),
    };
    try {
      await startAudit(cleaned);
    } catch {
      /* already surfaced via state.error */
    }
  };

  return (
    <div className="h-full overflow-auto rib-scrollbar" style={{ background: "var(--rib-bg0)" }}>
      <div className="mx-auto max-w-[960px] px-8 pt-10 pb-24 space-y-6">
        <div>
          <div
            className="mb-2 text-[11px] font-semibold uppercase"
            style={{
              color: "var(--rib-text2)",
              letterSpacing: "0.16em",
            }}
          >
            New audit
          </div>
          <h1
            className="text-[28px] font-semibold text-balance"
            style={{
              color: "var(--rib-text0)",
              letterSpacing: "-0.02em",
              lineHeight: "36px",
            }}
          >
            Initiate Reproducibility Audit
          </h1>
          <p
            className="mt-3 text-[15px] max-w-[680px] text-pretty"
            style={{ color: "var(--rib-text1)", lineHeight: "24px" }}
          >
            Point at a paper and its associated repo. Paper Analyst extracts claims,
            Code &amp; Data Auditor reads the code and data, Validator runs targeted
            checks, and Reviewer assembles the report. Expect
            20–60 minutes depending on repo size and timeout budget.
          </p>
        </div>

        <PaperInputPanel
          value={req.paper}
          onChange={(paper) => setReq((r) => ({ ...r, paper }))}
        />
        <CodeInputPanel
          value={req.code}
          onChange={(code) => setReq((r) => ({ ...r, code }))}
        />
        <DataInputPanel
          value={req.data}
          onChange={(data) => setReq((r) => ({ ...r, data }))}
          dataStructureText={req.data_structure_text ?? ""}
          onDataStructureTextChange={(text) =>
            setReq((r) => ({ ...r, data_structure_text: text }))
          }
        />
        <AuditOptions
          timeoutMinutes={req.timeout_minutes ?? 45}
          includeEda={req.include_eda ?? true}
          includeSuggestedFixes={req.include_suggested_fixes ?? true}
          userNotes={req.user_notes ?? ""}
          onChange={(patch) =>
            setReq((r) => ({
              ...r,
              timeout_minutes: patch.timeoutMinutes ?? r.timeout_minutes,
              include_eda: patch.includeEda ?? r.include_eda,
              include_suggested_fixes:
                patch.includeSuggestedFixes ?? r.include_suggested_fixes,
              user_notes:
                patch.userNotes != null ? patch.userNotes : r.user_notes,
            }))
          }
        />

        {error && (
          <div
            className="flex items-start gap-3 p-4 rounded-md"
            style={{
              background: "rgba(229,83,83,0.08)",
              border: "1px solid rgba(229,83,83,0.35)",
              color: "var(--rib-text0)",
            }}
          >
            <span style={{ color: "var(--rib-critical)", fontSize: 18 }}>
              !
            </span>
            <div className="min-w-0">
              <div
                className="text-[13px] font-semibold"
                style={{ color: "var(--rib-critical)" }}
              >
                {error.errorType ?? "Error"}
              </div>
              <div className="mt-1 text-[13px]">{error.message}</div>
            </div>
          </div>
        )}

        <div
          className="sticky bottom-0 py-4 -mx-2 px-2"
          style={{
            background:
              "linear-gradient(180deg, transparent 0%, var(--rib-bg0) 40%)",
            backdropFilter: "blur(4px)",
          }}
        >
          <div
            className="flex items-center gap-4 p-3 rounded-md"
            style={{
              background: "var(--rib-bg1)",
              border: "1px solid var(--rib-line)",
            }}
          >
            <div className="flex-1 min-w-0">
              <div
                className="text-[13px]"
                style={{
                  color: validation.ok
                    ? "var(--rib-text1)"
                    : "var(--rib-text2)",
                }}
              >
                {validation.ok ? (
                  <>
                    <span
                      style={{
                        color: "var(--rib-reproducible)",
                        marginRight: 8,
                      }}
                    >
                      Ready
                    </span>
                    <span>
                      {describePaper(req.paper)} · {describeCode(req)} ·{" "}
                      {describeData(req)}
                    </span>
                  </>
                ) : (
                  validation.reason
                )}
              </div>
            </div>
            <AuditButton
              disabled={!validation.ok}
              loading={submitting}
              onClick={submit}
            >
              {validation.ok ? "Run audit" : "Fill required fields"}
            </AuditButton>
          </div>
        </div>
      </div>
    </div>
  );
}

function validate(r: AuditRequest): { ok: boolean; reason: string } {
  switch (r.paper.kind) {
    case "arxiv":
      if (!r.paper.arxiv_url.trim())
        return { ok: false, reason: "Paper: arXiv URL is required." };
      break;
    case "pdf_url":
      if (!r.paper.url.trim())
        return { ok: false, reason: "Paper: PDF URL is required." };
      break;
    case "upload":
      if (!r.paper.upload_id)
        return { ok: false, reason: "Paper: upload has not finished." };
      break;
    case "raw_text":
      if ((r.paper.text || "").length < 500)
        return { ok: false, reason: "Paper: at least 500 characters required." };
      break;
    case "none":
      break;
  }
  if (r.code.kind === "git") {
    if (!r.code.url.trim())
      return { ok: false, reason: "Code: repository URL is required." };
  } else {
    if (!String(r.code.path).trim())
      return { ok: false, reason: "Code: local path is required." };
  }
  if (r.data.kind === "local" && !String(r.data.path).trim())
    return { ok: false, reason: "Data: local path is required." };
  if (r.data.kind === "url" && !r.data.url.trim())
    return { ok: false, reason: "Data: download URL is required." };
  return { ok: true, reason: "" };
}

function describePaper(p: PaperSource): string {
  switch (p.kind) {
    case "arxiv":
      return `paper arXiv ${shortHost(p.arxiv_url)}`;
    case "pdf_url":
      return `paper PDF ${shortHost(p.url)}`;
    case "upload":
      return "paper uploaded";
    case "raw_text":
      return "paper text pasted";
    case "none":
      return "no paper";
  }
}

function describeCode(r: AuditRequest): string {
  if (r.code.kind === "git") return `code ${shortHost(r.code.url)}`;
  return `code ${r.code.path}`;
}

function describeData(r: AuditRequest): string {
  switch (r.data.kind) {
    case "local":
      return `data ${r.data.path}`;
    case "url":
      return `data ${shortHost(r.data.url)}`;
    case "bundled":
      return `data bundled`;
    case "skip":
      return "no data";
  }
}

function shortHost(url: string): string {
  try {
    const u = new URL(url);
    const path = u.pathname.length > 1 ? u.pathname : "";
    return `${u.host}${path}`.slice(0, 48);
  } catch {
    return url.slice(0, 48);
  }
}

function normalizePaper(p: PaperSource): PaperSource {
  if (p.kind === "raw_text") {
    return { ...p, title_hint: p.title_hint?.trim() || null };
  }
  if (p.kind === "none") {
    return { kind: "none", title_hint: p.title_hint?.trim() || null };
  }
  return p;
}
