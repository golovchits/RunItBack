import type { ReactNode } from "react";
import type { DataEDA, Severity } from "../../types/schemas";
import { SEVERITY_META } from "../../util/tokens";

interface Props {
  eda?: DataEDA | null;
  empty?: boolean;
}

export function EDASummary({ eda, empty }: Props) {
  if (empty || !eda) {
    return (
      <div
        className="flex items-center gap-[14px] p-6 rounded-lg"
        style={{
          border: "1px dashed var(--rib-line2)",
          background: "var(--rib-bg1)",
          color: "var(--rib-text2)",
          fontSize: 13.5,
        }}
      >
        <div
          className="grid place-items-center"
          style={{
            width: 28,
            height: 28,
            borderRadius: 4,
            border: "1px solid var(--rib-line2)",
            color: "var(--rib-text3)",
          }}
        >
          ∅
        </div>
        <div>
          <div
            className="font-medium"
            style={{ color: "var(--rib-text1)", fontSize: 14 }}
          >
            No data audit performed
          </div>
          <div
            style={{ color: "var(--rib-text2)", marginTop: 2 }}
          >
            Data source was not provided for this audit run.
          </div>
        </div>
      </div>
    );
  }

  const classes = eda.class_distribution ?? {};
  const classKeys = Object.keys(classes);
  const allClasses = Array.from(
    new Set(classKeys.flatMap((s) => Object.keys(classes[s] ?? {}))),
  );
  const splitsTotal = Object.values(eda.splits_observed ?? {}).reduce(
    (a, b) => a + b,
    0,
  );

  return (
    <div className="grid gap-4" style={{ gridTemplateColumns: "1fr 1fr" }}>
      <Panel title="Splits observed" mono>
        {Object.entries(eda.splits_observed ?? {}).map(([k, v]) => (
          <PanelRow key={k} label={k} value={v.toLocaleString()} />
        ))}
        <PanelRow label="total" value={splitsTotal.toLocaleString()} accent />
        {eda.sample_dimensions_summary && (
          <div
            className="mt-3 pt-3"
            style={{
              borderTop: "1px solid var(--rib-line)",
              color: "var(--rib-text2)",
              fontSize: 12.5,
              lineHeight: "18px",
            }}
          >
            {eda.sample_dimensions_summary}
          </div>
        )}
      </Panel>

      {classKeys.length > 0 && (
        <Panel title="Class distribution">
          {classKeys.map((split) => {
            const dist = classes[split] ?? {};
            const total = Object.values(dist).reduce((a, b) => a + b, 0);
            return (
              <div key={split} style={{ marginBottom: 10 }}>
                <div
                  className="flex justify-between mb-1"
                  style={{ fontSize: 12, color: "var(--rib-text2)" }}
                >
                  <span>{split}</span>
                  <span
                    className="font-mono"
                    style={{ color: "var(--rib-text3)" }}
                  >
                    {total}
                  </span>
                </div>
                <div
                  className="flex overflow-hidden"
                  style={{
                    height: 8,
                    borderRadius: 2,
                    background: "var(--rib-bg3)",
                  }}
                >
                  {allClasses.map((c, i) => {
                    const n = dist[c] ?? 0;
                    const pct = total > 0 ? (n / total) * 100 : 0;
                    const colors = [
                      "var(--rib-agent-auditor)",
                      "var(--rib-agent-paper)",
                      "var(--rib-agent-validator)",
                      "var(--rib-agent-reviewer)",
                    ];
                    return (
                      <div
                        key={c}
                        style={{
                          width: `${pct}%`,
                          background: colors[i % colors.length],
                          opacity: 0.75,
                        }}
                        title={`${c}: ${n}`}
                      />
                    );
                  })}
                </div>
                <div
                  className="flex gap-3 mt-[5px] font-mono"
                  style={{ fontSize: 11.5, color: "var(--rib-text2)" }}
                >
                  {allClasses.map((c, i) => {
                    const colors = [
                      "var(--rib-agent-auditor)",
                      "var(--rib-agent-paper)",
                      "var(--rib-agent-validator)",
                      "var(--rib-agent-reviewer)",
                    ];
                    return (
                      <span
                        key={c}
                        className="inline-flex items-center gap-[5px]"
                      >
                        <span
                          style={{
                            width: 6,
                            height: 6,
                            borderRadius: 1,
                            background: colors[i % colors.length],
                            opacity: 0.75,
                          }}
                        />
                        {c} {dist[c] ?? 0}
                      </span>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </Panel>
      )}

      {eda.file_format_stats && Object.keys(eda.file_format_stats).length > 0 && (
        <Panel title="File formats" mono>
          {Object.entries(eda.file_format_stats).map(([k, v]) => (
            <PanelRow key={k} label={k} value={v.toLocaleString()} />
          ))}
        </Panel>
      )}

      <Panel
        title={`Corrupt files · ${(eda.corrupt_files ?? []).length}`}
        toneLevel="critical"
        mono
      >
        {(eda.corrupt_files?.length ?? 0) === 0 ? (
          <div style={{ color: "var(--rib-text3)", fontSize: 12.5 }}>
            None detected.
          </div>
        ) : (
          <ul className="flex flex-col gap-1 m-0 p-0 list-none">
            {eda.corrupt_files!.map((f) => (
              <li
                key={f}
                className="font-mono flex items-center gap-2"
                style={{ fontSize: 12, color: "var(--rib-text1)" }}
              >
                <span style={{ color: "var(--rib-critical)" }}>✕</span>
                {f}
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </div>
  );
}

function Panel({
  title,
  children,
  mono,
  toneLevel,
}: {
  title: string;
  children: ReactNode;
  mono?: boolean;
  toneLevel?: Severity;
}) {
  const tone = toneLevel ? SEVERITY_META[toneLevel] : null;
  return (
    <div
      style={{
        background: "var(--rib-bg1)",
        border: "1px solid var(--rib-line)",
        borderRadius: 8,
        padding: "14px 18px 16px",
      }}
    >
      <div className="flex items-center gap-2 mb-[10px]">
        {tone && (
          <span
            style={{
              width: 6,
              height: 6,
              borderRadius: 1,
              background: tone.fg,
            }}
          />
        )}
        <div
          className="font-semibold uppercase"
          style={{
            fontSize: 11,
            letterSpacing: "0.14em",
            color: tone ? tone.fg : "var(--rib-text2)",
          }}
        >
          {title}
        </div>
      </div>
      <div className={mono ? "font-mono" : "font-ui"}>{children}</div>
    </div>
  );
}

function PanelRow({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent?: boolean;
}) {
  return (
    <div
      className="grid items-center"
      style={{
        gridTemplateColumns: "1fr auto",
        padding: "3px 0",
        fontSize: 12.5,
        color: accent ? "var(--rib-text0)" : "var(--rib-text1)",
        fontWeight: accent ? 600 : 400,
        borderTop: accent ? "1px solid var(--rib-line)" : "none",
        paddingTop: accent ? 8 : 3,
        marginTop: accent ? 4 : 0,
      }}
    >
      <span>{label}</span>
      <span className="tabular-nums">{value}</span>
    </div>
  );
}
