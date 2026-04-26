import { useState } from "react";
import type { PaperSource } from "../../types/schemas";
import { api } from "../../api/client";
import { InputField } from "./InputField";
import { TabSwitcher } from "./TabSwitcher";
import { DropArea } from "./DropArea";
import { SectionCard } from "./SectionCard";

type PaperTab = "arxiv" | "pdf_url" | "upload" | "raw_text" | "none";

const TABS = [
  { key: "arxiv" as const, label: "arXiv URL" },
  { key: "pdf_url" as const, label: "PDF URL" },
  { key: "upload" as const, label: "Upload PDF" },
  { key: "raw_text" as const, label: "Paste text" },
  { key: "none" as const, label: "No paper", hint: "Code-only audit" },
];

interface Props {
  value: PaperSource;
  onChange: (value: PaperSource) => void;
}

export function PaperInputPanel({ value, onChange }: Props) {
  const [tab, setTab] = useState<PaperTab>(value.kind);
  const [arxivUrl, setArxivUrl] = useState(
    value.kind === "arxiv" ? value.arxiv_url : "",
  );
  const [pdfUrl, setPdfUrl] = useState(
    value.kind === "pdf_url" ? value.url : "",
  );
  const [rawText, setRawText] = useState(
    value.kind === "raw_text" ? value.text : "",
  );
  const [titleHint, setTitleHint] = useState(
    value.kind === "raw_text" || value.kind === "none"
      ? value.title_hint ?? ""
      : "",
  );
  const [uploadFile, setUploadFile] = useState<{
    name: string;
    size: number;
    uploadId: string;
  } | null>(value.kind === "upload" ? null : null);
  const [uploadMeta, setUploadMeta] = useState<{
    loading: boolean;
    error: string | null;
  }>({ loading: false, error: null });

  const switchTab = (t: PaperTab) => {
    setTab(t);
    if (t === "arxiv") onChange({ kind: "arxiv", arxiv_url: arxivUrl });
    else if (t === "pdf_url") onChange({ kind: "pdf_url", url: pdfUrl });
    else if (t === "upload")
      onChange(
        uploadFile
          ? { kind: "upload", upload_id: uploadFile.uploadId }
          : { kind: "upload", upload_id: "" },
      );
    else if (t === "raw_text")
      onChange({
        kind: "raw_text",
        text: rawText,
        title_hint: titleHint || null,
      });
    else if (t === "none")
      onChange({ kind: "none", title_hint: titleHint || null });
  };

  const onUpload = async (file: File) => {
    setUploadMeta({ loading: true, error: null });
    setUploadFile({ name: file.name, size: file.size, uploadId: "" });
    try {
      const resp = await api.uploadPdf(file);
      setUploadFile({
        name: file.name,
        size: file.size,
        uploadId: resp.upload_id,
      });
      setUploadMeta({ loading: false, error: null });
      onChange({ kind: "upload", upload_id: resp.upload_id });
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setUploadMeta({ loading: false, error: msg });
    }
  };

  return (
    <SectionCard
      eyebrow="Paper"
      title="Research paper"
      subtitle="Source of the claims to audit. Skip if you just want a code-only methodology check."
      accent="paper"
      right={<TabSwitcher tabs={TABS} value={tab} onChange={switchTab} />}
    >
      {tab === "arxiv" && (
        <InputField
          label="arXiv PDF URL"
          placeholder="https://arxiv.org/pdf/2401.12345"
          value={arxivUrl}
          mono
          onChange={(e) => {
            setArxivUrl(e.target.value);
            onChange({ kind: "arxiv", arxiv_url: e.target.value });
          }}
          hint="Only /pdf variants are supported."
        />
      )}
      {tab === "pdf_url" && (
        <InputField
          label="Direct PDF URL"
          placeholder="https://example.org/paper.pdf"
          value={pdfUrl}
          mono
          onChange={(e) => {
            setPdfUrl(e.target.value);
            onChange({ kind: "pdf_url", url: e.target.value });
          }}
        />
      )}
      {tab === "upload" && (
        <DropArea
          accept="application/pdf"
          maxSizeMb={50}
          value={uploadFile}
          loading={uploadMeta.loading}
          error={uploadMeta.error}
          onFile={onUpload}
          onClear={() => {
            setUploadFile(null);
            setUploadMeta({ loading: false, error: null });
            onChange({ kind: "upload", upload_id: "" });
          }}
        />
      )}
      {tab === "raw_text" && (
        <div className="space-y-3">
          <InputField
            label="Title hint (optional)"
            placeholder="e.g. TRIDENT: Tri-modal drone detection"
            value={titleHint}
            onChange={(e) => {
              setTitleHint(e.target.value);
              onChange({
                kind: "raw_text",
                text: rawText,
                title_hint: e.target.value || null,
              });
            }}
          />
          <InputField
            as="textarea"
            label="Paper text"
            placeholder="Paste the full paper text (abstract, methods, results, …). 500–500,000 chars."
            value={rawText}
            onChange={(e) => {
              setRawText(e.target.value);
              onChange({
                kind: "raw_text",
                text: e.target.value,
                title_hint: titleHint || null,
              });
            }}
            hint={`${rawText.length.toLocaleString()} / 500,000 chars`}
          />
        </div>
      )}
      {tab === "none" && (
        <div className="space-y-3">
          <div
            className="p-[14px] rounded-md"
            style={{
              border: "1px dashed var(--rib-line2)",
              background: "var(--rib-bg2)",
              color: "var(--rib-text1)",
              fontSize: 13,
              lineHeight: "20px",
            }}
          >
            <div
              className="mb-1 text-[11px] font-semibold uppercase"
              style={{
                color: "var(--rib-text2)",
                letterSpacing: "0.12em",
              }}
            >
              Code-only mode
            </div>
            No paper will be fetched. If the repo ships an extensive README,
            the Paper Analyst will treat it as the paper and extract claims
            from it; otherwise that phase is skipped and the remaining agents
            audit the repo against general ML-methodology checks.
          </div>
          <InputField
            label="Repo description (optional)"
            placeholder="e.g. fraud-detection LSTM training pipeline"
            value={titleHint}
            onChange={(e) => {
              setTitleHint(e.target.value);
              onChange({
                kind: "none",
                title_hint: e.target.value || null,
              });
            }}
            hint="Helps the agents know what kind of ML system they're reading."
          />
        </div>
      )}
    </SectionCard>
  );
}
