import type { AgentName, Severity, Verdict } from "../types/schemas";
// re-exported for callers that only need the enum literal.
export type { AgentName } from "../types/schemas";

export const AGENT_META: Record<
  AgentName | "paper" | "auditor",
  { label: string; fg: string; bg: string; short: string }
> = {
  paper_analyst: {
    label: "Paper Analyst",
    fg: "var(--rib-agent-paper)",
    bg: "rgba(217,128,64,0.12)",
    short: "paper",
  },
  code_auditor: {
    label: "Code & Data Auditor",
    fg: "var(--rib-agent-auditor)",
    bg: "rgba(90,140,217,0.12)",
    short: "auditor",
  },
  validator: {
    label: "Validator",
    fg: "var(--rib-agent-validator)",
    bg: "rgba(79,165,121,0.12)",
    short: "validator",
  },
  reviewer: {
    label: "Reviewer",
    fg: "var(--rib-agent-reviewer)",
    bg: "rgba(154,127,209,0.12)",
    short: "reviewer",
  },
  // Aliases for detector role strings
  paper: {
    label: "Paper Analyst",
    fg: "var(--rib-agent-paper)",
    bg: "rgba(217,128,64,0.12)",
    short: "paper",
  },
  auditor: {
    label: "Auditor",
    fg: "var(--rib-agent-auditor)",
    bg: "rgba(90,140,217,0.12)",
    short: "auditor",
  },
};

export const SEVERITY_META: Record<
  Severity,
  { label: string; fg: string; bg: string; line: string }
> = {
  critical: {
    label: "Critical",
    fg: "var(--rib-critical)",
    bg: "rgba(229,83,83,0.10)",
    line: "rgba(229,83,83,0.35)",
  },
  high: {
    label: "High",
    fg: "var(--rib-high)",
    bg: "rgba(224,131,64,0.10)",
    line: "rgba(224,131,64,0.35)",
  },
  medium: {
    label: "Medium",
    fg: "var(--rib-medium)",
    bg: "rgba(214,165,74,0.10)",
    line: "rgba(214,165,74,0.35)",
  },
  low: {
    label: "Low",
    fg: "var(--rib-low)",
    bg: "rgba(155,163,74,0.10)",
    line: "rgba(155,163,74,0.35)",
  },
  info: {
    label: "Info",
    fg: "var(--rib-info)",
    bg: "rgba(124,133,147,0.10)",
    line: "rgba(124,133,147,0.30)",
  },
};

export const VERDICT_META: Record<
  Verdict,
  { label: string; short: string; fg: string }
> = {
  reproducible: {
    label: "Reproducible",
    short: "REPRODUCIBLE",
    fg: "var(--rib-reproducible)",
  },
  likely_reproducible: {
    label: "Likely reproducible",
    short: "LIKELY REPRO.",
    fg: "var(--rib-likely)",
  },
  questionable: {
    label: "Questionable",
    short: "QUESTIONABLE",
    fg: "var(--rib-questionable)",
  },
  not_reproducible: {
    label: "Not reproducible",
    short: "NOT REPRO.",
    fg: "var(--rib-notrep)",
  },
  inconclusive: {
    label: "Inconclusive",
    short: "INCONCLUSIVE",
    fg: "var(--rib-inconclusive)",
  },
};

export const CLAIM_META = {
  verified: { label: "Verified", fg: "var(--rib-reproducible)" },
  partial: { label: "Partial", fg: "var(--rib-questionable)" },
  not_verified: { label: "Not verified", fg: "var(--rib-notrep)" },
  unchecked: { label: "Unchecked", fg: "var(--rib-text2)" },
};

export const VALIDATION_META = {
  confirmed: { label: "Confirmed", fg: "var(--rib-reproducible)", fill: true },
  denied: { label: "Denied", fg: "var(--rib-notrep)", fill: true },
  inconclusive: {
    label: "Inconclusive",
    fg: "var(--rib-questionable)",
    fill: false,
  },
  unvalidated: {
    label: "Unvalidated",
    fg: "var(--rib-text2)",
    fill: false,
  },
};

/** Maps DetectorRole → AgentName for styling. */
export function detectorToAgent(role: string): AgentName {
  if (role === "validator") return "validator";
  if (role === "reviewer") return "reviewer";
  // "auditor" is used by the backend for both paper and code detectors;
  // code auditor is the more common rendering context.
  return "code_auditor";
}
