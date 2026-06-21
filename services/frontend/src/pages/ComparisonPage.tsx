import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { listCandidatesForCase, listCases, listPairwiseComparisons } from "../lib/api";
import { useResolvedCaseId } from "../lib/cases";

export function ComparisonPage() {
  const casesQuery = useQuery({ queryKey: ["cases"], queryFn: listCases });
  const { caseId, selectCase } = useResolvedCaseId(casesQuery.data);
  const [leftId, setLeftId] = useState("");
  const [rightId, setRightId] = useState("");

  const candidatesQuery = useQuery({
    queryKey: ["candidates", caseId],
    queryFn: () => listCandidatesForCase(caseId!),
    enabled: Boolean(caseId),
  });

  const comparisonsQuery = useQuery({
    queryKey: ["comparisons", caseId],
    queryFn: () => listPairwiseComparisons(caseId!),
    enabled: Boolean(caseId),
  });

  const leftCandidate = (candidatesQuery.data ?? []).find(c => c.id === leftId) ?? null;
  const rightCandidate = (candidatesQuery.data ?? []).find(c => c.id === rightId) ?? null;

  const comparison = (comparisonsQuery.data ?? []).find(c =>
    (c.left_candidate_id === leftId && c.right_candidate_id === rightId) ||
    (c.right_candidate_id === leftId && c.left_candidate_id === rightId)
  ) ?? null;

  return (
    <div className="workspace">
      <div className="panel panel-flex" style={{ overflow: "hidden", display: "flex", flexDirection: "column" }}>
        <div className="panel-head">
          <span className="panel-head-title">Pairwise Comparison</span>
          <select className="select-input" style={{ height: 26, maxWidth: 240 }} value={caseId ?? ""} onChange={e => selectCase(e.target.value || null)}>
            <option value="">— Select engagement —</option>
            {(casesQuery.data ?? []).map(c => <option key={c.id} value={c.id}>{c.title}</option>)}
          </select>
        </div>

        <div className="action-row action-row-border">
          <select className="select-input" style={{ maxWidth: 240 }} value={leftId} onChange={e => setLeftId(e.target.value)}>
            <option value="">— Left candidate —</option>
            {(candidatesQuery.data ?? []).map(c => <option key={c.id} value={c.id}>{c.full_name}</option>)}
          </select>
          <span style={{ color: "var(--text-dim)" }}>vs</span>
          <select className="select-input" style={{ maxWidth: 240 }} value={rightId} onChange={e => setRightId(e.target.value)}>
            <option value="">— Right candidate —</option>
            {(candidatesQuery.data ?? []).map(c => <option key={c.id} value={c.id}>{c.full_name}</option>)}
          </select>
        </div>

        <div style={{ overflowY: "auto", flex: 1, padding: "12px 16px" }}>
          {!leftId || !rightId ? (
            <p className="loading-text">Select two candidates to compare</p>
          ) : !comparison ? (
            <p className="loading-text">No comparison record found for these two candidates</p>
          ) : (
            <>
              <div className="settings-section">
                <div className="settings-section-head">
                  Result
                  {comparison.winner_candidate_name && (
                    <span style={{ marginLeft: 8, fontWeight: 400, color: "var(--success-text)" }}>
                      Winner: {comparison.winner_candidate_name}
                    </span>
                  )}
                  <span style={{ marginLeft: 8, fontWeight: 400, color: "var(--text-dim)" }}>
                    Confidence: {comparison.confidence}
                  </span>
                </div>
                {comparison.rationale && (
                  <p className="dossier-narrative">{comparison.rationale}</p>
                )}
              </div>

              {comparison.dimension_results.length > 0 && (
                <div className="settings-section">
                  <div className="settings-section-head">Dimension Results</div>
                  <table className="rubric-tbl">
                    <thead>
                      <tr>
                        <th>Dimension</th>
                        <th style={{ textAlign: "center" }}>{comparison.left_candidate_name}</th>
                        <th style={{ textAlign: "center" }}>{comparison.right_candidate_name}</th>
                        <th style={{ textAlign: "center" }}>Leader</th>
                      </tr>
                    </thead>
                    <tbody>
                      {comparison.dimension_results.map((d, i) => (
                        <tr key={i}>
                          <td>{d.dimension_id}</td>
                          <td style={{ textAlign: "center", fontWeight: 600 }}>{d.left_score}</td>
                          <td style={{ textAlign: "center", fontWeight: 600 }}>{d.right_score}</td>
                          <td style={{ textAlign: "center", color: "var(--success-text)" }}>{d.leader === "left" ? comparison.left_candidate_name : d.leader === "right" ? comparison.right_candidate_name : "Tie"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          )}

          {(comparisonsQuery.data ?? []).length > 0 && (
            <div className="settings-section">
              <div className="settings-section-head">All Comparisons ({comparisonsQuery.data!.length})</div>
              <table className="rubric-tbl">
                <thead><tr><th>Left</th><th>Right</th><th>Winner</th><th>Confidence</th></tr></thead>
                <tbody>
                  {comparisonsQuery.data!.map(c => (
                    <tr key={c.id} className="clickable" onClick={() => { setLeftId(c.left_candidate_id); setRightId(c.right_candidate_id); }}>
                      <td>{c.left_candidate_name}</td>
                      <td>{c.right_candidate_name}</td>
                      <td style={{ color: "var(--success-text)" }}>{c.winner_candidate_name ?? "—"}</td>
                      <td style={{ color: "var(--text-muted)" }}>{c.confidence}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
