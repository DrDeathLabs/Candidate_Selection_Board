import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";

import {
  createAdjudicationAction,
  generateSelectionRecommendation,
  getDecisionWorkspace,
  requestExport,
  type AdjudicationActionPayload,
  type CandidateMatrixRow,
  type RankedCandidateRecord,
} from "../lib/api";
import { formatLabel } from "../lib/format";

function extractTierLetter(tier: string): string {
  const t = (tier ?? "").trim().toUpperCase();
  const m = t.match(/([A-D])$/);
  if (m) return m[1];
  if (t === "UNRANKED" || t.startsWith("UNRANKED")) return "UNRANKED";
  return "";
}

function tierChip(tier: string) {
  const t = extractTierLetter(tier);
  if (t === "A") return <span className="chip chip-tier-a">A</span>;
  if (t === "B") return <span className="chip chip-tier-b">B</span>;
  if (t === "C") return <span className="chip chip-neutral">C</span>;
  return <span className="chip chip-dim">{t || "—"}</span>;
}

function dispositionChip(d: string) {
  const s = (d ?? "").toLowerCase();
  if (s === "selected")     return <span className="chip chip-tier-a">Selected</span>;
  if (s === "best_qualified" || s === "referred") return <span className="chip chip-brand">{formatLabel(d)}</span>;
  if (s === "not_selected") return <span className="chip chip-neutral">Not Selected</span>;
  if (s === "not_qualified") return <span className="chip chip-danger">NQ</span>;
  return <span className="chip chip-neutral">{formatLabel(d)}</span>;
}

export function EngagementDecisionPage() {
  const { engagementId } = useParams<{ engagementId: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const qc = useQueryClient();

  const candidateParam = searchParams.get("candidate") ?? null;
  const [adjForm, setAdjForm] = useState({ action_type: "", rationale: "", notes: "" });
  const [genPending, setGenPending] = useState(false);

  const wsQuery = useQuery({
    queryKey: ["decision-workspace", engagementId, candidateParam],
    queryFn: () => getDecisionWorkspace(engagementId!, { candidate: candidateParam }),
    enabled: Boolean(engagementId),
    staleTime: 10_000,
  });

  const generateMut = useMutation({
    mutationFn: () => generateSelectionRecommendation(engagementId!),
    onSuccess() { qc.invalidateQueries({ queryKey: ["decision-workspace", engagementId] }); },
  });

  const adjMut = useMutation({
    mutationFn: (payload: AdjudicationActionPayload) => createAdjudicationAction(engagementId!, payload),
    onSuccess() { qc.invalidateQueries({ queryKey: ["decision-workspace", engagementId] }); setAdjForm({ action_type: "", rationale: "", notes: "" }); },
  });

  const exportMut = useMutation({
    mutationFn: (exportType: string) => requestExport(engagementId!, exportType),
    onSuccess() { qc.invalidateQueries({ queryKey: ["decision-workspace", engagementId] }); },
  });

  const ws = wsQuery.data;
  const rec = ws?.recommendation ?? null;
  const selectedRow = ws?.candidate_rows.find(r => r.candidate_id === candidateParam) ?? null;

  useEffect(() => {
    if (wsQuery.isSuccess && !ws?.recommendation && !generateMut.isPending && !genPending) {
      setGenPending(true);
      generateMut.mutate();
    }
  }, [wsQuery.isSuccess, ws?.recommendation, generateMut.isPending, genPending]);

  function selectCandidate(candidateId: string) {
    setSearchParams(prev => {
      const p = new URLSearchParams(prev);
      p.set("candidate", candidateId);
      return p;
    });
  }

  function adjAction(actionType: string, candidateId: string | null = candidateParam) {
    if (!adjForm.rationale.trim()) { alert("Rationale is required"); return; }
    adjMut.mutate({ action_type: actionType, rationale: adjForm.rationale, target_candidate_id: candidateId, payload: { notes: adjForm.notes } });
  }

  if (!engagementId) return <div className="error-state">No engagement selected.</div>;

  return (
    <div className="workspace">
      {/* Left: Slate summary */}
      <div className="panel panel-260" style={{ overflow: "hidden" }}>
        <div className="panel-head">
          <span className="panel-head-title">Decision Package</span>
          {rec && (
            <span className={`chip ${rec.status === "finalized" ? "chip-success" : "chip-warning"}`}>
              {formatLabel(rec.status)}
            </span>
          )}
        </div>

        <div style={{ overflowY: "auto", flex: 1 }}>
          {!rec ? (
            <div style={{ padding: "16px 12px" }}>
              <p className="loading-text">{generateMut.isPending ? "Building decision package…" : "Loading…"}</p>
            </div>
          ) : (
            <>
              {rec.status !== "finalized" && (
                <div style={{ margin: "8px 12px 0", padding: "8px 10px",
                  background: "color-mix(in srgb, var(--warning) 10%, transparent)",
                  border: "1px solid color-mix(in srgb, var(--warning) 30%, transparent)", borderRadius: 3 }}>
                  <div style={{ fontSize: 11, fontWeight: 700, color: "var(--warning-text)" }}>AI-suggested selection — pending your review</div>
                  <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 2 }}>Review the ranking, make any changes, then finalize your selection below.</div>
                </div>
              )}

              {rec.selectee_candidate_name && (
                <>
                  <div className="section-divider">{rec.status === "finalized" ? "Official Selectee" : "Suggested Selectee"}</div>
                  <div style={{ padding: "8px 14px", fontWeight: 700, fontSize: 15, color: "var(--success-text)" }}>
                    {rec.selectee_candidate_name}
                  </div>
                </>
              )}

              {rec.alternate_candidate_names.length > 0 && (
                <>
                  <div className="section-divider">Alternates</div>
                  {rec.alternate_candidate_names.map((n, i) => (
                    <div key={i} className="checklist-item ok">
                      <span style={{ color: "var(--text-muted)", minWidth: 16 }}>{i + 1}.</span>
                      <span>{n}</span>
                    </div>
                  ))}
                </>
              )}

              {rec.interview_slate_candidate_names.length > 0 && (
                <>
                  <div className="section-divider">Narrative Slate</div>
                  {rec.interview_slate_candidate_names.map((n, i) => (
                    <div key={i} className="checklist-item ok">
                      <span style={{ color: "var(--text-muted)", minWidth: 16 }}>{i + 1}.</span>
                      <span>{n}</span>
                    </div>
                  ))}
                </>
              )}

              {ws?.unresolved_issues && ws.unresolved_issues.length > 0 && (
                <>
                  <div className="section-divider">Package Issues</div>
                  {ws.unresolved_issues.map((iss, i) => (
                    <div key={i} className="issue-row">
                      <span className="status-dot amber" />
                      <span className="issue-label">{iss}</span>
                    </div>
                  ))}
                </>
              )}

              {rec.rationale && (
                <>
                  <div className="section-divider">Rationale</div>
                  <p className="dossier-narrative" style={{ padding: "6px 12px" }}>{rec.rationale}</p>
                </>
              )}
            </>
          )}
        </div>

        {/* Export + readiness strip */}
        <div style={{ borderTop: "1px solid var(--border)", padding: "10px 12px", display: "flex", flexDirection: "column", gap: 6, flexShrink: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span className={`status-dot ${ws?.export_ready ? "green" : "gray"}`} />
            <span style={{ color: ws?.export_ready ? "var(--text)" : "var(--text-dim)" }}>
              {ws?.export_ready ? "Ready to export" : "Not ready for export"}
            </span>
          </div>
          {rec?.selectee_candidate_id && rec.status !== "finalized" && (
            <button
              className="btn btn-sm btn-primary"
              style={{ width: "100%" }}
              disabled={adjMut.isPending}
              onClick={() => adjMut.mutate({ action_type: "lock_selectee", rationale: "Selection finalized by selecting official.", target_candidate_id: null, payload: {} })}
            >
              Finalize Selection
            </button>
          )}
          {rec?.status === "finalized" && (
            <p style={{ fontSize: 11, color: "var(--success-text)", textAlign: "center", margin: 0 }}>Selection finalized</p>
          )}
          <div style={{ display: "flex", gap: 6 }}>
            <button className="btn btn-sm" style={{ flex: 1 }} disabled={exportMut.isPending} onClick={() => exportMut.mutate("decision_package")}>
              {exportMut.isPending ? "Exporting…" : "Export package"}
            </button>
            <button className="btn btn-sm" disabled={generateMut.isPending} onClick={() => generateMut.mutate()} title="Rebuild package">
              ↺
            </button>
          </div>
          {exportMut.isSuccess && <p className="feedback-success">Export queued.</p>}
        </div>
      </div>

      {/* Center: Full ranked table */}
      <div className="panel panel-flex" style={{ overflow: "hidden", display: "flex", flexDirection: "column" }}>
        <div className="panel-head">
          <span className="panel-head-title">Candidate Rankings</span>
          <span className="text-muted text-sm">{(ws?.candidate_rows ?? []).length} candidates</span>
        </div>
        <div style={{ overflowY: "auto", flex: 1 }}>
          <table className="tbl">
            <thead>
              <tr>
                <th style={{ width: 36, textAlign: "center" }}>#</th>
                <th>Candidate</th>
                <th style={{ width: 60, textAlign: "center" }}>Tier</th>
                <th style={{ width: 80, textAlign: "center" }}>Score</th>
                <th>Disposition</th>
                <th style={{ width: 80, textAlign: "center" }}>Confidence</th>
                <th style={{ width: 80, textAlign: "center" }}>Decision</th>
              </tr>
            </thead>
            <tbody>
              {(ws?.candidate_rows ?? []).length === 0 && (
                <tr className="empty-row">
                  <td colSpan={7}>
                    {wsQuery.isLoading ? "Loading…" : "No candidates — generate a recommendation first"}
                  </td>
                </tr>
              )}
              {(ws?.candidate_rows ?? []).map((row, i) => {
                const isSelected = row.candidate_id === candidateParam;
                const ranked = rec?.rankings.find(r => r.candidate_id === row.candidate_id);
                return (
                  <tr
                    key={row.candidate_id}
                    className={`clickable ${isSelected ? "row-selected" : ""}`}
                    onClick={() => selectCandidate(row.candidate_id)}
                  >
                    <td style={{ textAlign: "center", color: "var(--text-muted)" }}>{i + 1}</td>
                    <td style={{ fontWeight: isSelected ? 600 : 400 }}>
                      {row.candidate_name}
                      {rec?.selectee_candidate_id === row.candidate_id && (
                        <span className="chip chip-tier-a" style={{ marginLeft: 6 }}>Selectee</span>
                      )}
                      {rec?.alternate_candidate_ids.includes(row.candidate_id) && (
                        <span className="chip chip-brand" style={{ marginLeft: 6 }}>Alt</span>
                      )}
                    </td>
                    <td style={{ textAlign: "center" }}>{tierChip(row.final_tier ?? row.proposed_tier ?? "")}</td>
                    <td style={{ textAlign: "center", fontWeight: 600 }}>{ranked?.score ?? row.stage_score ?? "—"}</td>
                    <td>{dispositionChip(row.final_disposition ?? row.proposed_disposition ?? "")}</td>
                    <td style={{ textAlign: "center", color: "var(--text)" }}>{ranked?.confidence ?? row.confidence ?? "—"}</td>
                    <td style={{ textAlign: "center" }}>
                      {rec?.selectee_candidate_id === row.candidate_id
                        ? <span className="chip chip-tier-a" style={{ fontSize: 10 }}>Selected</span>
                        : row.final_disposition?.toLowerCase() === "discarded"
                        ? <span className="chip chip-dim" style={{ fontSize: 10 }}>Not Selected</span>
                        : rec?.alternate_candidate_ids?.includes(row.candidate_id)
                        ? <span className="chip chip-brand" style={{ fontSize: 10 }}>Alternate</span>
                        : <span style={{ color: "var(--text-dim)", fontSize: 11 }}>—</span>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Right: Adjudication panel */}
      <div className="panel panel-320">
        <div className="panel-head">
          {selectedRow ? (
            <span style={{ fontSize: 15, fontWeight: 600, color: "var(--text)" }}>
              {selectedRow.candidate_name}
            </span>
          ) : (
            <span className="panel-head-title">Selection Decision</span>
          )}
          {selectedRow && tierChip(selectedRow.final_tier ?? selectedRow.proposed_tier ?? "")}
        </div>

        {!selectedRow ? (
          <div style={{ padding: "32px 16px", textAlign: "center", color: "var(--text-muted)" }}>
            Select a candidate to make a decision
          </div>
        ) : (
          <div style={{ overflowY: "auto", flex: 1, padding: "0 0 12px" }}>
            {/* Ranked candidate summary */}
            {rec?.rankings.find(r => r.candidate_id === selectedRow.candidate_id) && (() => {
              const ranked = rec!.rankings.find(r => r.candidate_id === selectedRow.candidate_id)!;
              return (
                <>
                  {ranked.strengths.length > 0 && (
                    <>
                      <div className="section-divider">Strengths</div>
                      <ul className="bullet-list" style={{ padding: "4px 12px 0" }}>
                        {ranked.strengths.map((s, i) => <li key={i}>{s}</li>)}
                      </ul>
                    </>
                  )}
                  {ranked.concerns.length > 0 && (
                    <>
                      <div className="section-divider">Concerns</div>
                      <ul className="bullet-list concern" style={{ padding: "4px 12px 0" }}>
                        {ranked.concerns.map((c, i) => <li key={i}>{c}</li>)}
                      </ul>
                    </>
                  )}
                </>
              );
            })()}

            <div className="section-divider">Your Decision</div>
            <div style={{ padding: "0 12px", display: "flex", flexDirection: "column", gap: 8 }}>
              <textarea
                className="textarea-input"
                style={{ minHeight: 60 }}
                placeholder="Rationale (required)"
                value={adjForm.rationale}
                onChange={e => setAdjForm(f => ({ ...f, rationale: e.target.value }))}
              />
              <textarea
                className="textarea-input"
                style={{ minHeight: 44 }}
                placeholder="Non-selection notes (optional)"
                value={adjForm.notes}
                onChange={e => setAdjForm(f => ({ ...f, notes: e.target.value }))}
              />
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                <button
                  className="btn btn-primary btn-sm"
                  disabled={adjMut.isPending}
                  onClick={() => adjAction("promote_candidate")}
                >
                  Make Official Selection
                </button>
                <button
                  className="btn btn-sm"
                  disabled={adjMut.isPending}
                  onClick={() => adjAction("discard_candidate")}
                  style={{ color: "var(--danger-text)" }}
                >
                  Not Selected
                </button>
                <button
                  className="btn btn-sm"
                  disabled={adjMut.isPending}
                  onClick={() => adjAction("restore_candidate")}
                >
                  Return to Consideration
                </button>
              </div>
              {adjMut.isError && <p className="feedback-error">Action failed</p>}
              {adjMut.isSuccess && <p className="feedback-success">Saved.</p>}
            </div>
          </div>
        )}

        {/* Dossier mini if dossier available */}
        {ws?.dossier && ws.dossier.candidate_id === candidateParam && (
          <>
            <div className="section-divider">AI Assessment</div>
            <div style={{ padding: "4px 12px 12px" }}>
              <p className="dossier-narrative">{ws.dossier.stage_record.ai_rationale || "—"}</p>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
