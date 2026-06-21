import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { generateSelectionRecommendation, getSelectionRecommendation, listCases } from "../lib/api";
import { useResolvedCaseId } from "../lib/cases";
import { formatLabel } from "../lib/format";

export function SelectionRecommendationPage() {
  const qc = useQueryClient();
  const casesQuery = useQuery({ queryKey: ["cases"], queryFn: listCases });
  const { caseId, selectCase } = useResolvedCaseId(casesQuery.data);

  const recQuery = useQuery({
    queryKey: ["recommendation", caseId],
    queryFn: () => getSelectionRecommendation(caseId!),
    enabled: Boolean(caseId),
    retry: false,
  });

  const generateMut = useMutation({
    mutationFn: () => generateSelectionRecommendation(caseId!),
    onSuccess() { qc.invalidateQueries({ queryKey: ["recommendation", caseId] }); },
  });

  const rec = recQuery.data;

  return (
    <div className="workspace">
      <div className="panel panel-flex" style={{ overflow: "hidden", display: "flex", flexDirection: "column" }}>
        <div className="panel-head">
          <span className="panel-head-title">Selection Recommendation</span>
          <select className="select-input" style={{ height: 26, maxWidth: 240 }} value={caseId ?? ""} onChange={e => selectCase(e.target.value || null)}>
            <option value="">— Select engagement —</option>
            {(casesQuery.data ?? []).map(c => <option key={c.id} value={c.id}>{c.title}</option>)}
          </select>
          {caseId && (
            <button className="btn btn-primary btn-sm" disabled={generateMut.isPending} onClick={() => generateMut.mutate()}>
              {generateMut.isPending ? "Generating…" : rec ? "Regenerate" : "Generate Recommendation"}
            </button>
          )}
          {rec && <span className={`chip ${rec.status === "finalized" ? "chip-success" : "chip-warning"}`}>{formatLabel(rec.status)}</span>}
        </div>
        <div style={{ overflowY: "auto", flex: 1, padding: "0 16px 16px" }}>
          {!caseId && <p className="loading-text">Select an engagement</p>}
          {caseId && !rec && <p className="loading-text">{recQuery.isLoading ? "Loading…" : "No recommendation — generate one first"}</p>}

          {rec && (
            <>
              <div className="settings-section" style={{ paddingTop: 12 }}>
                <div className="settings-section-head">Selectee</div>
                <p style={{ fontSize: 15, fontWeight: 700, padding: "8px 0", color: "var(--text)" }}>{rec.selectee_candidate_name ?? "—"}</p>
              </div>

              {rec.alternate_candidate_names.length > 0 && (
                <div className="settings-section">
                  <div className="settings-section-head">Alternates</div>
                  {rec.alternate_candidate_names.map((n, i) => (
                    <div key={i} className="settings-row">
                      <span className="settings-key">#{i + 1}</span>
                      <span className="settings-val">{n}</span>
                    </div>
                  ))}
                </div>
              )}

              {rec.interview_slate_candidate_names.length > 0 && (
                <div className="settings-section">
                  <div className="settings-section-head">Interview / Narrative Slate</div>
                  {rec.interview_slate_candidate_names.map((n, i) => (
                    <div key={i} className="settings-row">
                      <span className="settings-key">#{i + 1}</span>
                      <span className="settings-val">{n}</span>
                    </div>
                  ))}
                </div>
              )}

              {rec.rationale && (
                <div className="settings-section">
                  <div className="settings-section-head">Rationale</div>
                  <p className="dossier-narrative" style={{ paddingTop: 8 }}>{rec.rationale}</p>
                </div>
              )}

              {rec.remaining_validation_issues.length > 0 && (
                <div className="settings-section">
                  <div className="settings-section-head">Validation Issues</div>
                  {rec.remaining_validation_issues.map((iss, i) => (
                    <div key={i} className="issue-row">
                      <span className="status-dot amber" />
                      <span>{iss}</span>
                    </div>
                  ))}
                </div>
              )}

              <div className="settings-section">
                <div className="settings-section-head">Full Rankings ({rec.rankings.length})</div>
                <table className="rubric-tbl">
                  <thead>
                    <tr>
                      <th>Candidate</th>
                      <th>Disposition</th>
                      <th>Score</th>
                      <th>Confidence</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rec.rankings.map((r, i) => (
                      <tr key={i}>
                        <td style={{ fontWeight: rec.selectee_candidate_id === r.candidate_id ? 700 : 400 }}>
                          {r.candidate_name}
                          {rec.selectee_candidate_id === r.candidate_id && <span className="chip chip-tier-a" style={{ marginLeft: 6 }}>Selectee</span>}
                        </td>
                        <td style={{ color: "var(--text-muted)" }}>{formatLabel(r.disposition)}</td>
                        <td style={{ fontWeight: 600 }}>{r.score}</td>
                        <td style={{ color: "var(--text-muted)" }}>{r.confidence}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
