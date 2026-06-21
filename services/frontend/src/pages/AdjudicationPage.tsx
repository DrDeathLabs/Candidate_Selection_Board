import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { listAdjudicationActions, listCases } from "../lib/api";
import { useResolvedCaseId } from "../lib/cases";
import { formatLabel } from "../lib/format";

export function AdjudicationPage() {
  const casesQuery = useQuery({ queryKey: ["cases"], queryFn: listCases });
  const { caseId, selectCase } = useResolvedCaseId(casesQuery.data);
  const [search, setSearch] = useState("");

  const actionsQuery = useQuery({
    queryKey: ["adjudication-actions", caseId],
    queryFn: () => listAdjudicationActions(caseId!),
    enabled: Boolean(caseId),
  });

  const actions = (actionsQuery.data ?? []).filter(a =>
    !search || a.action_type.toLowerCase().includes(search.toLowerCase()) || a.rationale.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="workspace">
      <div className="panel panel-flex" style={{ overflow: "hidden", display: "flex", flexDirection: "column" }}>
        <div className="panel-head">
          <span className="panel-head-title">Adjudication Log</span>
          <select className="select-input" style={{ height: 26, maxWidth: 240 }} value={caseId ?? ""} onChange={e => selectCase(e.target.value || null)}>
            <option value="">— Select engagement —</option>
            {(casesQuery.data ?? []).map(c => <option key={c.id} value={c.id}>{c.title}</option>)}
          </select>
          <input className="input" style={{ height: 26, width: 180 }} placeholder="Search…" value={search} onChange={e => setSearch(e.target.value)} />
          <span className="text-muted text-sm">{actions.length} actions</span>
        </div>
        <div style={{ overflowY: "auto", flex: 1 }}>
          <table className="tbl">
            <thead>
              <tr>
                <th>Time</th>
                <th>Action</th>
                <th>Actor</th>
                <th>Rationale</th>
              </tr>
            </thead>
            <tbody>
              {!caseId && <tr className="empty-row"><td colSpan={4}>Select an engagement</td></tr>}
              {caseId && actions.length === 0 && (
                <tr className="empty-row"><td colSpan={4}>{actionsQuery.isLoading ? "Loading…" : "No adjudication actions"}</td></tr>
              )}
              {actions.map(a => (
                <tr key={a.id}>
                  <td style={{ color: "var(--text-muted)", whiteSpace: "nowrap" }}>{new Date(a.created_at).toLocaleString()}</td>
                  <td style={{ fontWeight: 600 }}>{formatLabel(a.action_type)}</td>
                  <td style={{ color: "var(--text-muted)" }}>{a.actor_id || "system"}</td>
                  <td style={{ color: "var(--text-muted)", maxWidth: 360 }}>{a.rationale}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
