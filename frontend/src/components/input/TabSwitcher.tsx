interface Tab<T extends string> {
  key: T;
  label: string;
  hint?: string;
}

interface Props<T extends string> {
  tabs: readonly Tab<T>[];
  value: T;
  onChange: (value: T) => void;
}

export function TabSwitcher<T extends string>({
  tabs,
  value,
  onChange,
}: Props<T>) {
  return (
    <div
      className="inline-flex items-center gap-[2px] p-[3px]"
      style={{
        background: "var(--rib-bg2)",
        border: "1px solid var(--rib-line)",
        borderRadius: 6,
      }}
    >
      {tabs.map((t) => {
        const active = value === t.key;
        return (
          <button
            key={t.key}
            type="button"
            onClick={() => onChange(t.key)}
            className="font-ui whitespace-nowrap"
            title={t.hint}
            style={{
              padding: "5px 12px",
              borderRadius: 4,
              fontSize: 12.5,
              fontWeight: active ? 600 : 500,
              color: active ? "var(--rib-text0)" : "var(--rib-text2)",
              background: active ? "var(--rib-bg4)" : "transparent",
              border: `1px solid ${active ? "var(--rib-line2)" : "transparent"}`,
              cursor: "pointer",
              transition: "all 0.15s",
            }}
          >
            {t.label}
          </button>
        );
      })}
    </div>
  );
}
