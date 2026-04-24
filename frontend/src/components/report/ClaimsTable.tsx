import type { ClaimVerification } from "../../types/schemas";
import { ClaimStatusBadge } from "../atoms";

interface Props {
  claims: ClaimVerification[];
}

export function ClaimsTable({ claims }: Props) {
  if (claims.length === 0) {
    return (
      <div
        className="p-6 rounded-lg text-center"
        style={{
          border: "1px dashed var(--rib-line2)",
          background: "var(--rib-bg1)",
          color: "var(--rib-text2)",
        }}
      >
        No paper claims were extracted for this audit.
      </div>
    );
  }
  return (
    <div
      className="overflow-hidden"
      style={{
        border: "1px solid var(--rib-line)",
        borderRadius: 8,
        background: "var(--rib-bg1)",
      }}
    >
      <div
        className="grid gap-5 px-4 py-[10px] font-semibold uppercase"
        style={{
          gridTemplateColumns: "minmax(0, 2.4fr) minmax(0, 1.2fr) 140px 80px",
          background: "var(--rib-bg2)",
          borderBottom: "1px solid var(--rib-line)",
          fontSize: 11,
          letterSpacing: "0.12em",
          color: "var(--rib-text2)",
        }}
      >
        <div>Claim</div>
        <div>Code location</div>
        <div>Status</div>
        <div className="text-right">Findings</div>
      </div>
      {claims.map((c, i) => (
        <div
          key={c.claim_id}
          className="grid gap-5 items-start"
          style={{
            gridTemplateColumns: "minmax(0, 2.4fr) minmax(0, 1.2fr) 140px 80px",
            padding: "14px 16px",
            borderTop: i === 0 ? "none" : "1px solid var(--rib-line)",
          }}
        >
          <div className="min-w-0">
            <div
              className="text-pretty"
              style={{
                color: "var(--rib-text0)",
                fontSize: 13.5,
                lineHeight: "20px",
                marginBottom: c.notes ? 4 : 0,
              }}
            >
              {c.claim_summary || c.claim_id}
            </div>
            {c.notes && (
              <div
                className="text-pretty"
                style={{
                  color: "var(--rib-text2)",
                  fontSize: 12.5,
                  lineHeight: "18px",
                }}
              >
                {c.notes}
              </div>
            )}
          </div>
          <div
            className="font-mono"
            style={{
              fontSize: 12,
              color: "var(--rib-mono)",
              lineHeight: "20px",
              wordBreak: "break-all",
            }}
          >
            {c.code_location || "—"}
          </div>
          <div>
            <ClaimStatusBadge status={c.status} />
          </div>
          <div
            className="text-right font-mono tabular-nums"
            style={{
              fontSize: 12.5,
              color: (c.linked_finding_ids?.length ?? 0)
                ? "var(--rib-text0)"
                : "var(--rib-text3)",
            }}
          >
            {c.linked_finding_ids?.length || "—"}
          </div>
        </div>
      ))}
    </div>
  );
}
