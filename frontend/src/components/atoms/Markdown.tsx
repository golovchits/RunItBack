import type { ReactNode } from "react";

/**
 * Tiny inline markdown renderer: paragraphs split on blank lines, with
 * **bold** and `inline code`. Enough for agent-produced markdown that
 * mostly formats emphasis, metric values, and file paths.
 */
export function Markdown({ src }: { src: string }) {
  if (!src) return null;
  const paras = src.split(/\n\n+/);
  return (
    <>
      {paras.map((p, i) => (
        <p
          key={i}
          className="text-pretty"
          style={{
            margin: i === 0 ? 0 : "12px 0 0",
            color: "var(--rib-text1)",
          }}
        >
          {renderInline(p, i)}
        </p>
      ))}
    </>
  );
}

function renderInline(text: string, key: number): ReactNode[] {
  const parts: ReactNode[] = [];
  const re = /(\*\*([^*]+)\*\*|`([^`]+)`)/g;
  let idx = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text))) {
    if (m.index > idx) parts.push(text.slice(idx, m.index));
    if (m[2]) {
      parts.push(
        <strong
          key={`${key}-${m.index}-b`}
          style={{ fontWeight: 600, color: "var(--rib-text0)" }}
        >
          {m[2]}
        </strong>,
      );
    } else if (m[3]) {
      parts.push(
        <code
          key={`${key}-${m.index}-c`}
          className="font-mono"
          style={{
            fontSize: 12.5,
            background: "var(--rib-bg3)",
            color: "var(--rib-mono)",
            padding: "1px 5px",
            borderRadius: 3,
            border: "1px solid var(--rib-line)",
          }}
        >
          {m[3]}
        </code>,
      );
    }
    idx = m.index + m[0].length;
  }
  if (idx < text.length) parts.push(text.slice(idx));
  return parts;
}
