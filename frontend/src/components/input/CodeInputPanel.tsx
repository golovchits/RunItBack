import { useState } from "react";
import type { CodeSource } from "../../types/schemas";
import { InputField } from "./InputField";
import { SectionCard } from "./SectionCard";

interface Props {
  value: CodeSource;
  onChange: (value: CodeSource) => void;
}

export function CodeInputPanel({ value, onChange }: Props) {
  const [gitUrl, setGitUrl] = useState(value.kind === "git" ? value.url : "");
  const [gitRef, setGitRef] = useState(
    value.kind === "git" ? value.ref ?? "" : "",
  );

  return (
    <SectionCard
      eyebrow="Code"
      title="Repository"
      subtitle="The codebase to audit. Must be a public GitHub repo — managed agents clone it into their sandbox."
      accent="auditor"
    >
      <div className="space-y-3">
        <InputField
          label="Repository URL"
          placeholder="https://github.com/org/repo"
          value={gitUrl}
          mono
          onChange={(e) => {
            setGitUrl(e.target.value);
            onChange({
              kind: "git",
              url: e.target.value,
              ref: gitRef || null,
            });
          }}
          hint="HTTPS URL to a public GitHub repo."
        />
        <InputField
          label="Ref (branch, tag, or commit — optional)"
          placeholder="main"
          value={gitRef}
          mono
          onChange={(e) => {
            setGitRef(e.target.value);
            onChange({
              kind: "git",
              url: gitUrl,
              ref: e.target.value || null,
            });
          }}
        />
      </div>
    </SectionCard>
  );
}
