import { useEffect, useRef, useState } from "react";
import { useAudit, type ActivityMessage } from "../../state/audit";
import { AGENT_META } from "../../util/tokens";
import { AgentBadge } from "../atoms";

export function ActivityFeed() {
  const activity = useAudit((s) => s.activity);
  const scrollRef = useRef<HTMLDivElement>(null);
  const [autoScroll, setAutoScroll] = useState(true);

  useEffect(() => {
    if (!autoScroll || !scrollRef.current) return;
    scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [activity, autoScroll]);

  return (
    <section
      className="flex flex-col h-full min-w-0"
      style={{ background: "var(--rib-bg0)" }}
    >
      <header
        className="flex items-center justify-between px-5 py-3"
        style={{ borderBottom: "1px solid var(--rib-line)" }}
      >
        <div className="flex items-center gap-3">
          <div
            className="text-[11px] font-semibold uppercase"
            style={{
              color: "var(--rib-text2)",
              letterSpacing: "0.14em",
            }}
          >
            Activity
          </div>
          <div
            className="text-[12px] font-mono tabular-nums"
            style={{ color: "var(--rib-text3)" }}
          >
            {activity.length.toLocaleString()} events
          </div>
        </div>
        <button
          type="button"
          onClick={() => setAutoScroll((v) => !v)}
          className="font-ui"
          style={{
            fontSize: 11.5,
            color: autoScroll ? "var(--rib-agent-auditor)" : "var(--rib-text2)",
            padding: "3px 8px",
            borderRadius: 4,
            border: `1px solid ${
              autoScroll ? "rgba(90,140,217,0.33)" : "var(--rib-line2)"
            }`,
            cursor: "pointer",
            background: "transparent",
          }}
        >
          {autoScroll ? "Auto-scroll on" : "Auto-scroll off"}
        </button>
      </header>
      <div
        ref={scrollRef}
        className="flex-1 overflow-auto rib-scrollbar"
        onScroll={(e) => {
          const el = e.currentTarget;
          const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
          setAutoScroll(atBottom);
        }}
      >
        <ol className="px-5 py-3 flex flex-col gap-[6px]">
          {activity.map((a) => (
            <ActivityRow key={a.id} msg={a} />
          ))}
          {activity.length === 0 && (
            <li
              className="text-[13px] py-10 text-center"
              style={{ color: "var(--rib-text3)" }}
            >
              Waiting for the first agent to start…
            </li>
          )}
        </ol>
      </div>
    </section>
  );
}

function ActivityRow({ msg }: { msg: ActivityMessage }) {
  const [open, setOpen] = useState(false);
  const meta = msg.agent ? AGENT_META[msg.agent] : null;
  const time = msg.ts
    ? new Date(msg.ts).toLocaleTimeString(undefined, {
        hour12: false,
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      })
    : "";

  const common = {
    fontSize: 13,
    lineHeight: "20px",
  } as const;

  if (msg.kind === "thinking") {
    return (
      <li
        className="flex items-start gap-3"
        style={{ color: "var(--rib-text3)" }}
      >
        <span
          className="font-mono tabular-nums"
          style={{
            fontSize: 11,
            color: "var(--rib-text3)",
            width: 60,
            flexShrink: 0,
          }}
        >
          {time}
        </span>
        {meta && <Dot fg={meta.fg} />}
        <div
          className="italic text-pretty"
          style={{ ...common, color: "var(--rib-text2)" }}
        >
          {msg.text}
        </div>
      </li>
    );
  }

  if (msg.kind === "tool_use" || msg.kind === "tool_result") {
    const isUse = msg.kind === "tool_use";
    return (
      <li>
        <div className="flex items-start gap-3">
          <span
            className="font-mono tabular-nums"
            style={{
              fontSize: 11,
              color: "var(--rib-text3)",
              width: 60,
              flexShrink: 0,
            }}
          >
            {time}
          </span>
          {meta && <Dot fg={meta.fg} />}
          <button
            type="button"
            onClick={() => setOpen((o) => !o)}
            className="flex-1 min-w-0 text-left font-mono"
            style={{
              ...common,
              color: isUse ? "var(--rib-text1)" : msg.success === false ? "var(--rib-critical)" : "var(--rib-text2)",
              cursor: "pointer",
              background: "transparent",
              padding: 0,
              border: "none",
            }}
          >
            <span
              style={{
                color: isUse ? "var(--rib-agent-auditor)" : "var(--rib-text3)",
                marginRight: 8,
              }}
            >
              {isUse ? "▶" : "◀"}
            </span>
            <span style={{ color: "var(--rib-text0)" }}>{msg.tool}</span>
            <span style={{ color: "var(--rib-text2)", marginLeft: 8 }}>
              {truncate(msg.text, 200)}
            </span>
          </button>
        </div>
        {open && msg.text.length > 200 && (
          <pre
            className="rib-scrollbar font-mono mt-1 ml-[88px] px-3 py-2"
            style={{
              fontSize: 11.5,
              lineHeight: "18px",
              background: "var(--rib-bg1)",
              border: "1px solid var(--rib-line)",
              borderRadius: 4,
              color: "var(--rib-text1)",
              maxHeight: 220,
              overflow: "auto",
              whiteSpace: "pre-wrap",
            }}
          >
            {msg.text}
          </pre>
        )}
      </li>
    );
  }

  if (msg.kind === "finding") {
    return (
      <li
        className="flex items-start gap-3 px-3 py-2"
        style={{
          background: "rgba(229,83,83,0.06)",
          border: "1px solid rgba(229,83,83,0.25)",
          borderRadius: 4,
        }}
      >
        <span
          className="font-mono tabular-nums"
          style={{
            fontSize: 11,
            color: "var(--rib-text3)",
            width: 60,
            flexShrink: 0,
          }}
        >
          {time}
        </span>
        <span
          style={{
            color: "var(--rib-critical)",
            fontWeight: 700,
            fontSize: 10.5,
            letterSpacing: "0.12em",
            marginTop: 2,
          }}
        >
          FINDING
        </span>
        <div className="flex-1 min-w-0">
          <div
            style={{
              color: "var(--rib-text0)",
              fontSize: 13.5,
              fontWeight: 500,
              lineHeight: "20px",
            }}
          >
            {msg.text}
          </div>
          {msg.detail && (
            <div
              className="font-mono mt-1"
              style={{ color: "var(--rib-text2)", fontSize: 11.5 }}
            >
              {msg.detail}
            </div>
          )}
        </div>
      </li>
    );
  }

  if (msg.kind === "validation") {
    return (
      <li className="flex items-start gap-3">
        <span
          className="font-mono tabular-nums"
          style={{
            fontSize: 11,
            color: "var(--rib-text3)",
            width: 60,
            flexShrink: 0,
          }}
        >
          {time}
        </span>
        {meta && <Dot fg={meta.fg} />}
        <div
          className="flex-1 min-w-0 font-mono"
          style={{ ...common, color: "var(--rib-text1)" }}
        >
          <span style={{ color: "var(--rib-agent-validator)" }}>verdict</span>{" "}
          <span style={{ color: "var(--rib-text0)" }}>{msg.text}</span>
          {msg.detail && (
            <span style={{ color: "var(--rib-text2)", marginLeft: 6 }}>
              · {msg.detail}
            </span>
          )}
        </div>
      </li>
    );
  }

  if (msg.kind === "file_opened") {
    return (
      <li
        className="flex items-start gap-3"
        style={{ color: "var(--rib-text2)" }}
      >
        <span
          className="font-mono tabular-nums"
          style={{
            fontSize: 11,
            color: "var(--rib-text3)",
            width: 60,
            flexShrink: 0,
          }}
        >
          {time}
        </span>
        {meta && <Dot fg={meta.fg} />}
        <div
          className="font-mono"
          style={{ ...common, color: "var(--rib-text1)" }}
        >
          <span style={{ color: "var(--rib-text3)", marginRight: 6 }}>open</span>
          {msg.text}
        </div>
      </li>
    );
  }

  if (msg.kind === "status" || msg.kind === "finished" || msg.kind === "claims" || msg.kind === "fallback" || msg.kind === "error") {
    const color =
      msg.kind === "error"
        ? "var(--rib-critical)"
        : msg.kind === "fallback"
          ? "var(--rib-high)"
          : "var(--rib-text1)";
    return (
      <li className="flex items-start gap-3">
        <span
          className="font-mono tabular-nums"
          style={{
            fontSize: 11,
            color: "var(--rib-text3)",
            width: 60,
            flexShrink: 0,
          }}
        >
          {time}
        </span>
        {meta ? <Dot fg={meta.fg} /> : <Dot fg="var(--rib-text3)" />}
        <div
          className="text-pretty"
          style={{ ...common, color }}
        >
          {msg.text}
        </div>
      </li>
    );
  }

  // Default: message
  return (
    <li className="flex items-start gap-3 py-1">
      <span
        className="font-mono tabular-nums"
        style={{
          fontSize: 11,
          color: "var(--rib-text3)",
          width: 60,
          flexShrink: 0,
        }}
      >
        {time}
      </span>
      {meta && <Dot fg={meta.fg} />}
      <div className="flex-1 min-w-0">
        {msg.agent && (
          <div className="mb-1">
            <AgentBadge agent={msg.agent} size="sm" />
          </div>
        )}
        <div
          className="text-pretty"
          style={{ ...common, color: "var(--rib-text0)" }}
        >
          {truncate(msg.text, 400)}
        </div>
      </div>
    </li>
  );
}

function Dot({ fg }: { fg: string }) {
  return (
    <span
      style={{
        width: 6,
        height: 6,
        borderRadius: 3,
        background: fg,
        marginTop: 8,
        flexShrink: 0,
      }}
    />
  );
}

function truncate(s: string, n: number) {
  if (!s) return "";
  if (s.length <= n) return s;
  return s.slice(0, n - 1) + "…";
}
