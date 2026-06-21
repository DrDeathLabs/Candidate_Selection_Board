import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { listCandidateEvaluations, listCases } from "../lib/api";
import { useResolvedCaseId } from "../lib/cases";
import { formatLabel } from "../lib/format";

function ratingChip(rating: string) {
  const r = (rating ?? "").toLowerCase();
  if (r === "high")   return <span className="chip chip-success">H</span>;
  if (r === "medium") return <span className="chip chip-warning">M</span>;
  if (r === "low")    return <span className="chip chip-danger">L</span>;
  return <span className="chip chip-dim">{rating || "—"}</span>;
}

export function CandidateEvaluationPage() {
  const casesQuery = useQuery({ queryKey: ["cases"], queryFn: listCases });
  const { caseId, selectCase } = useResolvedCaseId(casesQuery.data);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const evsQuery = useQuery({
    queryKey: ["candidate-evaluations", caseId],
    queryFn: () => listCandidateEvaluations(caseId!),
    enabled: Boolean(caseId),
  });

  const evs = evsQuery.data ?? [];
  const selected = evs.find(e => e.candidate_id === selectedId) ?? null;

  return (
    <div className="workspace">
      <div className="panel panel-260">
        <div className="panel-head">
          <span className="panel-head-title">Evaluations</span>
          <span className="text-muted text-sm">{evs.length}</span>
        </div>
        <div style={{ padding: "6px 12px", borderBottom: "1px solid var(--border)" }}>
          <select className="select-input" style={{ height: 26, width: "100%" }} value={caseId ?? ""} onChange={e => selectCase(e.target.value || null)}>
            <option value="">— Select engagement —</option>
            {(casesQuery.data ?? []).map(c => <option key={c.id} value={c.id}>{c.title}</option>)}
          </select>
        </div>
        <div style={{ overflowY: "auto", flex: 1 }}>
          {evs.map(ev => (
            <div
              key={ev.candidate_id}
              className={`stage-item ${selectedId === ev.candidate_id ? "active" : ""}`}
              onClick={() => setSelectedId(ev.candidate_id)}
            >
              <div className="stage-item-body">
                <div className="stage-name">{ev.candidate_name}</div>
                <div className="stage-meta">Score: {ev.overall_score} · {ev.fact_count} facts</div>
              </div>
              <span className={`chip ${ev.disposition === "qualified" || ev.disposition === "best_qualified" ? "chip-success" : "chip-neutral"}`} style={{ fontSize: 9 }}>
                {formatLabel(ev.disposition)}
              </span>
            </div>
          ))}
          {evs.length === 0 && (
            <p className="loading-text">{!caseId ? "Select engagement" : evsQuery.isLoading ? "Loading…" : "No evaluations"}</p>
          )}
        </div>
      </div>

      <div className="panel panel-flex" style={{ overflowY: "auto" }}>
        {!selected ? (
          <div style={{ padding: "32px 16px", textAlign: "center", color: "var(--text-muted)", fontSize: 12 }}>
            Select a candidate to view their evaluation
          </div>
        ) : (
          <>
            <div className="panel-head">
              <span className="panel-head-title">{selected.candidate_name}</span>
              <span style={{ color: "var(--text-muted)", fontSize: 12 }}>Score: {selected.overall_score}</span>
            </div>
            <div style={{ padding: "12px 16px" }}>
              <table className="mini-table" style={{ marginBottom: 16 }}>
                <tbody>
                  <tr><td className="mini-key">Disposition</td><td>{formatLabel(selected.disposition)}</td></tr>
                  <tr><td className="mini-key">Overall Score</td><td style={{ fontWeight: 600 }}>{selected.overall_score}</td></tr>
                  <tr><td className="mini-key">Resume Conf.</td><td>{selected.resume_confidence}</td></tr>
                  <tr><td className="mini-key">Facts</td><td>{selected.fact_count}</td></tr>
                  <tr><td className="mini-key">Resume</td><td className="truncate" style={{ maxWidth: 200 }}>{selected.matched_resume ?? "—"}</td></tr>
                </tbody>
              </table>

              {selected.ratings.length > 0 && (
                <div className="settings-section">
                  <div className="settings-section-head">Dimension Ratings</div>
                  <table className="rubric-tbl">
                    <thead>
                      <tr>
                        <th>Dimension</th>
                        <th style={{ textAlign: "center" }}>Rating</th>
                        <th style={{ textAlign: "center" }}>Score</th>
                        <th>Evidence</th>
                      </tr>
                    </thead>
                    <tbody>
                      {selected.ratings.map(r => (
                        <tr key={r.id}>
                          <td>{r.dimension_id}</td>
                          <td style={{ textAlign: "center" }}>{ratingChip(r.rating)}</td>
                          <td style={{ textAlign: "center", fontWeight: 600 }}>{r.score}</td>
                          <td style={{ maxWidth: 280 }}>
                            <span className="rubric-rat-text">{r.evidence_summary}</span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
