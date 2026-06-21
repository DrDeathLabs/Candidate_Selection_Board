import type { CaseSummary } from "../lib/api";

type CaseSelectorProps = {
  cases: CaseSummary[];
  value: string | null;
  onChange: (caseId: string | null) => void;
  label?: string;
};

export function CaseSelector({ cases, value, onChange, label = "Active engagement" }: CaseSelectorProps) {
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      <select className="input" value={value ?? ""} onChange={(event) => onChange(event.target.value)}>
        <option value="">{cases.length === 0 ? "No engagements yet" : "Select an engagement"}</option>
        {cases.map((entry) => (
          <option key={entry.id} value={entry.id}>
            {entry.title} ({entry.status})
          </option>
        ))}
      </select>
    </label>
  );
}
