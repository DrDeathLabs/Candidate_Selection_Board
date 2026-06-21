import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { listCases, listInterviewQuestions } from "../lib/api";
import { useResolvedCaseId } from "../lib/cases";
import { formatLabel } from "../lib/format";

export function InterviewPlanningPage() {
  const casesQuery = useQuery({ queryKey: ["cases"], queryFn: listCases });
  const { caseId, selectCase } = useResolvedCaseId(casesQuery.data);
  const [selectedCandidate, setSelectedCandidate] = useState<string | null>(null);

  const questionsQuery = useQuery({
    queryKey: ["interview-questions", caseId],
    queryFn: () => listInterviewQuestions(caseId!),
    enabled: Boolean(caseId),
  });

  const questions = questionsQuery.data ?? [];
  const candidateNames = [...new Set(questions.map(q => q.candidate_name))].sort();

  const displayed = selectedCandidate
    ? questions.filter(q => q.candidate_name === selectedCandidate)
    : questions;

  const byCategory = displayed.reduce<Record<string, typeof displayed>>((acc, q) => {
    const k = q.category || "General";
    if (!acc[k]) acc[k] = [];
    acc[k].push(q);
    return acc;
  }, {});

  return (
    <div className="workspace">
      <div className="panel panel-220">
        <div className="panel-head">
          <span className="panel-head-title">Candidates</span>
        </div>
        <div style={{ overflowY: "auto", flex: 1 }}>
          <div
            className={`stage-item ${!selectedCandidate ? "active" : ""}`}
            onClick={() => setSelectedCandidate(null)}
          >
            <span className="stage-name">All candidates</span>
          </div>
          {candidateNames.map(name => (
            <div
              key={name}
              className={`stage-item ${selectedCandidate === name ? "active" : ""}`}
              onClick={() => setSelectedCandidate(name)}
            >
              <span className="stage-name">{name}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="panel panel-flex" style={{ overflow: "hidden", display: "flex", flexDirection: "column" }}>
        <div className="panel-head">
          <span className="panel-head-title">Interview Questions</span>
          <select className="select-input" style={{ height: 26, maxWidth: 240 }} value={caseId ?? ""} onChange={e => selectCase(e.target.value || null)}>
            <option value="">— Select engagement —</option>
            {(casesQuery.data ?? []).map(c => <option key={c.id} value={c.id}>{c.title}</option>)}
          </select>
          <span className="text-muted text-sm">{displayed.length} questions</span>
        </div>
        <div style={{ overflowY: "auto", flex: 1, padding: "0 0 16px" }}>
          {!caseId && <p className="loading-text">Select an engagement</p>}
          {caseId && questions.length === 0 && (
            <p className="loading-text">{questionsQuery.isLoading ? "Loading…" : "No interview questions generated yet"}</p>
          )}
          {Object.entries(byCategory).map(([category, qs]) => (
            <div key={category}>
              <div className="section-divider">{formatLabel(category)} ({qs.length})</div>
              {qs.map(q => (
                <div key={q.id} style={{ padding: "8px 12px", borderBottom: "1px solid var(--border)" }}>
                  {!selectedCandidate && (
                    <div style={{ fontSize: 10, color: "var(--text-dim)", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 3 }}>
                      {q.candidate_name}
                    </div>
                  )}
                  <p style={{ fontSize: 12, color: "var(--text)", lineHeight: 1.5 }}>{q.question_text}</p>
                  {q.rationale && (
                    <p style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 3 }}>{q.rationale}</p>
                  )}
                </div>
              ))}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
