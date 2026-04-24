import { useMemo, type ReactNode } from "react";
import type { CodeSpan } from "../../types/schemas";

interface Props {
  span?: CodeSpan | null;
  /** Override content entirely (e.g. live viewer fetches via API). */
  content?: string;
  filePath?: string;
  lineStart?: number;
  lineEnd?: number;
  /** Explicit highlight line set (1-indexed). Otherwise [start, end]. */
  highlightLines?: number[];
  maxHeight?: number | string;
  showHeader?: boolean;
}

/**
 * Styled pre/code with line numbers, red-line highlighting, and an overview
 * ruler. Designed to match the handoff "Monaco-looking" aesthetic without
 * pulling the Monaco dep. Python/ML-ish token highlighting is a best-effort
 * regex; agents primarily emit Python so this is the sweet spot.
 */
export function CodeViewer({
  span,
  content,
  filePath,
  lineStart,
  lineEnd,
  highlightLines,
  maxHeight,
  showHeader = true,
}: Props) {
  const resolved = useMemo(() => {
    const text =
      content != null ? content : span?.snippet ?? "";
    const start = lineStart ?? span?.line_start ?? 1;
    const end =
      lineEnd ??
      span?.line_end ??
      start + Math.max(0, text.split("\n").length - 1);
    // Prefer an explicit highlight set (passed by the caller, or supplied
    // on the span itself); otherwise fall back to the span's full range.
    const hl = new Set<number>(
      highlightLines ??
        span?.highlight_lines ??
        rangeInclusive(span?.line_start ?? start, span?.line_end ?? end),
    );
    return { text, start, end, hl, path: filePath ?? span?.file_path ?? "" };
  }, [content, span, lineStart, lineEnd, highlightLines, filePath]);

  if (!resolved.text) {
    return (
      <EmptyViewer path={resolved.path} message="No snippet available" />
    );
  }
  const lines = resolved.text.split("\n");
  const gutterDigits = String(resolved.start + lines.length - 1).length;

  return (
    <div
      style={{
        background: "var(--rib-bg0)",
        border: "1px solid var(--rib-line)",
        borderRadius: 6,
        fontFamily:
          '"JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, monospace',
        fontSize: 12.5,
        lineHeight: "20px",
        color: "var(--rib-mono)",
        overflow: "hidden",
        position: "relative",
      }}
    >
      {showHeader && (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "8px 12px",
            borderBottom: "1px solid var(--rib-line)",
            background: "var(--rib-bg2)",
          }}
        >
          <span
            className="font-mono"
            style={{ fontSize: 12, color: "var(--rib-text1)" }}
          >
            {resolved.path || "—"}
          </span>
          <span
            style={{
              fontSize: 11,
              color: "var(--rib-text2)",
              fontFamily:
                '"Inter", -apple-system, BlinkMacSystemFont, sans-serif',
              letterSpacing: "0.04em",
            }}
          >
            L{resolved.start}–L{resolved.end}
          </span>
        </div>
      )}
      <div
        className="rib-scrollbar"
        style={{
          display: "flex",
          position: "relative",
          maxHeight,
          overflow: maxHeight ? "auto" : "visible",
        }}
      >
        <div style={{ flex: 1, padding: "10px 0", minWidth: 0 }}>
          {lines.map((line, i) => {
            const ln = resolved.start + i;
            const isHl = resolved.hl.has(ln);
            return (
              <div
                key={i}
                style={{
                  display: "grid",
                  gridTemplateColumns: `${gutterDigits * 8 + 32}px 1fr`,
                  background: isHl ? "var(--rib-code-hl)" : "transparent",
                  borderLeft: `3px solid ${isHl ? "var(--rib-code-hl-edge)" : "transparent"}`,
                  paddingLeft: isHl ? 0 : 3,
                  minHeight: 20,
                  // inline tokens to avoid tailwind rebuilds for every color
                  // (bg0 is the viewer bg; hl overlay is rgba).
                  ...(isHl
                    ? { background: "rgba(229,83,83,0.14)", borderLeft: "3px solid #e55353" }
                    : {}),
                }}
              >
                <div
                  style={{
                    textAlign: "right",
                    color: "var(--rib-text2)",
                    userSelect: "none",
                    paddingRight: 12,
                    paddingLeft: 4,
                    opacity: isHl ? 1 : 0.7,
                  }}
                >
                  {ln}
                </div>
                <div
                  className="rib-scrollbar"
                  style={{
                    whiteSpace: "pre",
                    overflowX: "auto",
                    paddingRight: 18,
                  }}
                >
                  {renderPyTokens(line) || " "}
                </div>
              </div>
            );
          })}
        </div>
        {/* overview ruler */}
        <div
          style={{
            width: 8,
            background: "var(--rib-bg2)",
            borderLeft: "1px solid var(--rib-line)",
            position: "relative",
            flexShrink: 0,
          }}
        >
          {lines.map((_, i) => {
            const ln = resolved.start + i;
            if (!resolved.hl.has(ln)) return null;
            const top = (i / lines.length) * 100;
            const h = (1 / lines.length) * 100;
            return (
              <div
                key={i}
                style={{
                  position: "absolute",
                  top: `${top}%`,
                  left: 1,
                  right: 1,
                  height: `max(3px, ${h}%)`,
                  background: "#e55353",
                  borderRadius: 1,
                }}
              />
            );
          })}
        </div>
      </div>
    </div>
  );
}

function rangeInclusive(a: number, b: number): number[] {
  if (a > b) [a, b] = [b, a];
  const out: number[] = [];
  for (let i = a; i <= b; i++) out.push(i);
  return out;
}

function EmptyViewer({ path, message }: { path: string; message: string }) {
  return (
    <div
      style={{
        background: "var(--rib-bg0)",
        border: "1px dashed var(--rib-line2)",
        borderRadius: 6,
        padding: "24px 20px",
        color: "var(--rib-text2)",
        fontSize: 13,
      }}
    >
      <div
        className="font-mono"
        style={{ color: "var(--rib-text1)", marginBottom: 6 }}
      >
        {path || "—"}
      </div>
      {message}
    </div>
  );
}

const PY_KEYWORDS = new Set([
  "def",
  "return",
  "for",
  "in",
  "if",
  "else",
  "elif",
  "import",
  "from",
  "as",
  "class",
  "with",
  "try",
  "except",
  "finally",
  "lambda",
  "pass",
  "None",
  "True",
  "False",
  "not",
  "and",
  "or",
  "is",
  "raise",
  "yield",
  "global",
  "nonlocal",
  "async",
  "await",
  "self",
  "cls",
  "break",
  "continue",
  "while",
  "assert",
]);

const PY_RE =
  /(#[^\n]*)|("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')|(\b[0-9]+\.?[0-9]*\b)|(\b[A-Za-z_][A-Za-z0-9_]*\b)|(\s+)|([^\w\s]+)/g;

function renderPyTokens(line: string): ReactNode {
  const out: ReactNode[] = [];
  let m: RegExpExecArray | null;
  const re = new RegExp(PY_RE.source, "g");
  let i = 0;
  while ((m = re.exec(line))) {
    if (m[1]) {
      out.push(
        <span key={i++} style={{ color: "#6b7685" }}>
          {m[1]}
        </span>,
      );
    } else if (m[2]) {
      out.push(
        <span key={i++} style={{ color: "#b5a06a" }}>
          {m[2]}
        </span>,
      );
    } else if (m[3]) {
      out.push(
        <span key={i++} style={{ color: "#b28cd9" }}>
          {m[3]}
        </span>,
      );
    } else if (m[4]) {
      if (PY_KEYWORDS.has(m[4])) {
        out.push(
          <span key={i++} style={{ color: "#c97aa7" }}>
            {m[4]}
          </span>,
        );
      } else {
        out.push(m[4]);
      }
    } else if (m[5]) {
      out.push(m[5]);
    } else if (m[6]) {
      out.push(
        <span key={i++} style={{ color: "var(--rib-text2)" }}>
          {m[6]}
        </span>,
      );
    }
  }
  return out;
}
