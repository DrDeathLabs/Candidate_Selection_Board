import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  getCandidateReconciliationSummary,
  listCandidateMatches,
  listCases,
  listResumeSegments,
  runCandidateReconciliation,
  updateCandidateMatch,
} from "../lib/api";
import { useResolvedCaseId } from "../lib/cases";

export function CandidateReconciliationPage() {
  const qc = useQueryClient();
  const casesQuery = useQuery({ queryKey: ["cases"], queryFn: listCases });
  const { caseId, selectCase } = useResolvedCaseId(casesQuery.data);
  const [editingId, setEditingId] = useState<string | null>(null);

  const summaryQuery = useQuery({
    queryKey: ["reconciliation-summary", caseId],
    queryFn: () => getCandidateReconciliationSummary(caseId!),
    enabled: Boolean(caseId),
  });

  const matchesQuery = useQuery({
    queryKey: ["candidate-matches", caseId],
    queryFn: () => listCandidateMatches(caseId!),
    enabled: Boolean(caseId),
  });

  const segmentsQuery = useQuery({
    queryKey: ["resume-segments", caseId],
    queryFn: () => listResumeSegments(caseId!),
    enabled: Boolean(caseId),
  });

  const reconcileMut = useMutation({
    mutationFn: () => runCandidateReconciliation(caseId!),
    onSuccess() { qc.invalidateQueries({ queryKey: ["reconciliation-summary", caseId] }); qc.invalidateQueries({ queryKey: ["candidate-matches", caseId] }); },
  });

  const updateMatchMut = useMutation({
    mutationFn: ({ candidateId, segmentId }: { candidateId: string; segmentId: string | null }) =>
      updateCandidateMatch(caseId!, candidateId, { resume_segment_id: segmentId }),
    onSuccess() { qc.invalidateQueries({ queryKey: ["candidate-matches", caseId] }); setEditingId(null); },
  });

  const summary = summaryQuery.data;
  const matches = matchesQuery.data ?? [];
  const segments = segmentsQuery.data ?? [];

  return (
    <div className="workspace">
      <div className="panel panel-220">
        <div className="panel-head">
          <span className="panel-head-title">Summary</span>
        </div>
        {summary ? (
          <div className="checklist">
            {[
              ["Candidates", summary.candidate_count],
              ["Matched", summary.matched_count],
              ["Unmatched", summary.unmatched_count],
              ["Duplicates", summary.duplicate_count],
              ["Resume Segments", summary.resume_segment_count],
              ["Unmatched Segments", summary.unmatched_segment_count],
            ].map(([label, val]) => (
              <div key={String(label)} className={`checklist-item ${Number(val) > 0 && (String(label).includes("Unmatched") || String(label).includes("Duplicate")) ? "warn" : "ok"}`}>
                <span style={{ fontWeight: 600, minWidth: 32, textAlign: "right" }}>{val}</span>
                <span>{label}</span>
              </div>
            ))}
          </div>
        ) : (
          <p className="loading-text">{!caseId ? "Select engagement" : summaryQuery.isLoading ? "Loading…" : "—"}</p>
        )}
        {caseId && (
          <div style={{ padding: "8px 12px", borderTop: "1px solid var(--border)" }}>
            <button className="btn btn-primary btn-sm" style={{ width: "100%" }} disabled={reconcileMut.isPending} onClick={() => reconcileMut.mutate()}>
              {reconcileMut.isPending ? "Running…" : "Run Reconciliation"}
            </button>
          </div>
        )}
      </div>

      <div className="panel panel-flex" style={{ overflow: "hidden", display: "flex", flexDirection: "column" }}>
        <div className="panel-head">
          <span className="panel-head-title">Candidate Matches</span>
          <select className="select-input" style={{ height: 26, maxWidth: 240 }} value={caseId ?? ""} onChange={e => selectCase(e.target.value || null)}>
            <option value="">— Select engagement —</option>
            {(casesQuery.data ?? []).map(c => <option key={c.id} value={c.id}>{c.title}</option>)}
          </select>
          <span className="text-muted text-sm">{matches.length} candidates</span>
        </div>
        <div style={{ overflowY: "auto", flex: 1 }}>
          <table className="tbl">
            <thead>
              <tr>
                <th>Candidate</th>
                <th>Email</th>
                <th>Matched Name</th>
                <th>Confidence</th>
                <th>Duplicate</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {!caseId && <tr className="empty-row"><td colSpan={6}>Select an engagement</td></tr>}
              {caseId && matches.length === 0 && (
                <tr className="empty-row"><td colSpan={6}>{matchesQuery.isLoading ? "Loading…" : "No candidates — run reconciliation first"}</td></tr>
              )}
              {matches.map(m => (
                <tr key={m.id} className={m.is_duplicate ? "row-overridden" : ""}>
                  <td style={{ fontWeight: 600 }}>{m.candidate_name}</td>
                  <td style={{ color: "var(--text-muted)" }}>{m.candidate_email ?? "—"}</td>
                  <td style={{ color: "var(--text-muted)" }}>{m.matched_name ?? m.inferred_name ?? "—"}</td>
                  <td>
                    <span className={`chip ${Number(m.confidence) > 0.8 ? "chip-success" : Number(m.confidence) > 0.5 ? "chip-warning" : "chip-danger"}`}>
                      {m.confidence}
                    </span>
                  </td>
                  <td style={{ textAlign: "center" }}>{m.is_duplicate ? <span className="chip chip-danger">Dup</span> : "—"}</td>
                  <td>
                    {editingId === m.id ? (
                      <select
                        className="select-input"
                        style={{ height: 24, fontSize: 11, width: 160 }}
                        defaultValue={m.resume_segment_id ?? ""}
                        onChange={e => updateMatchMut.mutate({ candidateId: m.candidate_id, segmentId: e.target.value || null })}
                      >
                        <option value="">— No segment —</option>
                        {segments.map(s => <option key={s.id} value={s.id}>{s.inferred_name ?? s.id.slice(0, 12)} (p.{s.start_page}–{s.end_page})</option>)}
                      </select>
                    ) : (
                      <button className="btn btn-ghost btn-sm" onClick={() => setEditingId(m.id)}>Reassign</button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
