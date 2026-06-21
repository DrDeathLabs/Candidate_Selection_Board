import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import {
  listCandidatesForCase,
  listCases,
} from "../lib/api";
import { useResolvedCaseId } from "../lib/cases";
import { formatLabel } from "../lib/format";

export function CandidateProfilePage() {
  const casesQuery = useQuery({ queryKey: ["cases"], queryFn: listCases });
  const { caseId, selectCase } = useResolvedCaseId(casesQuery.data);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const candidatesQuery = useQuery({
    queryKey: ["candidates", caseId],
    queryFn: () => listCandidatesForCase(caseId!),
    enabled: Boolean(caseId),
  });

  const candidates = candidatesQuery.data ?? [];
  const selected = candidates.find(c => c.id === selectedId) ?? null;

  return (
    <div className="workspace">
      <div className="panel panel-260">
        <div className="panel-head">
          <span className="panel-head-title">Candidates</span>
          <span className="text-muted text-sm">{candidates.length}</span>
        </div>
        <div style={{ padding: "6px 12px", borderBottom: "1px solid var(--border)" }}>
          <select className="select-input" style={{ height: 26, width: "100%" }} value={caseId ?? ""} onChange={e => selectCase(e.target.value || null)}>
            <option value="">— Select engagement —</option>
            {(casesQuery.data ?? []).map(c => <option key={c.id} value={c.id}>{c.title}</option>)}
          </select>
        </div>
        <div style={{ overflowY: "auto", flex: 1 }}>
          {candidates.map(c => (
            <div
              key={c.id}
              className={`stage-item ${selectedId === c.id ? "active" : ""}`}
              onClick={() => setSelectedId(c.id)}
            >
              <div className="stage-item-body">
                <div className="stage-name">{c.full_name}</div>
                <div className="stage-meta">{c.email ?? "—"}</div>
              </div>
              <span className={`chip ${c.disposition === "qualified" || c.disposition === "best_qualified" ? "chip-success" : "chip-neutral"}`} style={{ fontSize: 9 }}>
                {formatLabel(c.disposition)}
              </span>
            </div>
          ))}
          {candidates.length === 0 && (
            <p className="loading-text">{!caseId ? "Select engagement" : candidatesQuery.isLoading ? "Loading…" : "No candidates"}</p>
          )}
        </div>
      </div>

      <div className="panel panel-flex" style={{ overflowY: "auto" }}>
        {!selected ? (
          <div style={{ padding: "32px 16px", textAlign: "center", color: "var(--text-muted)", fontSize: 12 }}>
            Select a candidate to view their profile
          </div>
        ) : (
          <>
            <div className="panel-head">
              <span className="panel-head-title">{selected.full_name}</span>
            </div>
            <div style={{ padding: "12px 16px" }}>
              <table className="mini-table" style={{ marginBottom: 16 }}>
                <tbody>
                  <tr><td className="mini-key">Full Name</td><td>{selected.full_name}</td></tr>
                  <tr><td className="mini-key">Email</td><td>{selected.email ?? "—"}</td></tr>
                  <tr><td className="mini-key">Certificate</td><td>{selected.certificate_identifier ?? "—"}</td></tr>
                  <tr><td className="mini-key">Disposition</td><td>{formatLabel(selected.disposition)}</td></tr>
                  <tr><td className="mini-key">Created</td><td>{new Date(selected.created_at).toLocaleString()}</td></tr>
                </tbody>
              </table>

              {Object.keys(selected.profile).length > 0 && (
                <div className="settings-section">
                  <div className="settings-section-head">Profile Data</div>
                  {Object.entries(selected.profile).map(([k, v]) => (
                    <div key={k} className="settings-row">
                      <span className="settings-key">{formatLabel(k)}</span>
                      <span className="settings-val" style={{ color: "var(--text-muted)" }}>{String(v)}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
