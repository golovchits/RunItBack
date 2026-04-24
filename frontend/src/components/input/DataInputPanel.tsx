import { useState } from "react";
import type { DataSource } from "../../types/schemas";
import { InputField } from "./InputField";
import { SectionCard } from "./SectionCard";

type DataKind = "url" | "bundled" | "skip";

const KIND_OPTIONS: Array<{ key: DataKind; label: string; hint: string }> = [
  {
    key: "url",
    label: "URL (direct download)",
    hint: "Auth-free HTTP(S) — HuggingFace, S3 presigned, Cloudflare R2, plain HTTP.",
  },
  {
    key: "bundled",
    label: "Bundled in repo",
    hint: "Data sits inside the cloned repo at a subpath (commit a sample, or use git-lfs).",
  },
  {
    key: "skip",
    label: "None (skip data audit)",
    hint: "Code-only audit. EDA section will be empty but findings still run.",
  },
];

interface Props {
  value: DataSource;
  onChange: (value: DataSource) => void;
  dataStructureText: string;
  onDataStructureTextChange: (text: string) => void;
}

const MAX_TREE_LEN = 200_000;

export function DataInputPanel({
  value,
  onChange,
  dataStructureText,
  onDataStructureTextChange,
}: Props) {
  // Map the backend's union to the 3 UI options. If the stored value
  // is DataSourceLocal (legacy or API-only), we surface as "skip" in
  // the UI — local isn't reachable from here anymore.
  const uiKind: DataKind =
    value.kind === "url" || value.kind === "bundled" || value.kind === "skip"
      ? value.kind
      : "skip";

  const [url, setUrl] = useState(value.kind === "url" ? value.url : "");
  const [sizeGb, setSizeGb] = useState<string>(
    value.kind === "url" && value.expected_size_gb != null
      ? String(value.expected_size_gb)
      : "",
  );
  const [subpath, setSubpath] = useState(
    value.kind === "bundled" ? value.subpath ?? "" : "",
  );
  const [treeHelpOpen, setTreeHelpOpen] = useState(false);
  const [urlHelpOpen, setUrlHelpOpen] = useState(false);
  const [sampleHelpOpen, setSampleHelpOpen] = useState(false);

  const switchKind = (k: DataKind) => {
    if (k === "url") {
      onChange({
        kind: "url",
        url,
        expected_size_gb: sizeGb ? parseFloat(sizeGb) : null,
      });
    } else if (k === "bundled") {
      onChange({ kind: "bundled", subpath: subpath || null });
    } else {
      onChange({ kind: "skip" });
    }
  };

  const treeLen = dataStructureText.length;
  const treeOver = treeLen > MAX_TREE_LEN;

  return (
    <SectionCard
      eyebrow="Data"
      title="Dataset"
      subtitle="Optional. Used for EDA (split balance, duplicates, corruption, leakage signals). Skip for code-only audits."
      accent="validator"
    >
      <div className="space-y-4">
        {/* Primary data source — dropdown */}
        <div className="space-y-2">
          <label
            className="block text-[11px] font-semibold uppercase"
            style={{
              color: "var(--rib-text2)",
              letterSpacing: "0.12em",
            }}
          >
            Data source
          </label>
          <select
            value={uiKind}
            onChange={(e) => switchKind(e.target.value as DataKind)}
            className="w-full rounded-md px-3 py-2"
            style={{
              background: "var(--rib-bg1)",
              border: "1px solid var(--rib-line2)",
              color: "var(--rib-text0)",
              fontSize: 14,
            }}
          >
            {KIND_OPTIONS.map((o) => (
              <option key={o.key} value={o.key}>
                {o.label}
              </option>
            ))}
          </select>
          <div
            className="text-[12px]"
            style={{
              color: "var(--rib-text2)",
              lineHeight: "16px",
            }}
          >
            {KIND_OPTIONS.find((o) => o.key === uiKind)?.hint}
          </div>
        </div>

        {/* URL-specific fields */}
        {uiKind === "url" && (
          <div className="space-y-3">
            <InputField
              label="Download URL"
              placeholder="https://huggingface.co/datasets/me/ds/resolve/main/sample.tar.gz"
              value={url}
              mono
              onChange={(e) => {
                setUrl(e.target.value);
                onChange({
                  kind: "url",
                  url: e.target.value,
                  expected_size_gb: sizeGb ? parseFloat(sizeGb) : null,
                });
              }}
              hint="Single archive (.tar.gz, .zip) that returns file bytes (not a share page)."
            />
            <InputField
              label="Expected size (GB, optional)"
              placeholder="0.5"
              value={sizeGb}
              inputMode="decimal"
              onChange={(e) => {
                setSizeGb(e.target.value);
                onChange({
                  kind: "url",
                  url,
                  expected_size_gb: e.target.value
                    ? parseFloat(e.target.value)
                    : null,
                });
              }}
              hint="Server cap is 2 GB. Validator has ~10 min total — smaller samples run faster."
            />

            <Disclosure
              open={urlHelpOpen}
              onToggle={() => setUrlHelpOpen((v) => !v)}
              title="How to host a dataset for auditing"
            >
              <div className="space-y-3">
                <BlockHeading>HuggingFace datasets (recommended)</BlockHeading>
                <Code>
                  {`huggingface-cli upload my-user/my-dataset ./sample
# URL: https://huggingface.co/datasets/my-user/my-dataset/resolve/main/<file>`}
                </Code>

                <BlockHeading>S3 presigned URL (7-day expiry)</BlockHeading>
                <Code>
                  {`aws s3 cp sample.tar.gz s3://my-bucket/
aws s3 presign s3://my-bucket/sample.tar.gz --expires-in 604800`}
                </Code>

                <BlockHeading>Cloudflare R2 public bucket</BlockHeading>
                <Code>
                  {`wrangler r2 object put my-bucket/sample.tar.gz -f sample.tar.gz
# make the bucket public, URL is https://pub-<hash>.r2.dev/...`}
                </Code>

                <div
                  className="mt-2 pt-2"
                  style={{
                    borderTop: "1px dashed var(--rib-line2)",
                    color: "var(--rib-text2)",
                    fontSize: 12,
                  }}
                >
                  <strong>Won't work:</strong> Google Drive shares, Dropbox
                  share pages, SharePoint / OneDrive, anything behind auth
                  or a "click to download" page.
                </div>
              </div>
            </Disclosure>

            <Disclosure
              open={sampleHelpOpen}
              onToggle={() => setSampleHelpOpen((v) => !v)}
              title="Got a 10 GB dataset? Make a sample."
            >
              <div className="space-y-3">
                <div
                  style={{
                    color: "var(--rib-text2)",
                    fontSize: 12,
                    lineHeight: "18px",
                  }}
                >
                  Bigger isn't better — the Validator has ~10 min total.
                  A stratified 500 MB slice gives better signal than a
                  naive 5 GB one. Pair with a pasted tree listing below
                  for full-dataset split / leakage checks.
                </div>

                <BlockHeading>Stratified (one file per class)</BlockHeading>
                <Code>
                  {`find /data -type f | shuf -n 1000 \\
  | tar -czf sample.tar.gz -T -`}
                </Code>

                <BlockHeading>Size-limited (quick sanity)</BlockHeading>
                <Code>
                  {`find /data -type f -size -10M | head -500 \\
  | tar -czf sample.tar.gz -T -`}
                </Code>

                <BlockHeading>First file per subdir (preview)</BlockHeading>
                <Code>
                  {`find /data -maxdepth 2 -type f \\
  | awk -F/ '!seen[$(NF-1)]++' \\
  | tar -czf sample.tar.gz -T -`}
                </Code>
              </div>
            </Disclosure>
          </div>
        )}

        {/* Bundled-specific fields */}
        {uiKind === "bundled" && (
          <InputField
            label="Subpath within repo (optional)"
            placeholder="data/"
            value={subpath}
            mono
            onChange={(e) => {
              setSubpath(e.target.value);
              onChange({
                kind: "bundled",
                subpath: e.target.value || null,
              });
            }}
            hint="Leave blank to treat the whole repo as the dataset. Works with your own fork."
          />
        )}

        {/* Skip-specific explainer */}
        {uiKind === "skip" && (
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
              Skip data audit
            </div>
            Content-level EDA (corruption, duplicates, format) will be
            skipped. Code-side findings and paper-vs-code checks still
            run. Paste a tree listing below to still get split-balance +
            leakage checks.
          </div>
        )}

        {/* Always-visible: dataset structure textarea */}
        <div
          className="pt-4 mt-2"
          style={{ borderTop: "1px solid var(--rib-line)" }}
        >
          <label
            className="block text-[11px] font-semibold uppercase"
            style={{
              color: "var(--rib-text2)",
              letterSpacing: "0.12em",
              marginBottom: 6,
            }}
          >
            Dataset structure (optional)
          </label>
          <div
            className="text-[12px] mb-2"
            style={{ color: "var(--rib-text2)", lineHeight: "16px" }}
          >
            Paste a <code>tree</code>/<code>find</code> listing of the full
            dataset. Enables split-balance, filename-leakage, and extension-
            consistency checks even when the dataset itself is too big,
            private, or not direct-downloadable.
          </div>
          <textarea
            value={dataStructureText}
            onChange={(e) => onDataStructureTextChange(e.target.value)}
            rows={6}
            placeholder={`dataset/
├── train/
│   ├── class_a/ ...
│   └── class_b/ ...
└── val/
    └── ...`}
            className="w-full rounded-md px-3 py-2"
            style={{
              background: "var(--rib-bg1)",
              border: `1px solid ${treeOver ? "var(--rib-sev-high, #c66)" : "var(--rib-line2)"}`,
              color: "var(--rib-text0)",
              fontSize: 12,
              fontFamily: "var(--rib-font-mono, monospace)",
              lineHeight: "16px",
              resize: "vertical",
            }}
          />
          <div
            className="flex justify-between mt-1 text-[11px]"
            style={{ color: treeOver ? "var(--rib-sev-high, #c66)" : "var(--rib-text2)" }}
          >
            <span>
              {treeOver
                ? `Over 200 KB cap — trim with \`tree -L 3\` or similar.`
                : "Max 200 KB. Trim depth if larger."}
            </span>
            <span className="font-mono tabular-nums">
              {treeLen.toLocaleString()} / {MAX_TREE_LEN.toLocaleString()}
            </span>
          </div>

          <div className="mt-2">
            <Disclosure
              open={treeHelpOpen}
              onToggle={() => setTreeHelpOpen((v) => !v)}
              title="How to generate a tree listing"
            >
              <div className="space-y-3">
                <BlockHeading>Basic (4 levels deep)</BlockHeading>
                <Code>
                  tree -L 4 --noreport /path/to/dataset &gt; structure.txt
                </Code>

                <BlockHeading>Shallow (huge trees)</BlockHeading>
                <Code>tree -L 3 /path/to/dataset &gt; structure.txt</Code>

                <BlockHeading>Directories only</BlockHeading>
                <Code>tree -L 4 -d /path/to/dataset &gt; structure.txt</Code>

                <BlockHeading>No `tree` command? Use `find`</BlockHeading>
                <Code>
                  find /path/to/dataset -maxdepth 4 &gt; structure.txt
                </Code>

                <div
                  className="mt-2 pt-2"
                  style={{
                    borderTop: "1px dashed var(--rib-line2)",
                    color: "var(--rib-text2)",
                    fontSize: 12,
                  }}
                >
                  Then paste the contents of <code>structure.txt</code>{" "}
                  into the textarea above.
                </div>
              </div>
            </Disclosure>
          </div>
        </div>
      </div>
    </SectionCard>
  );
}

// --- small presentational helpers ---

function Disclosure({
  open,
  onToggle,
  title,
  children,
}: {
  open: boolean;
  onToggle: () => void;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div
      className="rounded-md"
      style={{
        border: "1px solid var(--rib-line2)",
        background: "var(--rib-bg2)",
      }}
    >
      <button
        type="button"
        onClick={onToggle}
        className="flex items-center justify-between w-full px-3 py-2"
        style={{
          color: "var(--rib-text1)",
          fontSize: 12,
          fontWeight: 500,
        }}
      >
        <span>{title}</span>
        <span style={{ color: "var(--rib-text3)" }}>{open ? "−" : "+"}</span>
      </button>
      {open && (
        <div
          className="px-3 pb-3"
          style={{ borderTop: "1px solid var(--rib-line2)" }}
        >
          <div className="pt-3">{children}</div>
        </div>
      )}
    </div>
  );
}

function BlockHeading({ children }: { children: React.ReactNode }) {
  return (
    <div
      className="text-[10px] font-semibold uppercase"
      style={{
        color: "var(--rib-text2)",
        letterSpacing: "0.12em",
      }}
    >
      {children}
    </div>
  );
}

function Code({ children }: { children: React.ReactNode }) {
  return (
    <pre
      className="rounded-md px-3 py-2 overflow-auto"
      style={{
        background: "var(--rib-bg0)",
        border: "1px solid var(--rib-line2)",
        color: "var(--rib-text0)",
        fontSize: 11,
        fontFamily: "var(--rib-font-mono, monospace)",
        lineHeight: "16px",
        whiteSpace: "pre",
      }}
    >
      {children}
    </pre>
  );
}
