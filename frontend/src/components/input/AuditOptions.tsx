import { InputField } from "./InputField";

interface Props {
  timeoutMinutes: number;
  includeEda: boolean;
  includeSuggestedFixes: boolean;
  userNotes: string;
  onChange: (patch: {
    timeoutMinutes?: number;
    includeEda?: boolean;
    includeSuggestedFixes?: boolean;
    userNotes?: string;
  }) => void;
}

// Presets cover: tiny-repo sanity (25), default (45), thorough (60),
// generous (90), and max (120). Users can still type any value in
// [5, 120] if they want something off-preset.
const TIMEOUT_PRESETS = [25, 45, 60, 90, 120];

// Mirror of _TIMEOUT_FRACTIONS in backend/orchestrator/pipeline.py.
// Kept in sync manually — if the backend changes these fractions,
// update here too.
const PHASE_FRACTIONS: Array<{ name: string; fraction: number }> = [
  { name: "Paper", fraction: 1 / 5 },
  { name: "Code", fraction: 2 / 5 },
  { name: "Validator", fraction: 1 / 2 },
  { name: "Reviewer", fraction: 1 / 6 },
];

function fmtMin(m: number): string {
  if (m < 1) return `${Math.round(m * 60)}s`;
  if (Number.isInteger(m)) return `${m}m`;
  return `${Math.round(m)}m`;
}

export function AuditOptions({
  timeoutMinutes,
  includeEda,
  includeSuggestedFixes,
  userNotes,
  onChange,
}: Props) {
  const setTimeout = (v: number) => {
    const clamped = Math.max(5, Math.min(120, Math.round(v)));
    onChange({ timeoutMinutes: clamped });
  };

  return (
    <section
      style={{
        background: "var(--rib-bg1)",
        border: "1px solid var(--rib-line)",
        borderRadius: 8,
        padding: 20,
      }}
    >
      <div
        className="mb-4 text-[11px] font-semibold uppercase"
        style={{
          color: "var(--rib-text2)",
          letterSpacing: "0.14em",
        }}
      >
        Options
      </div>

      {/* Timeout selector — prominent, with description + per-phase breakdown */}
      <div
        className="mb-4 p-[14px] rounded-md"
        style={{
          background: "var(--rib-bg2)",
          border: "1px solid var(--rib-line2)",
        }}
      >
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 mb-2">
          <div>
            <div
              className="text-[13px] font-medium"
              style={{ color: "var(--rib-text0)" }}
            >
              Total timeout budget
            </div>
            <div
              className="text-[12px] mt-[2px]"
              style={{ color: "var(--rib-text2)", lineHeight: "16px" }}
            >
              Per-agent wall-clock cap. If any agent hits its phase cap,
              it degrades (partial findings, unvalidated claims) and the
              audit continues. Higher = more thorough, costlier, slower.
              Lower = cheap sanity run but agents may time out on real
              work.
            </div>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {TIMEOUT_PRESETS.map((preset) => {
            const active = timeoutMinutes === preset;
            return (
              <button
                key={preset}
                type="button"
                onClick={() => setTimeout(preset)}
                className="px-3 py-[6px] rounded-md text-[12px] font-medium"
                style={{
                  background: active
                    ? "var(--rib-agent-auditor)"
                    : "var(--rib-bg1)",
                  color: active ? "var(--rib-bg0)" : "var(--rib-text1)",
                  border: `1px solid ${active ? "var(--rib-agent-auditor)" : "var(--rib-line2)"}`,
                  cursor: "pointer",
                }}
              >
                {preset} min
              </button>
            );
          })}
          <div className="ml-auto flex items-center gap-2">
            <input
              type="number"
              min={5}
              max={120}
              value={timeoutMinutes}
              onChange={(e) =>
                setTimeout(parseInt(e.target.value || "45", 10))
              }
              className="w-[72px] text-right rounded-md px-2 py-[6px] font-mono tabular-nums"
              style={{
                background: "var(--rib-bg1)",
                border: "1px solid var(--rib-line2)",
                color: "var(--rib-text0)",
                fontSize: 12,
              }}
            />
            <span
              style={{
                color: "var(--rib-text2)",
                fontSize: 12,
              }}
            >
              min
            </span>
          </div>
        </div>

        {/* Live per-phase breakdown */}
        <div
          className="mt-3 pt-3 flex flex-wrap gap-4"
          style={{ borderTop: "1px dashed var(--rib-line2)" }}
        >
          <div
            className="text-[10px] font-semibold uppercase"
            style={{
              color: "var(--rib-text2)",
              letterSpacing: "0.12em",
            }}
          >
            Per-phase cap
          </div>
          {PHASE_FRACTIONS.map((p) => (
            <div
              key={p.name}
              className="flex items-baseline gap-1"
              style={{ fontSize: 12, color: "var(--rib-text1)" }}
            >
              <span style={{ color: "var(--rib-text2)" }}>{p.name}</span>
              <span className="font-mono tabular-nums font-medium">
                {fmtMin(timeoutMinutes * p.fraction)}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Toggles */}
      <div className="space-y-2 mb-4">
        <ToggleRow
          checked={includeEda}
          onChange={(v) => onChange({ includeEda: v })}
          label="Include data EDA in the report"
        />
        <ToggleRow
          checked={includeSuggestedFixes}
          onChange={(v) => onChange({ includeSuggestedFixes: v })}
          label="Generate suggested fixes"
        />
      </div>

      <InputField
        as="textarea"
        label="Notes to the agents (optional)"
        placeholder="I suspect data leakage in the preprocessing pipeline. The checkpoint download may be stale. Only audit the training loop, not the notebooks."
        value={userNotes}
        onChange={(e) => onChange({ userNotes: e.target.value })}
        hint={`${userNotes.length.toLocaleString()} / 5,000 chars · agents treat these as hints, not ground truth.`}
      />
    </section>
  );
}

function ToggleRow({
  checked,
  onChange,
  label,
  hint,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
  hint?: string;
}) {
  return (
    <label
      className="flex items-start gap-3 cursor-pointer"
      style={{ color: "var(--rib-text1)" }}
    >
      <span
        role="checkbox"
        aria-checked={checked}
        tabIndex={0}
        onClick={() => onChange(!checked)}
        onKeyDown={(e) => (e.key === " " ? onChange(!checked) : undefined)}
        style={{
          width: 32,
          height: 18,
          borderRadius: 999,
          background: checked ? "var(--rib-agent-auditor)" : "var(--rib-bg3)",
          border: `1px solid ${
            checked ? "var(--rib-agent-auditor)" : "var(--rib-line2)"
          }`,
          position: "relative",
          transition: "all 0.15s",
          flexShrink: 0,
          marginTop: 2,
        }}
      >
        <span
          style={{
            position: "absolute",
            top: 1,
            left: checked ? 15 : 1,
            width: 14,
            height: 14,
            borderRadius: 999,
            background: "var(--rib-text0)",
            transition: "left 0.15s",
          }}
        />
      </span>
      <span className="min-w-0">
        <span
          className="block text-[13px] font-ui"
          style={{ color: "var(--rib-text0)", fontWeight: 500 }}
          onClick={() => onChange(!checked)}
        >
          {label}
        </span>
        {hint && (
          <span
            className="block mt-[2px] text-[12px]"
            style={{ color: "var(--rib-text2)" }}
          >
            {hint}
          </span>
        )}
      </span>
    </label>
  );
}
