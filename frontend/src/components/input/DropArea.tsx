import { useRef, useState } from "react";

interface Props {
  accept: string;
  maxSizeMb?: number;
  value?: { name: string; size: number } | null;
  loading?: boolean;
  error?: string | null;
  onFile: (file: File) => void;
  onClear?: () => void;
}

export function DropArea({
  accept,
  maxSizeMb = 50,
  value,
  loading,
  error,
  onFile,
  onClear,
}: Props) {
  const [hover, setHover] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const onDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setHover(false);
    const f = e.dataTransfer.files?.[0];
    if (f) onFile(f);
  };

  const trigger = () => inputRef.current?.click();

  if (value) {
    return (
      <div
        className="flex items-center justify-between px-[14px] py-[12px]"
        style={{
          background: "var(--rib-bg1)",
          border: `1px solid ${error ? "var(--rib-critical)" : "var(--rib-line)"}`,
          borderRadius: 6,
        }}
      >
        <div className="flex items-center gap-3 min-w-0">
          <span
            style={{
              width: 28,
              height: 28,
              borderRadius: 4,
              display: "grid",
              placeItems: "center",
              background: "var(--rib-bg3)",
              color: "var(--rib-text1)",
              fontSize: 12,
              fontWeight: 600,
              flexShrink: 0,
            }}
          >
            {loading ? "…" : "PDF"}
          </span>
          <div className="min-w-0">
            <div
              className="font-mono truncate"
              style={{
                color: "var(--rib-text0)",
                fontSize: 13,
              }}
            >
              {value.name}
            </div>
            <div
              className="text-[12px]"
              style={{ color: "var(--rib-text2)" }}
            >
              {(value.size / 1024 / 1024).toFixed(2)} MB
              {loading ? " · uploading…" : ""}
              {error ? ` · ${error}` : ""}
            </div>
          </div>
        </div>
        {onClear && (
          <button
            type="button"
            onClick={onClear}
            className="text-[12px] font-ui"
            style={{ color: "var(--rib-text2)", cursor: "pointer", padding: 6 }}
          >
            Clear
          </button>
        )}
      </div>
    );
  }

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setHover(true);
      }}
      onDragLeave={() => setHover(false)}
      onDrop={onDrop}
      onClick={trigger}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && trigger()}
      className="flex flex-col items-center justify-center gap-2 cursor-pointer select-none"
      style={{
        border: `1px dashed ${hover ? "var(--rib-line2)" : "var(--rib-line)"}`,
        borderRadius: 6,
        padding: "26px 16px",
        background: hover ? "var(--rib-bg2)" : "var(--rib-bg1)",
        transition: "all 0.15s",
      }}
    >
      <div
        className="font-ui text-[13px]"
        style={{ color: "var(--rib-text1)" }}
      >
        Drop PDF here, or <span style={{ color: "var(--rib-agent-auditor)" }}>browse</span>
      </div>
      <div
        className="text-[11.5px]"
        style={{ color: "var(--rib-text3)" }}
      >
        application/pdf · max {maxSizeMb} MB
      </div>
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) onFile(f);
          e.target.value = "";
        }}
      />
    </div>
  );
}
