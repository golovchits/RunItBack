import type { Recommendation } from "../../types/schemas";
import { Markdown, Pill } from "../atoms";

interface Props {
  items: Recommendation[];
}

export function RecommendationsList({ items }: Props) {
  if (items.length === 0) {
    return (
      <div
        className="p-6 rounded-lg text-center"
        style={{
          border: "1px dashed var(--rib-line2)",
          background: "var(--rib-bg1)",
          color: "var(--rib-text2)",
        }}
      >
        No recommendations.
      </div>
    );
  }
  return (
    <ol className="m-0 p-0 list-none flex flex-col gap-[10px]">
      {items.map((r) => (
        <li
          key={r.rank}
          className="grid items-start gap-[14px]"
          style={{
            background: "var(--rib-bg1)",
            border: "1px solid var(--rib-line)",
            borderRadius: 8,
            padding: "14px 18px",
            gridTemplateColumns: "44px 1fr auto",
          }}
        >
          <div
            className="font-mono tabular-nums flex items-center"
            style={{
              fontSize: 22,
              fontWeight: 600,
              color: "var(--rib-text0)",
              letterSpacing: "-0.02em",
              borderRight: "1px solid var(--rib-line)",
              paddingRight: 14,
              alignSelf: "stretch",
            }}
          >
            {String(r.rank).padStart(2, "0")}
          </div>
          <div className="min-w-0">
            <div
              className="font-semibold mb-1 text-pretty"
              style={{
                fontSize: 14.5,
                color: "var(--rib-text0)",
                letterSpacing: "-0.005em",
              }}
            >
              <Markdown src={r.title} />
            </div>
            <div
              className="text-pretty"
              style={{
                fontSize: 13,
                lineHeight: "20px",
                color: "var(--rib-text1)",
              }}
            >
              {r.rationale}
            </div>
          </div>
          <div className="flex flex-col gap-[5px] items-end">
            {r.linked_finding_ids.map((id) => (
              <Pill key={id} mono>
                {id}
              </Pill>
            ))}
          </div>
        </li>
      ))}
    </ol>
  );
}
