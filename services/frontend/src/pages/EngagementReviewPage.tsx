import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";

import {
  clearStageOverrides,
  getBoardMeeting,
  getReviewWorkspace,
  recordNarrativeResponse,
  recordWorkflowStageDecision,
  resetCandidateNarrativeArtifacts,
  runWorkflowStage,
  updateWorkflowStage,
  type BoardMeetingRecord,
  type CandidateDossierView,
  type CandidateMatrixRow,
  type CandidateStageDecisionPayload,
  type ResumeProfile,
  type StageArtifactRecord,
  type WorkflowDimensionScoreRecord,
} from "../lib/api";
import { formatLabel } from "../lib/format";

const TIER_ORDER = ["A", "B", "C", "D", "UNRANKED"];

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

function ratingLabel(rating: string): { label: string; cls: string } {
  const r = (rating ?? "").toLowerCase().replace(/_/g, " ");
  if (r === "high" || r === "exceeds")    return { label: "Exceeds",         cls: "chip-success" };
  if (r === "medium" || r === "meets")    return { label: "Meets",            cls: "chip-warning" };
  if (r === "low" || r === "partial")     return { label: "Partially Meets",  cls: "chip-dim-warn" };
  if (r === "does not meet")              return { label: "Does Not Meet",    cls: "chip-dim" };
  return { label: rating || "—", cls: "chip-dim" };
}

function ratingChip(rating: string) {
  const { label, cls } = ratingLabel(rating);
  return <span className={`chip ${cls}`} style={{ fontSize: 11 }}>{label}</span>;
}

function stageStatusDot(status: string) {
  const s = (status ?? "").toLowerCase();
  if (s === "complete" || s === "completed") return <span className="status-dot green" />;
  if (s === "active" || s === "running") return <span className="status-dot amber" />;
  return <span className="status-dot gray" />;
}

type DossierTab = "snapshot" | "evidence" | "scorecard" | "overrides" | "history" | "narrative" | "interview";

function evalScore(scores: CandidateDossierView["stage_record"]["dimension_scores"]): number {
  const totalWeight = scores.reduce((s, r) => s + Number(r.weight ?? 0), 0);
  if (totalWeight <= 0) return 0;
  const weightedSum = scores.reduce((s, r) => s + Number(r.score ?? 0) * Number(r.weight ?? 0), 0);
  return (weightedSum / totalWeight) * 20;
}

function DossierSnapshot({
  sr,
  dossier,
  boardMeeting,
}: {
  sr: CandidateDossierView["stage_record"];
  dossier: CandidateDossierView;
  boardMeeting: BoardMeetingRecord | null;
}) {
  const score = sr.dimension_scores.length > 0 ? evalScore(sr.dimension_scores) : null;
  const synthesis = boardMeeting?.phase3_synthesis ?? null;
  const boardRec = synthesis?.recommendation ?? sr.council_recommendation ?? null;
  const councilConf = synthesis?.confidence != null ? `${Math.round((synthesis.confidence as number) * 100)}%` : null;
  const tier = sr.final_tier ?? sr.proposed_tier ?? "";

  // Evidence quality summary from Phase I agent turns
  const ph1 = boardMeeting?.phase1_turns ?? [];
  const eqCounts = ph1.reduce(
    (acc, t) => {
      const eq = ((t.evidence_quality as string) ?? "").toUpperCase();
      if (eq === "DOCUMENTED") acc.DOCUMENTED++;
      else if (eq === "INFERRED") acc.INFERRED++;
      else if (eq === "ABSENT") acc.ABSENT++;
      return acc;
    },
    { DOCUMENTED: 0, INFERRED: 0, ABSENT: 0 },
  );

  return (
    <div className="dossier-section">
      {/* 4-cell stat grid */}
      <div className="snapshot-grid" style={{ marginBottom: 14 }}>
        <div className="snapshot-cell">
          <div className="snapshot-label">Score</div>
          <div className="snapshot-val">{score != null ? score.toFixed(2) : "—"}</div>
        </div>
        <div className="snapshot-cell">
          <div className="snapshot-label">Tier</div>
          <div className="snapshot-val">{extractTierLetter(tier) || "—"}</div>
        </div>
        <div className="snapshot-cell">
          <div className="snapshot-label">Board</div>
          <div className="snapshot-val" style={{ fontSize: boardRec && boardRec.length > 7 ? 11 : 15 }}>{boardRec ?? "—"}</div>
        </div>
        <div className="snapshot-cell">
          <div className="snapshot-label">Confidence</div>
          <div className="snapshot-val">{councilConf ?? "—"}</div>
        </div>
      </div>

      {/* Board Assessment — meeting_summary is the premium narrative */}
      {boardMeeting?.meeting_summary ? (
        <>
          <div className="dossier-section-label">Board Assessment</div>
          <p className="dossier-narrative">{boardMeeting.meeting_summary}</p>
        </>
      ) : sr.ai_rationale ? (
        <>
          <div className="dossier-section-label">AI Assessment</div>
          <p className="dossier-narrative">{sr.ai_rationale}</p>
        </>
      ) : null}

      {/* Board Agreements */}
      {(synthesis?.agreements as string[] | undefined)?.length ? (
        <>
          <div className="dossier-section-label">Board Agreements</div>
          <ul className="bullet-list">
            {(synthesis!.agreements as string[]).map((a, i) => <li key={i}>{a}</li>)}
          </ul>
        </>
      ) : null}

      {/* Interview Targets */}
      {(synthesis?.open_questions as string[] | undefined)?.length ? (
        <>
          <div className="dossier-section-label">Interview Targets</div>
          <ul className="bullet-list">
            {(synthesis!.open_questions as string[]).map((q, i) => <li key={i}>{q}</li>)}
          </ul>
        </>
      ) : null}

      {/* Key Differentiators */}
      {sr.differentiators.length > 0 && (
        <>
          <div className="dossier-section-label">Key Differentiators</div>
          <ul className="bullet-list">
            {sr.differentiators.map((d, i) => <li key={i}>{d}</li>)}
          </ul>
        </>
      )}

      {/* Concerns */}
      {sr.risks.length > 0 && (
        <>
          <div className="dossier-section-label">Concerns</div>
          <ul className="bullet-list concern">
            {sr.risks.map((r, i) => <li key={i}>{r}</li>)}
          </ul>
        </>
      )}

      {/* Evidence quality */}
      {ph1.length > 0 && (
        <>
          <div className="dossier-section-label">Evidence Quality</div>
          <div style={{ fontSize: 12, color: "var(--text-muted)", padding: "2px 12px 8px" }}>
            <span style={{ color: "var(--success-text)" }}>Documented {eqCounts.DOCUMENTED}</span>
            {" · "}
            <span style={{ color: "var(--warning-text)" }}>Inferred {eqCounts.INFERRED}</span>
            {" · "}
            <span style={{ color: "var(--text-dim)" }}>Absent {eqCounts.ABSENT}</span>
            <span style={{ color: "var(--text-dim)", marginLeft: 6 }}>({ph1.length} agents)</span>
          </div>
        </>
      )}

      {/* OSINT */}
      {sr.osint_summary && (
        <>
          <div className="dossier-section-label">OSINT Summary</div>
          <p className="dossier-narrative">{sr.osint_summary}</p>
        </>
      )}

      {/* Flags */}
      {sr.flags.length > 0 && (
        <>
          <div className="dossier-section-label">Flags</div>
          {sr.flags.map((f, i) => (
            <div key={i} className="flag-row"><span className="status-dot red" />{f}</div>
          ))}
        </>
      )}
    </div>
  );
}

function ResumeProfileSection({ profile }: { profile: ResumeProfile }) {
  return (
    <div>
      {/* Career History */}
      {profile.work_experience.length > 0 && (
        <>
          <div className="dossier-section-label">Career History</div>
          {profile.work_experience.map((job, i) => (
            <div key={i} style={{ padding: "6px 12px", borderBottom: "1px solid var(--border)" }}>
              <div style={{ display: "flex", alignItems: "baseline", gap: 6, flexWrap: "wrap" }}>
                <span style={{ fontWeight: 600, fontSize: 13, color: "var(--text)" }}>{job.title}</span>
                <span style={{ color: "var(--text-muted)", fontSize: 12 }}>·</span>
                <span style={{ fontSize: 13, color: "var(--text)" }}>{job.employer}</span>
                {job.grade_level && <span className="chip chip-dim" style={{ fontSize: 10 }}>{job.grade_level}</span>}
                {job.is_current && <span className="chip chip-brand" style={{ fontSize: 10 }}>Current</span>}
              </div>
              <div style={{ display: "flex", gap: 12, marginTop: 2, flexWrap: "wrap" }}>
                {(job.start_date || job.end_date) && (
                  <span style={{ fontSize: 11, color: "var(--text-muted)" }}>
                    {job.start_date ?? "?"} — {job.is_current ? "Present" : (job.end_date ?? "?")}
                  </span>
                )}
                {job.location && <span style={{ fontSize: 11, color: "var(--text-muted)" }}>{job.location}</span>}
                {job.is_supervisory && job.team_size != null && (
                  <span style={{ fontSize: 11, color: "var(--text-muted)" }}>{job.team_size.toLocaleString()} staff</span>
                )}
                {job.budget && <span style={{ fontSize: 11, color: "var(--text-muted)" }}>${job.budget}</span>}
              </div>
              {job.highlights.length > 0 && (
                <ul className="bullet-list" style={{ marginTop: 4, paddingLeft: 0 }}>
                  {job.highlights.map((h, j) => <li key={j} style={{ fontSize: 12 }}>{h}</li>)}
                </ul>
              )}
            </div>
          ))}
        </>
      )}

      {/* Education */}
      {profile.education.length > 0 && (
        <>
          <div className="dossier-section-label" style={{ marginTop: 8 }}>Education</div>
          {profile.education.map((ed, i) => (
            <div key={i} style={{ padding: "5px 12px", display: "flex", gap: 8, alignItems: "baseline" }}>
              <span style={{ fontWeight: 600, fontSize: 12, color: "var(--text)" }}>{ed.degree}{ed.field ? ` — ${ed.field}` : ""}</span>
              <span style={{ fontSize: 12, color: "var(--text-muted)" }}>· {ed.institution}{ed.graduation_year ? ` · ${ed.graduation_year}` : ""}</span>
            </div>
          ))}
        </>
      )}

      {/* Certifications */}
      {profile.certifications.length > 0 && (
        <>
          <div className="dossier-section-label" style={{ marginTop: 8 }}>Certifications</div>
          <div style={{ padding: "5px 12px", display: "flex", flexWrap: "wrap", gap: 6 }}>
            {profile.certifications.map((cert, i) => (
              <span key={i} className="chip chip-neutral" style={{ fontSize: 11 }}>
                {cert.name}{cert.issuer ? ` · ${cert.issuer}` : ""}
              </span>
            ))}
          </div>
        </>
      )}

      {/* Clearance */}
      {profile.clearance && (
        <>
          <div className="dossier-section-label" style={{ marginTop: 8 }}>Clearance</div>
          <div style={{ padding: "5px 12px", fontSize: 12, color: "var(--text)" }}>
            {profile.clearance.level}{profile.clearance.status ? ` · ${profile.clearance.status}` : ""}
          </div>
        </>
      )}

      {/* Skills */}
      {profile.skills.length > 0 && (
        <>
          <div className="dossier-section-label" style={{ marginTop: 8 }}>Skills</div>
          <div style={{ padding: "5px 12px", display: "flex", flexWrap: "wrap", gap: 4 }}>
            {profile.skills.map((s, i) => <span key={i} className="chip chip-dim" style={{ fontSize: 10 }}>{s}</span>)}
          </div>
        </>
      )}
    </div>
  );
}

function DossierEvidence({ ratings, facts, resumeProfile }: { ratings: WorkflowDimensionScoreRecord[]; facts: Array<Record<string, unknown>>; resumeProfile: ResumeProfile | null }) {
  return (
    <div className="dossier-section">
      {/* Resume Profile — structured career data from parsed resume */}
      {resumeProfile && <ResumeProfileSection profile={resumeProfile} />}

      {(ratings.length > 0 || facts.length > 0) && (
        <div className="dossier-section-label" style={{ marginTop: resumeProfile ? 12 : 0 }}>Dimension Evidence</div>
      )}
      {ratings.map((r, i) => (
        <div key={i} className="evidence-block">
          <div className="evidence-header">
            <span className="evidence-dim">{r.title}</span>
            {ratingChip(r.rating)}
            <span className="evidence-score">{r.score}</span>
          </div>
          {r.evidence_summary && <p className="evidence-text">{r.evidence_summary}</p>}
          {r.strengths.length > 0 && (
            <ul className="bullet-list">
              {r.strengths.map((s, j) => <li key={j}>{s}</li>)}
            </ul>
          )}
          {r.concerns.length > 0 && (
            <ul className="bullet-list concern">
              {r.concerns.map((c, j) => <li key={j}>{c}</li>)}
            </ul>
          )}
          {r.overridden && (
            <div className="override-badge">Overridden{r.override_rationale ? ` — ${r.override_rationale}` : ""}</div>
          )}
        </div>
      ))}

      {facts.length > 0 && (
        <>
          <div className="dossier-section-label" style={{ marginTop: 12 }}>Evidence Facts ({facts.length})</div>
          {facts.slice(0, 20).map((f, i) => (
            <div key={i} className="fact-row">
              <span className="fact-type">{String(f.fact_type ?? "")}</span>
              <span className="fact-val">{String((f.fact_value as Record<string, unknown>)?.value ?? JSON.stringify(f.fact_value))}</span>
              {f.evidence_quote != null && <div className="fact-quote">"{String(f.evidence_quote)}"</div>}
            </div>
          ))}
        </>
      )}
    </div>
  );
}

function DossierScorecard({ ratings }: { ratings: WorkflowDimensionScoreRecord[] }) {
  const computed = evalScore(ratings);
  return (
    <div className="dossier-section">
      <table className="rubric-tbl">
        <thead>
          <tr>
            <th>Dimension</th>
            <th className="col-wt">Wt</th>
            <th style={{ width: 64, textAlign: "center" }}>Rating</th>
            <th style={{ width: 56, textAlign: "center" }}>Score</th>
          </tr>
        </thead>
        <tbody>
          {ratings.map((r, i) => {
            const contrib = ((Number(r.score ?? 0) / 5.0) * Number(r.weight ?? 0)).toFixed(1);
            return (
              <tr key={i} className={r.overridden ? "row-overridden" : ""}>
                <td>
                  {r.title}
                  {r.overridden && <span className="chip chip-warning" style={{ marginLeft: 6 }}>OVR</span>}
                </td>
                <td className="col-wt">×{r.weight}</td>
                <td style={{ textAlign: "center" }}>{ratingChip(r.rating)}</td>
                <td style={{ textAlign: "center", fontWeight: 600 }}>{contrib}</td>
              </tr>
            );
          })}
          <tr style={{ borderTop: "1px solid var(--border-strong)", fontWeight: 700 }}>
            <td colSpan={3}>Score</td>
            <td style={{ textAlign: "center" }}>{computed.toFixed(2)} / 100</td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}

function DossierOverrides({
  form, onChange, dimensionScores, onSave, onClearAll, isPending, isError,
}: {
  form: CandidateStageDecisionPayload;
  onChange: (patch: Partial<CandidateStageDecisionPayload>) => void;
  dimensionScores: WorkflowDimensionScoreRecord[];
  onSave: () => void;
  onClearAll: () => void;
  isPending: boolean;
  isError: boolean;
}) {
  return (
    <div className="dossier-section">
      <div className="action-row" style={{ marginBottom: 12, gap: 6 }}>
        <button className="btn btn-primary btn-sm" disabled={isPending} onClick={onSave}>
          {isPending ? "Saving…" : "Save overrides"}
        </button>
        <button className="btn btn-sm" disabled={isPending} style={{ color: "var(--warning-text)" }} onClick={onClearAll}>
          Reset to defaults
        </button>
        {isError && <span className="feedback-error">Save failed</span>}
      </div>

      <div className="dossier-section-label">Tier Override</div>
      <select className="select-input" style={{ width: "100%" }} value={form.final_tier ?? ""} onChange={e => onChange({ final_tier: e.target.value || null })}>
        <option value="">— AI proposed —</option>
        {["A", "B", "C", "D"].map(t => <option key={t} value={`Tier ${t}`}>Tier {t}</option>)}
      </select>

      <div className="dossier-section-label" style={{ marginTop: 10 }}>Disposition</div>
      <select className="select-input" style={{ width: "100%" }} value={form.final_disposition ?? ""} onChange={e => onChange({ final_disposition: e.target.value || null })}>
        <option value="">— AI proposed —</option>
        {["qualified", "best_qualified", "not_qualified", "referred", "selected", "not_selected"].map(d => (
          <option key={d} value={d}>{formatLabel(d)}</option>
        ))}
      </select>

      <div className="dossier-section-label" style={{ marginTop: 10 }}>Advancement Decision</div>
      <select className="select-input" style={{ width: "100%" }} value={form.advancement_decision ?? ""} onChange={e => onChange({ advancement_decision: e.target.value || null })}>
        <option value="">— Clear / AI decides —</option>
        <option value="advance">Advance</option>
        <option value="hold">Hold</option>
        <option value="do_not_advance">Do Not Advance</option>
      </select>

      <div className="dossier-section-label" style={{ marginTop: 10 }}>Rationale</div>
      <textarea
        className="textarea-input"
        style={{ minHeight: 72, width: "100%" }}
        value={form.rationale ?? ""}
        onChange={e => onChange({ rationale: e.target.value })}
        placeholder="Override rationale (required for audit)"
      />

      {dimensionScores.length > 0 && (
        <>
          <div className="dossier-section-label" style={{ marginTop: 10 }}>Score Overrides</div>
          <table className="rubric-tbl">
            <thead>
              <tr><th>Dimension</th><th>Current</th><th>Override</th></tr>
            </thead>
            <tbody>
              {dimensionScores.map((d, i) => {
                const existing = form.dimension_overrides?.find(o => o.dimension_id === d.dimension_id);
                return (
                  <tr key={i}>
                    <td>{d.title}</td>
                    <td style={{ textAlign: "center" }}>{ratingChip(d.rating)}</td>
                    <td>
                      <select
                        className="select-input"
                        style={{ height: 30, width: "100%" }}
                        value={existing?.rating ?? ""}
                        onChange={e => {
                          const rating = e.target.value;
                          const overrides = (form.dimension_overrides ?? []).filter(o => o.dimension_id !== d.dimension_id);
                          if (rating) {
                            const score = rating === "high" ? Number(d.weight) * 3 : rating === "medium" ? Number(d.weight) * 2 : Number(d.weight);
                            overrides.push({ dimension_id: d.dimension_id, rating, score: String(score) });
                          }
                          onChange({ dimension_overrides: overrides });
                        }}
                      >
                        <option value="">—</option>
                        <option value="high">High</option>
                        <option value="medium">Medium</option>
                        <option value="low">Low</option>
                      </select>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </>
      )}

    </div>
  );
}

function DossierHistory({ dossier }: { dossier: CandidateDossierView }) {
  return (
    <div className="dossier-section">
      <div className="dossier-section-label">Stage History</div>
      {dossier.stage_history.length === 0 && <p className="loading-text">No history</p>}
      {dossier.stage_history.map((h, i) => (
        <div key={i} className="history-row">
          <div className="history-stage">{h.stage_name}</div>
          <div className="history-detail">
            Tier {h.final_tier ?? h.proposed_tier ?? "—"} · {formatLabel(h.final_disposition ?? h.proposed_disposition ?? "pending")}
            {h.advancement_decision && ` · ${formatLabel(h.advancement_decision)}`}
          </div>
          {h.rationale && <div className="history-rationale">{h.rationale}</div>}
          <div className="history-meta">{h.updated_at ? new Date(h.updated_at).toLocaleString() : "—"}</div>
        </div>
      ))}

      {dossier.audit_events.length > 0 && (
        <>
          <div className="dossier-section-label" style={{ marginTop: 12 }}>Audit Events</div>
          {dossier.audit_events.slice(0, 30).map((e, i) => (
            <div key={i} className="audit-row">
              <span className="audit-type">{formatLabel(e.event_type)}</span>
              <span className="audit-meta">{new Date(e.occurred_at).toLocaleString()}</span>
            </div>
          ))}
        </>
      )}
    </div>
  );
}

type StageQuestion = { number: number; question: string; context: string };

function StageQuestionPanel({
  caseId,
  stageId,
  stageConfig,
  questionsKey,
  panelLabel,
  secondaryAction,
  subtitleText,
}: {
  caseId: string;
  stageId: string;
  stageConfig: Record<string, unknown>;
  questionsKey: string;
  panelLabel: string;
  secondaryAction: { label: string; onClick: () => void | Promise<void> };
  subtitleText?: string;
}) {
  const qc = useQueryClient();
  const serverQuestions = (stageConfig[questionsKey] as StageQuestion[] | undefined) ?? [];

  const [expanded, setExpanded] = useState(false);
  const [localQuestions, setLocalQuestions] = useState<StageQuestion[]>(serverQuestions);
  const [editingIdx, setEditingIdx] = useState<number | null>(null);
  const [draftQ, setDraftQ] = useState("");
  const [draftCtx, setDraftCtx] = useState("");
  const [secondaryPending, setSecondaryPending] = useState(false);

  // Sync from server when not mid-edit
  useEffect(() => {
    if (editingIdx === null) setLocalQuestions(serverQuestions);
  }, [serverQuestions.length, editingIdx]);

  const saveMut = useMutation({
    mutationFn: (updatedQuestions: StageQuestion[]) =>
      updateWorkflowStage(caseId, stageId, {
        config: { ...stageConfig, [questionsKey]: updatedQuestions },
      }),
    onSuccess() {
      setEditingIdx(null);
      qc.invalidateQueries({ queryKey: ["review-workspace", caseId] });
    },
  });

  function startEdit(i: number) {
    setEditingIdx(i);
    setDraftQ(localQuestions[i]?.question ?? "");
    setDraftCtx(localQuestions[i]?.context ?? "");
  }

  function saveRow(i: number) {
    const updated = localQuestions.map((q, idx) =>
      idx === i ? { ...q, question: draftQ, context: draftCtx } : q
    );
    setLocalQuestions(updated);
    saveMut.mutate(updated);
  }

  function cancelEdit() {
    if (editingIdx !== null && !localQuestions[editingIdx]?.question) {
      const pruned = localQuestions.filter((_, i) => i !== editingIdx);
      setLocalQuestions(pruned);
    }
    setEditingIdx(null);
  }

  function deleteQuestion(i: number) {
    if (!confirm(`Remove question ${i + 1}?`)) return;
    const updated = localQuestions
      .filter((_, idx) => idx !== i)
      .map((q, idx) => ({ ...q, number: idx + 1 }));
    setLocalQuestions(updated);
    saveMut.mutate(updated);
  }

  function addQuestion() {
    const newQ: StageQuestion = { number: localQuestions.length + 1, question: "", context: "" };
    const updated = [...localQuestions, newQ];
    setLocalQuestions(updated);
    setExpanded(true);
    setEditingIdx(updated.length - 1);
    setDraftQ("");
    setDraftCtx("");
  }

  async function handleSecondaryAction(e: React.MouseEvent) {
    e.stopPropagation();
    setSecondaryPending(true);
    try { await secondaryAction.onClick(); } finally { setSecondaryPending(false); }
  }

  return (
    <div style={{ borderBottom: "1px solid var(--border)", background: "var(--bg-elevated)", flexShrink: 0 }}>
      {/* Collapsed header — always visible */}
      <div
        onClick={() => setExpanded(e => !e)}
        style={{ display: "flex", alignItems: "center", gap: 8, padding: "7px 14px", cursor: "pointer", userSelect: "none" }}
      >
        <span style={{ fontSize: 11, color: "var(--text-dim)", transition: "transform 0.15s", display: "inline-block", transform: expanded ? "rotate(90deg)" : "rotate(0deg)" }}>▶</span>
        <span style={{ fontSize: 11, fontWeight: 600, letterSpacing: "0.06em", color: "var(--text-dim)", textTransform: "uppercase" }}>
          {panelLabel} ({localQuestions.length})
        </span>
        {!!subtitleText && (
          <span style={{ fontSize: 11, color: "var(--text-muted)" }}>· {subtitleText}</span>
        )}
        <button
          className="btn btn-sm"
          style={{ marginLeft: "auto", fontSize: 11, opacity: 0.7 }}
          onClick={handleSecondaryAction}
          disabled={secondaryPending}
        >
          {secondaryPending ? "Loading…" : secondaryAction.label}
        </button>
      </div>

      {/* Expanded body */}
      {expanded && (
        <div style={{ padding: "0 14px 10px" }}>
          {localQuestions.length === 0 && editingIdx === null && (
            <p style={{ fontSize: 12, color: "var(--text-dim)", margin: "6px 0" }}>No questions yet — use the button above or add one below.</p>
          )}

          {localQuestions.map((q, i) => (
            <div key={i} style={{ borderTop: "1px solid var(--border)", padding: "8px 0" }}>
              {editingIdx === i ? (
                /* Edit mode for this row */
                <div>
                  <textarea
                    className="textarea-input"
                    style={{ width: "100%", minHeight: 72, fontSize: 12, lineHeight: 1.5, marginBottom: 6 }}
                    placeholder="Question text…"
                    value={draftQ}
                    onChange={e => setDraftQ(e.target.value)}
                    autoFocus
                  />
                  <input
                    className="input"
                    style={{ width: "100%", fontSize: 11, marginBottom: 8 }}
                    placeholder="Context — which duty or factor this addresses…"
                    value={draftCtx}
                    onChange={e => setDraftCtx(e.target.value)}
                  />
                  <div style={{ display: "flex", gap: 6 }}>
                    <button
                      className="btn btn-sm btn-primary"
                      onClick={() => saveRow(i)}
                      disabled={!draftQ.trim() || saveMut.isPending}
                    >
                      {saveMut.isPending ? "Saving…" : "Save"}
                    </button>
                    <button className="btn btn-sm" onClick={cancelEdit}>Cancel</button>
                  </div>
                </div>
              ) : (
                /* View mode for this row */
                <div style={{ display: "flex", alignItems: "flex-start", gap: 8 }}>
                  <span style={{ fontSize: 12, color: "var(--text-dim)", minWidth: 20, paddingTop: 1 }}>{i + 1}.</span>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 12, color: "var(--text)", lineHeight: 1.5 }}>{q.question}</div>
                    {!!q.context && (
                      <div style={{ fontSize: 11, color: "var(--text-dim)", marginTop: 2 }}>{q.context}</div>
                    )}
                  </div>
                  <div style={{ display: "flex", gap: 4, flexShrink: 0 }}>
                    <button
                      className="btn btn-sm"
                      style={{ fontSize: 11, opacity: 0.7 }}
                      onClick={() => startEdit(i)}
                    >Edit</button>
                    <button
                      className="btn btn-sm"
                      style={{ fontSize: 11, opacity: 0.5 }}
                      onClick={() => deleteQuestion(i)}
                      disabled={saveMut.isPending}
                    >✕</button>
                  </div>
                </div>
              )}
            </div>
          ))}

          <div style={{ marginTop: 8 }}>
            <button
              className="btn btn-sm"
              style={{ fontSize: 11, opacity: 0.7 }}
              onClick={addQuestion}
              disabled={editingIdx !== null}
            >+ Add question</button>
          </div>
        </div>
      )}
    </div>
  );
}

function DossierInterview({
  caseId,
  stageId,
  candidateId,
  stageConfig,
  narrativeAnalysisArtifact,
  stageTemplateKey,
}: {
  caseId: string;
  stageId: string;
  candidateId: string;
  stageConfig: Record<string, unknown>;
  narrativeAnalysisArtifact: StageArtifactRecord | null;
  stageTemplateKey: string;
}) {
  const isPanelInterview = stageTemplateKey === "panel_interview";
  const qc = useQueryClient();

  // Per-candidate overrides stored in stage config under candidate_questions[candidateId]
  const allCandidateQuestions = (stageConfig.candidate_questions as Record<string, StageQuestion[]> | undefined) ?? {};
  const savedQuestions: StageQuestion[] | null = allCandidateQuestions[candidateId] ?? null;

  // Fall back to AI-generated questions from the narrative analysis artifact
  const aiQuestions: StageQuestion[] = ((narrativeAnalysisArtifact?.metadata?.screening_interview_questions as Array<{ number: number; question: string; focus?: string; basis?: string }> | undefined) ?? [])
    .map(q => ({ number: q.number, question: q.question, context: q.focus || q.basis || "" }));

  const serverQuestions = savedQuestions ?? aiQuestions;

  const [localQuestions, setLocalQuestions] = useState<StageQuestion[]>(serverQuestions);
  const [editingIdx, setEditingIdx] = useState<number | null>(null);
  const [draftQ, setDraftQ] = useState("");
  const [draftCtx, setDraftCtx] = useState("");

  useEffect(() => {
    if (editingIdx === null) setLocalQuestions(serverQuestions);
  }, [serverQuestions.length, editingIdx]);

  const saveMut = useMutation({
    mutationFn: (updatedQuestions: StageQuestion[]) =>
      updateWorkflowStage(caseId, stageId, {
        config: {
          ...stageConfig,
          candidate_questions: { ...allCandidateQuestions, [candidateId]: updatedQuestions },
        },
      }),
    onSuccess() {
      setEditingIdx(null);
      qc.invalidateQueries({ queryKey: ["review-workspace", caseId] });
    },
  });

  function startEdit(i: number) {
    setEditingIdx(i);
    setDraftQ(localQuestions[i]?.question ?? "");
    setDraftCtx(localQuestions[i]?.context ?? "");
  }

  function saveRow(i: number) {
    const updated = localQuestions.map((q, idx) =>
      idx === i ? { ...q, question: draftQ, context: draftCtx } : q
    );
    setLocalQuestions(updated);
    saveMut.mutate(updated);
  }

  function cancelEdit() {
    if (editingIdx !== null && !localQuestions[editingIdx]?.question) {
      setLocalQuestions(localQuestions.filter((_, i) => i !== editingIdx));
    }
    setEditingIdx(null);
  }

  function deleteQuestion(i: number) {
    if (!confirm(`Remove question ${i + 1}?`)) return;
    const updated = localQuestions
      .filter((_, idx) => idx !== i)
      .map((q, idx) => ({ ...q, number: idx + 1 }));
    setLocalQuestions(updated);
    saveMut.mutate(updated);
  }

  function addQuestion() {
    const newQ: StageQuestion = { number: localQuestions.length + 1, question: "", context: "" };
    const updated = [...localQuestions, newQ];
    setLocalQuestions(updated);
    setEditingIdx(updated.length - 1);
    setDraftQ("");
    setDraftCtx("");
  }

  function resetToAI() {
    if (!confirm("Reset to AI-generated questions from this candidate's narrative response?")) return;
    setLocalQuestions(aiQuestions);
    saveMut.mutate(aiQuestions);
  }

  // Panel interview: universal questions from PD, same for all candidates — read-only in dossier
  if (isPanelInterview) {
    const panelQuestions = (stageConfig.panel_questions as StageQuestion[] | undefined) ?? [];
    if (panelQuestions.length === 0) {
      return (
        <div className="dossier-section">
          <p className="loading-text">Panel interview questions not yet generated. Run the Panel Interview stage to generate questions from the position description.</p>
        </div>
      );
    }
    return (
      <div className="dossier-section">
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
          <span className="dossier-section-label" style={{ margin: 0 }}>
            Panel Questions — {panelQuestions.length} — Applied to all candidates
          </span>
        </div>
        <p style={{ fontSize: 11, color: "var(--text-dim)", marginBottom: 10 }}>
          Edit this question set in the panel above the candidate matrix.
        </p>
        {panelQuestions.map((q, i) => (
          <div key={i} style={{ borderTop: "1px solid var(--border)", padding: "8px 0" }}>
            <div style={{ display: "flex", alignItems: "flex-start", gap: 8 }}>
              <span style={{ fontSize: 12, color: "var(--text-dim)", minWidth: 20, paddingTop: 1 }}>{i + 1}.</span>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 12, color: "var(--text)", lineHeight: 1.5 }}>{q.question}</div>
                {!!q.context && (
                  <div style={{ fontSize: 11, color: "var(--text-dim)", marginTop: 2 }}>Focus: {q.context}</div>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
    );
  }

  if (!narrativeAnalysisArtifact) {
    return (
      <div className="dossier-section">
        <p className="loading-text">No narrative analysis available. Complete the Narrative Request stage for this candidate first.</p>
      </div>
    );
  }

  return (
    <div className="dossier-section">
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
        <span className="dossier-section-label" style={{ margin: 0 }}>
          Screening Questions — {localQuestions.length} based on narrative response
        </span>
        {savedQuestions && (
          <button className="btn btn-sm" style={{ fontSize: 11, opacity: 0.6 }} onClick={resetToAI} disabled={saveMut.isPending}>
            Reset to AI
          </button>
        )}
      </div>

      {localQuestions.length === 0 && editingIdx === null && (
        <p style={{ fontSize: 12, color: "var(--text-dim)", marginBottom: 8 }}>No questions — add one below.</p>
      )}

      {localQuestions.map((q, i) => (
        <div key={i} style={{ borderTop: "1px solid var(--border)", padding: "8px 0" }}>
          {editingIdx === i ? (
            <div>
              <textarea
                className="textarea-input"
                style={{ width: "100%", minHeight: 72, fontSize: 12, lineHeight: 1.5, marginBottom: 6 }}
                placeholder="Question text…"
                value={draftQ}
                onChange={e => setDraftQ(e.target.value)}
                autoFocus
              />
              <input
                className="input"
                style={{ width: "100%", fontSize: 11, marginBottom: 8 }}
                placeholder="Focus — what gap or claim this probes…"
                value={draftCtx}
                onChange={e => setDraftCtx(e.target.value)}
              />
              <div style={{ display: "flex", gap: 6 }}>
                <button className="btn btn-sm btn-primary" onClick={() => saveRow(i)} disabled={!draftQ.trim() || saveMut.isPending}>
                  {saveMut.isPending ? "Saving…" : "Save"}
                </button>
                <button className="btn btn-sm" onClick={cancelEdit}>Cancel</button>
              </div>
            </div>
          ) : (
            <div style={{ display: "flex", alignItems: "flex-start", gap: 8 }}>
              <span style={{ fontSize: 12, color: "var(--text-dim)", minWidth: 20, paddingTop: 1 }}>{i + 1}.</span>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 12, color: "var(--text)", lineHeight: 1.5 }}>{q.question}</div>
                {!!q.context && (
                  <div style={{ fontSize: 11, color: "var(--text-dim)", marginTop: 2 }}>Focus: {q.context}</div>
                )}
              </div>
              <div style={{ display: "flex", gap: 4, flexShrink: 0 }}>
                <button className="btn btn-sm" style={{ fontSize: 11, opacity: 0.7 }} onClick={() => startEdit(i)}>Edit</button>
                <button className="btn btn-sm" style={{ fontSize: 11, opacity: 0.5 }} onClick={() => deleteQuestion(i)} disabled={saveMut.isPending}>✕</button>
              </div>
            </div>
          )}
        </div>
      ))}

      <div style={{ marginTop: 8 }}>
        <button className="btn btn-sm" style={{ fontSize: 11, opacity: 0.7 }} onClick={addQuestion} disabled={editingIdx !== null}>
          + Add question
        </button>
      </div>
    </div>
  );
}

function DossierNarrative({ caseId, dossier, stageId }: { caseId: string; dossier: CandidateDossierView; stageId: string }) {
  const qc = useQueryClient();
  const [responseText, setResponseText] = useState("");
  const [editing, setEditing] = useState(false);

  const promptArtifact: StageArtifactRecord | undefined = dossier.stage_artifacts.find(
    a => a.artifact_type === "prompt_request",
  );
  const responseArtifact: StageArtifactRecord | undefined = dossier.stage_artifacts.find(
    a => a.artifact_type === "candidate_response",
  );
  const analysisArtifact: StageArtifactRecord | undefined = dossier.stage_artifacts.find(
    a => a.artifact_type === "narrative_analysis",
  );

  const email = (promptArtifact?.metadata?.candidate_email as string | null) ?? dossier.candidate_email ?? null;
  const analysis = (analysisArtifact?.metadata ?? {}) as Record<string, unknown>;

  const submitMut = useMutation({
    mutationFn: (text: string) => recordNarrativeResponse(caseId, stageId, dossier.candidate_id, text),
    onSuccess() {
      setEditing(false);
      setResponseText("");
      qc.invalidateQueries({ queryKey: ["review-workspace", caseId] });
    },
  });

  const resetMut = useMutation({
    mutationFn: () => resetCandidateNarrativeArtifacts(caseId, stageId, dossier.candidate_id),
    onSuccess() { qc.invalidateQueries({ queryKey: ["review-workspace", caseId] }); },
  });

  if (!promptArtifact) {
    return (
      <div className="dossier-section">
        <p className="loading-text">Narrative request not yet generated — run the Narrative Request stage from the stage rail.</p>
      </div>
    );
  }

  const screeningQs = (analysis.screening_interview_questions as Array<Record<string, unknown>> | undefined) ?? [];
  const panelQs = (analysis.panel_interview_questions as Array<Record<string, unknown>> | undefined) ?? [];
  const questionAssessments = (analysis.question_assessments as Array<Record<string, unknown>> | undefined) ?? [];
  const expertInsights = (analysis.expert_insights as Array<Record<string, unknown>> | undefined) ?? [];
  const allScreeningText = screeningQs.map((q, i) => `${q.number ?? i + 1}. ${q.question ?? ""}`).join("\n");
  const allPanelText = panelQs.map((q, i) => `${q.number ?? i + 1}. ${q.question ?? ""}`).join("\n");

  const showResponseForm = !responseArtifact || editing;

  return (
    <div className="dossier-section">
      <div style={{ display: "flex", gap: 6, marginBottom: 8, flexWrap: "wrap", alignItems: "center" }}>
        <span className="chip chip-success">Prompt generated</span>
        {(promptArtifact.metadata?.prompt_sent as boolean | undefined)
          ? <span className="chip chip-brand">Sent</span>
          : <span className="chip chip-dim">Not sent</span>}
        {responseArtifact && <span className="chip chip-success">Response on file</span>}
        {analysisArtifact && <span className="chip chip-brand">Analyzed</span>}
        <button
          className="btn btn-sm"
          style={{ marginLeft: "auto", opacity: 0.6, fontSize: 11 }}
          onClick={() => resetMut.mutate()}
          disabled={resetMut.isPending}
        >
          {resetMut.isPending ? "Resetting…" : "Reset letter"}
        </button>
      </div>

      {!!email && (
        <div style={{ marginBottom: 10, fontSize: 12, color: "var(--text-muted)" }}>
          Send to: <span style={{ color: "var(--text)", marginLeft: 4 }}>{String(email)}</span>
          <button
            onClick={() => navigator.clipboard.writeText(email!)}
            style={{ marginLeft: 8, background: "none", border: "1px solid var(--border)", color: "var(--text-muted)", cursor: "pointer", fontSize: 11, padding: "1px 8px", borderRadius: 3 }}
          >Copy</button>
        </div>
      )}

      {!!promptArtifact.metadata?.subject_line && (
        <div style={{ marginBottom: 8, fontSize: 12 }}>
          <span style={{ color: "var(--text-dim)" }}>Subject: </span>
          <span style={{ color: "var(--text)" }}>{String(promptArtifact.metadata.subject_line)}</span>
        </div>
      )}

      <div className="dossier-section-label">Narrative Request Letter</div>
      <pre style={{ whiteSpace: "pre-wrap", fontSize: 12, lineHeight: 1.65, color: "var(--text)", fontFamily: "inherit", margin: 0, padding: "10px 12px", background: "var(--bg-elevated)", border: "1px solid var(--border)", borderRadius: 3 }}>
        {promptArtifact.content}
      </pre>
      <button
        onClick={() => navigator.clipboard.writeText(promptArtifact.content)}
        className="btn btn-sm"
        style={{ marginTop: 6, width: "100%" }}
      >Copy letter to clipboard</button>

      <div className="dossier-section-label" style={{ marginTop: 14 }}>Candidate Response</div>

      {showResponseForm ? (
        <>
          {!responseArtifact && (
            <p style={{ fontSize: 12, color: "var(--text-dim)", marginBottom: 8 }}>
              Paste the candidate's written response here to trigger AI evaluation.
            </p>
          )}
          <textarea
            className="textarea-input"
            style={{ minHeight: 140, width: "100%", fontSize: 12, lineHeight: 1.6 }}
            value={editing ? responseText || responseArtifact?.content || "" : responseText}
            onChange={e => setResponseText(e.target.value)}
            placeholder="Paste candidate narrative response..."
            onFocus={() => { if (editing && !responseText && responseArtifact) setResponseText(responseArtifact.content); }}
          />
          <div style={{ display: "flex", gap: 6, marginTop: 6 }}>
            <button
              className="btn btn-sm btn-primary"
              style={{ flex: 1 }}
              onClick={() => submitMut.mutate(editing ? responseText : responseText)}
              disabled={!(editing ? responseText : responseText).trim() || submitMut.isPending}
            >
              {submitMut.isPending ? "Saving & analyzing…" : "Save response + analyze"}
            </button>
            {editing && (
              <button className="btn btn-sm" onClick={() => { setEditing(false); setResponseText(""); }}>
                Cancel
              </button>
            )}
          </div>
          {submitMut.isError && (
            <p className="feedback-error" style={{ marginTop: 6 }}>Failed to save response. Please try again.</p>
          )}
        </>
      ) : (
        <>
          <pre style={{ whiteSpace: "pre-wrap", fontSize: 12, lineHeight: 1.6, color: "var(--text)", fontFamily: "inherit", margin: 0, padding: "10px 12px", background: "var(--bg-elevated)", border: "1px solid var(--border)", borderRadius: 3, maxHeight: 200, overflow: "auto" }}>
            {responseArtifact?.content}
          </pre>
          <div style={{ display: "flex", gap: 6, marginTop: 6 }}>
            <button
              className="btn btn-sm"
              style={{ flex: 1 }}
              onClick={() => { setEditing(true); setResponseText(responseArtifact?.content ?? ""); }}
            >Edit response</button>
          </div>
          {!analysisArtifact && (
            <p style={{ fontSize: 12, color: "var(--text-dim)", marginTop: 8 }}>
              AI analysis in progress…
            </p>
          )}
        </>
      )}

      {analysisArtifact && (
        <>
          <div className="dossier-section-label" style={{ marginTop: 14 }}>Response Evaluation</div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 12 }}>
            <div style={{ padding: "8px 10px", background: "var(--bg-elevated)", border: "1px solid var(--border)", borderRadius: 3 }}>
              <div style={{ fontSize: 11, color: "var(--text-dim)", marginBottom: 2 }}>RESPONSE SCORE</div>
              <div style={{ fontSize: 20, fontWeight: 700, color: "var(--text)" }}>{String(analysis.response_score ?? "—")}</div>
            </div>
            <div style={{ padding: "8px 10px", background: "var(--bg-elevated)", border: "1px solid var(--border)", borderRadius: 3 }}>
              <div style={{ fontSize: 11, color: "var(--text-dim)", marginBottom: 2 }}>TIER</div>
              <div style={{ fontSize: 14, fontWeight: 600, color: "var(--text)" }}>{String(analysis.response_tier ?? "—")}</div>
            </div>
          </div>

          {/* Advance recommendation */}
          {!!analysis.advance_recommendation && (
            <div style={{ padding: "8px 10px", background: "var(--bg-elevated)", border: "1px solid var(--border)", borderRadius: 3, marginBottom: 10 }}>
              <div style={{ fontSize: 11, color: "var(--text-dim)", marginBottom: 2 }}>RECOMMENDATION</div>
              <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text)" }}>{String(analysis.advance_recommendation)}</div>
              {!!analysis.advance_rationale && (
                <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 4 }}>{String(analysis.advance_rationale)}</div>
              )}
            </div>
          )}

          {/* Question assessments */}
          {questionAssessments.length > 0 && (
            <>
              <div className="dossier-section-label">Question Assessments</div>
              {questionAssessments.map((qa, i) => (
                <div key={i} style={{ marginBottom: 8, padding: "7px 10px", background: "var(--bg-elevated)", border: "1px solid var(--border)", borderRadius: 3 }}>
                  <div style={{ display: "flex", gap: 6, alignItems: "center", marginBottom: 4 }}>
                    <span style={{ fontSize: 11, color: "var(--text-dim)" }}>Q{String(qa.question_number ?? i + 1)}</span>
                    {ratingChip(String(qa.quality ?? ""))}
                    {!(qa.addressed as boolean | undefined) && <span className="chip chip-dim">Not addressed</span>}
                  </div>
                  <div style={{ fontSize: 12, color: "var(--text)" }}>{String(qa.key_finding ?? "")}</div>
                  {!!qa.gap && <div style={{ fontSize: 11, color: "var(--warning-text)", marginTop: 3 }}>{String(qa.gap)}</div>}
                </div>
              ))}
            </>
          )}

          {/* Expert insights */}
          {expertInsights.length > 0 && (
            <>
              <div className="dossier-section-label">Expert Insights</div>
              {expertInsights.map((insight, i) => (
                <div key={i} style={{ marginBottom: 6, padding: "6px 10px", borderLeft: "2px solid var(--border)", background: "var(--bg-elevated)" }}>
                  <div style={{ display: "flex", gap: 6, alignItems: "baseline", marginBottom: 2 }}>
                    <span style={{ fontSize: 11, fontWeight: 600, color: "var(--text)" }}>{String(insight.category ?? "")}</span>
                    <span style={{ fontSize: 10, color: "var(--text-dim)" }}>{String(insight.alignment ?? "")}</span>
                  </div>
                  <div style={{ fontSize: 12, color: "var(--text-muted)" }}>{String(insight.finding ?? "")}</div>
                </div>
              ))}
            </>
          )}

          {/* Screening interview questions */}
          {screeningQs.length > 0 && (
            <>
              <div className="dossier-section-label" style={{ marginTop: 12 }}>
                Screening Interview Questions
                <button
                  onClick={() => navigator.clipboard.writeText(allScreeningText)}
                  style={{ marginLeft: 8, background: "none", border: "1px solid var(--border)", color: "var(--text-muted)", cursor: "pointer", fontSize: 10, padding: "1px 7px", borderRadius: 3 }}
                >Copy all</button>
              </div>
              {screeningQs.map((q, i) => (
                <div key={i} style={{ marginBottom: 8, padding: "7px 10px", background: "var(--bg-elevated)", border: "1px solid var(--border)", borderRadius: 3 }}>
                  <div style={{ fontSize: 12, color: "var(--text)", marginBottom: 4 }}>
                    <strong>{String(q.number ?? i + 1)}.</strong> {String(q.question ?? "")}
                  </div>
                  <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                    {!!q.focus && <span style={{ fontSize: 10, color: "var(--text-dim)" }}>Focus: {String(q.focus)}</span>}
                    {!!q.basis && <span style={{ fontSize: 10, color: "var(--text-dim)" }}>· {String(q.basis)}</span>}
                  </div>
                </div>
              ))}
            </>
          )}

          {/* Panel interview questions */}
          {panelQs.length > 0 && (
            <>
              <div className="dossier-section-label" style={{ marginTop: 12 }}>
                Panel Interview Questions
                <button
                  onClick={() => navigator.clipboard.writeText(allPanelText)}
                  style={{ marginLeft: 8, background: "none", border: "1px solid var(--border)", color: "var(--text-muted)", cursor: "pointer", fontSize: 10, padding: "1px 7px", borderRadius: 3 }}
                >Copy all</button>
              </div>
              {panelQs.map((q, i) => (
                <div key={i} style={{ marginBottom: 8, padding: "7px 10px", background: "var(--bg-elevated)", border: "1px solid var(--border)", borderRadius: 3 }}>
                  <div style={{ fontSize: 12, color: "var(--text)", marginBottom: 4 }}>
                    <strong>{String(q.number ?? i + 1)}.</strong> {String(q.question ?? "")}
                  </div>
                  <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                    {!!q.focus && <span style={{ fontSize: 10, color: "var(--text-dim)" }}>Focus: {String(q.focus)}</span>}
                    {!!q.basis && <span style={{ fontSize: 10, color: "var(--text-dim)" }}>· {String(q.basis)}</span>}
                  </div>
                </div>
              ))}
            </>
          )}
        </>
      )}
    </div>
  );
}

function Dossier({ caseId, dossier, stageId, stageTemplateKey, stageConfig, onClose }: { caseId: string; dossier: CandidateDossierView; stageId: string; stageTemplateKey?: string | null; stageConfig?: Record<string, unknown>; onClose?: () => void }) {
  const qc = useQueryClient();
  const isNarrativeStage = stageTemplateKey === "narrative_request";
  const isInterviewStage = stageTemplateKey === "screening_interview" || stageTemplateKey === "panel_interview";
  const defaultTab: DossierTab = isNarrativeStage ? "narrative" : isInterviewStage ? "interview" : "snapshot";
  const [tab, setTab] = useState<DossierTab>(defaultTab);

  const boardMeetingQuery = useQuery({
    queryKey: ["board-meeting", caseId, dossier.candidate_id],
    queryFn: () => getBoardMeeting(caseId, dossier.candidate_id),
    retry: false,
    staleTime: 30_000,
  });
  const boardMeeting = boardMeetingQuery.data ?? null;
  const sr = dossier.stage_record;
  const displayTier = sr.final_tier ?? sr.proposed_tier;

  const [overrideForm, setOverrideForm] = useState<CandidateStageDecisionPayload>({
    final_tier: sr.final_tier ?? null,
    final_disposition: sr.final_disposition ?? null,
    advancement_decision: sr.advancement_decision ?? null,
    rationale: sr.manual_rationale ?? "",
    dimension_overrides: [],
  });

  const decisionMut = useMutation({
    mutationFn: (payload: CandidateStageDecisionPayload) =>
      recordWorkflowStageDecision(caseId, stageId, dossier.candidate_id, payload),
    onSuccess() {
      qc.invalidateQueries({ queryKey: ["review-workspace", caseId] });
    },
  });

  const TABS: Array<{ key: DossierTab; label: string }> = [
    { key: "snapshot", label: "Snapshot" },
    { key: "evidence", label: "Evidence" },
    { key: "scorecard", label: "Scorecard" },
    ...(isNarrativeStage ? [{ key: "narrative" as DossierTab, label: "Narrative" }] : []),
    ...(isInterviewStage ? [{ key: "interview" as DossierTab, label: "Questions" }] : []),
    { key: "overrides", label: "Overrides" },
    { key: "history", label: "History" },
  ];

  return (
    <div className="dossier">
      <div className="dossier-header">
        <span className="dossier-name">{dossier.candidate_name}</span>
        {tierChip(displayTier ?? "")}
        {(sr.stage_score_label || sr.stage_score) && (
          <span style={{ fontSize: 13, color: "var(--text-muted)", fontWeight: 400 }}>
            {sr.stage_score_label && sr.stage_score ? `${sr.stage_score_label} · ${sr.stage_score}` : sr.stage_score_label || sr.stage_score}
          </span>
        )}
        {sr.override_count > 0 && (
          <span className="chip chip-warning">{sr.override_count} ovr</span>
        )}
        {onClose && (
          <button
            onClick={onClose}
            style={{ marginLeft: "auto", background: "none", border: "none", color: "var(--text-muted)", cursor: "pointer", fontSize: 20, lineHeight: 1, padding: "0 6px", flexShrink: 0 }}
            title="Close"
          >×</button>
        )}
      </div>
      <div className="dossier-tabs">
        {TABS.map(t => (
          <button key={t.key} className={`dossier-tab ${tab === t.key ? "active" : ""}`} onClick={() => setTab(t.key)}>
            {t.label}
          </button>
        ))}
      </div>
      <div className="dossier-body">
        {tab === "snapshot"  && <DossierSnapshot sr={sr} dossier={dossier} boardMeeting={boardMeeting} />}
        {tab === "evidence"  && <DossierEvidence ratings={sr.dimension_scores} facts={dossier.facts} resumeProfile={dossier.resume_profile ?? null} />}
        {tab === "scorecard" && <DossierScorecard ratings={sr.dimension_scores} />}
        {tab === "narrative" && <DossierNarrative caseId={caseId} dossier={dossier} stageId={stageId} />}
        {tab === "interview" && (
          <DossierInterview
            caseId={caseId}
            stageId={stageId}
            candidateId={dossier.candidate_id}
            stageConfig={stageConfig ?? {}}
            narrativeAnalysisArtifact={dossier.stage_artifacts.find(a => a.artifact_type === "narrative_analysis") ?? null}
            stageTemplateKey={stageTemplateKey ?? ""}
          />
        )}
        {tab === "overrides" && (
          <DossierOverrides
            form={overrideForm}
            onChange={patch => setOverrideForm(f => ({ ...f, ...patch }))}
            dimensionScores={sr.dimension_scores}
            onSave={() => {
              const payload = { ...overrideForm };
              if (overrideForm.final_tier === null) payload.clear_final_tier = true;
              if (overrideForm.advancement_decision === null) payload.clear_advancement_decision = true;
              if (overrideForm.final_disposition === null) payload.clear_final_disposition = true;
              decisionMut.mutate(payload);
            }}
            onClearAll={() => decisionMut.mutate({ clear_all_overrides: true })}
            isPending={decisionMut.isPending}
            isError={decisionMut.isError}
          />
        )}
        {tab === "history"   && <DossierHistory dossier={dossier} />}
      </div>
    </div>
  );
}

export function EngagementReviewPage() {
  const { engagementId } = useParams<{ engagementId: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const qc = useQueryClient();

  const stageParam    = searchParams.get("stage")     ?? null;
  const candidateParam = searchParams.get("candidate") ?? null;
  const [tierFilter, setTierFilter] = useState("all");
  const [search, setSearch] = useState("");

  const wsQuery = useQuery({
    queryKey: ["review-workspace", engagementId, stageParam, candidateParam],
    queryFn: () => getReviewWorkspace(engagementId!, { stage: stageParam, candidate: candidateParam }),
    enabled: Boolean(engagementId),
    staleTime: 10_000,
  });

  const runStageMut = useMutation({
    mutationFn: ({ stageId, force = false }: { stageId: string; force?: boolean }) =>
      runWorkflowStage(engagementId!, stageId, force),
    onSuccess() { qc.invalidateQueries({ queryKey: ["review-workspace", engagementId] }); },
  });

  const acceptStageMut = useMutation({
    mutationFn: ({ stageId, config }: { stageId: string; config: Record<string, unknown>; nextStageId: string | null }) =>
      updateWorkflowStage(engagementId!, stageId, { config }),
    onSuccess: (_data, variables) => {
      qc.invalidateQueries({ queryKey: ["review-workspace", engagementId] });
      if (variables.nextStageId) selectStage(variables.nextStageId);
    },
  });

  const clearStageOverridesMut = useMutation({
    mutationFn: (stageId: string) => clearStageOverrides(engagementId!, stageId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["review-workspace", engagementId] }),
  });

  const rerunStageMut = useMutation({
    mutationFn: async ({ stageId, config }: { stageId: string; config: Record<string, unknown> }) => {
      // eslint-disable-next-line @typescript-eslint/no-unused-vars
      const { official_accepted, accepted_at, ...rest } = config;
      await updateWorkflowStage(engagementId!, stageId, { config: rest });
      await runWorkflowStage(engagementId!, stageId, true);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["review-workspace", engagementId] }),
  });

  const stageDecisionMut = useMutation({
    mutationFn: ({ stageId, candidateId, finalTier }: { stageId: string; candidateId: string; finalTier: string | null }) =>
      recordWorkflowStageDecision(engagementId!, stageId, candidateId,
        finalTier
          ? { final_tier: finalTier, advancement_decision: "do_not_advance", rationale: "Manually removed from advancing pool" }
          : { clear_final_tier: true, advancement_decision: "advance", rationale: "Restored to advancing pool" },
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["review-workspace", engagementId] }),
  });

  const autoTriggeredStages = useRef<Set<string>>(new Set());

  useEffect(() => {
    const stage = wsQuery.data?.active_stage;
    if (
      stage?.template_key === "narrative_request" &&
      stage.status !== "completed" &&
      !runStageMut.isPending &&
      !autoTriggeredStages.current.has(stage.id)
    ) {
      autoTriggeredStages.current.add(stage.id);
      runStageMut.mutate({ stageId: stage.id, force: false });
    }
  }, [wsQuery.data?.active_stage?.id, wsQuery.data?.active_stage?.status, runStageMut.isPending]);

  const ws = wsQuery.data;

  function selectStage(stageId: string) {
    setSearchParams(prev => {
      const p = new URLSearchParams(prev);
      p.set("stage", stageId);
      p.delete("candidate");
      return p;
    });
  }

  function selectCandidate(candidateId: string) {
    setSearchParams(prev => {
      const p = new URLSearchParams(prev);
      p.set("candidate", candidateId);
      return p;
    });
  }

  function closeCandidate() {
    setSearchParams(prev => {
      const p = new URLSearchParams(prev);
      p.delete("candidate");
      return p;
    });
  }

  const filteredRows = (ws?.candidate_rows ?? []).filter(row => {
    const tier = (row.final_tier ?? row.proposed_tier ?? "").toUpperCase();
    if (tierFilter !== "all" && tier !== tierFilter) return false;
    if (search && !row.candidate_name.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  const sortedRows = [...filteredRows].sort((a, b) => a.rank - b.rank);

  const rows: Array<CandidateMatrixRow | { type: "divider"; label: string }> = [];
  let lastTier: string | null = null;
  for (const row of sortedRows) {
    const tier = extractTierLetter(row.final_tier ?? row.proposed_tier ?? "");
    if (tier !== lastTier) {
      rows.push({ type: "divider", label: tier === "UNRANKED" ? "Unranked" : `Tier ${tier}` });
      lastTier = tier;
    }
    rows.push(row);
  }

  const activeDossier = ws?.dossier ?? null;
  const activeStageId = ws?.active_stage?.id ?? null;

  if (!engagementId) return <div className="error-state">No engagement selected.</div>;

  return (
    <div className="workspace">
      {/* Stage rail */}
      <div className="panel panel-200" style={{ overflow: "hidden" }}>
        <div className="panel-head">
          <span className="panel-head-title">Stages</span>
        </div>
        <div className="stage-rail">
          {(ws?.stage_navigation ?? []).map(stage => (
            <div
              key={stage.id}
              className={`stage-item ${(stageParam ?? ws?.active_stage_id) === stage.id ? "active" : ""}`}
              onClick={() => selectStage(stage.id)}
            >
              {stageStatusDot(stage.last_run_status)}
              <div className="stage-item-body">
                <div className="stage-name">{stage.name}</div>
                {stage.candidate_count > 0 && (
                  <div className="stage-meta">
                    {stage.candidate_count} candidates
                    {stage.flagged_candidate_count > 0 ? ` · ${stage.flagged_candidate_count} flagged` : ""}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
        {ws?.active_stage && (
          <div style={{ borderTop: "1px solid var(--border)", flexShrink: 0 }}>
            {ws.active_stage.last_run_status === "completed" ? (() => {
              const navStages = ws.stage_navigation ?? [];
              const activeIdx = navStages.findIndex(s => s.id === ws.active_stage!.id);
              const nextStage = activeIdx >= 0 ? navStages[activeIdx + 1] : undefined;
              const isAccepted = !!(ws.active_stage.config as Record<string, unknown> | undefined)?.official_accepted;
              const acceptedAt = (ws.active_stage.config as Record<string, unknown> | undefined)?.accepted_at as string | undefined;

              const isExplicitlyExcluded = (r: typeof ws.candidate_rows[0]) =>
                r.final_disposition === "do_not_advance" ||
                r.final_disposition === "eliminate" ||
                r.advancement_decision === "do_not_advance" ||
                r.advancement_decision === "eliminate" ||
                (r.flags ?? []).includes("Candidate is currently discarded");
              const isExplicitlyAdvanced = (r: typeof ws.candidate_rows[0]) =>
                r.advancement_decision === "advance" ||
                r.advancement_decision === "hold" ||
                r.advancement_decision === "selected" ||
                r.advancement_decision === "alternate_ready" ||
                r.advancement_decision === "selectee_ready";
              const advancing = (ws.candidate_rows ?? []).filter(r => {
                if (isExplicitlyExcluded(r)) return false;
                if (isExplicitlyAdvanced(r)) return true;
                const t = extractTierLetter(r.final_tier ?? r.proposed_tier ?? "");
                return t === "A" || t === "B";
              });
              const notAdvancing = (ws.candidate_rows ?? []).filter(r => {
                if (isExplicitlyExcluded(r)) return true;
                if (isExplicitlyAdvanced(r)) return false;
                const t = extractTierLetter(r.final_tier ?? r.proposed_tier ?? "");
                return t !== "A" && t !== "B";
              });

              if (acceptStageMut.isPending) {
                // Saving in progress — neutral indicator
                return (
                  <div style={{ padding: "8px 10px", display: "flex", flexDirection: "column", gap: 4 }}>
                    <div style={{ fontSize: 11, color: "var(--text-muted)" }}>Saving…</div>
                  </div>
                );
              }

              if (isAccepted) {
                // State C — accepted
                return (
                  <div style={{ padding: "8px 10px", display: "flex", flexDirection: "column", gap: 4 }}>
                    <div style={{ fontSize: 11, color: "var(--success-text)", fontWeight: 600 }}>✓ Review Accepted</div>
                    {acceptedAt && (
                      <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
                        {new Date(acceptedAt).toLocaleDateString()}
                      </div>
                    )}
                    <button
                      className="btn btn-sm"
                      style={{ width: "100%", opacity: 0.5, marginTop: 4 }}
                      disabled={rerunStageMut.isPending}
                      onClick={() => ws.active_stage && rerunStageMut.mutate({ stageId: ws.active_stage.id, config: (ws.active_stage.config as Record<string, unknown>) ?? {} })}
                    >
                      {rerunStageMut.isPending ? "Re-running…" : "Re-run stage"}
                    </button>
                  </div>
                );
              }

              // State B — completed but not yet accepted
              return (
                <div style={{ padding: "8px 10px", borderTop: "1px solid color-mix(in srgb, var(--warning) 35%, transparent)", display: "flex", flexDirection: "column", gap: 3 }}>
                  <div style={{ fontSize: 11, fontWeight: 700, color: "var(--warning-text)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}>
                    ⚠ Pending your review
                  </div>

                  {advancing.length > 0 && (
                    <>
                      <div style={{ fontSize: 11, color: "var(--success-text)", fontWeight: 600 }}>
                        Advancing ({advancing.length})
                      </div>
                      {advancing.map(r => (
                        <div key={r.candidate_id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 11, padding: "1px 0" }}>
                          <span style={{ color: "var(--text)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 100 }}>
                            {r.candidate_name}
                          </span>
                          <div style={{ display: "flex", alignItems: "center", gap: 4, flexShrink: 0 }}>
                            {tierChip(r.final_tier ?? r.proposed_tier ?? "")}
                            <button
                              title="Remove from advancing"
                              disabled={stageDecisionMut.isPending}
                              onClick={e => { e.stopPropagation(); stageDecisionMut.mutate({ stageId: ws.active_stage!.id, candidateId: r.candidate_id, finalTier: "Tier C" }); }}
                              style={{ background: "none", border: "none", color: "var(--text-muted)", cursor: "pointer", fontSize: 13, lineHeight: 1, padding: "0 2px", opacity: 0.7 }}
                            >×</button>
                          </div>
                        </div>
                      ))}
                    </>
                  )}

                  {notAdvancing.length > 0 && (
                    <>
                      <div style={{ fontSize: 11, color: "var(--text-dim)", fontWeight: 600, marginTop: 4 }}>
                        Not Advancing ({notAdvancing.length})
                      </div>
                      {notAdvancing.map(r => (
                        <div key={r.candidate_id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 11, padding: "1px 0" }}>
                          <span style={{ color: "var(--text-muted)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 110 }}>
                            {r.candidate_name}
                          </span>
                          <button
                            title="Move to advancing"
                            disabled={stageDecisionMut.isPending}
                            onClick={e => { e.stopPropagation(); stageDecisionMut.mutate({ stageId: ws.active_stage!.id, candidateId: r.candidate_id, finalTier: null }); }}
                            style={{ background: "none", border: "none", color: "var(--success-text)", cursor: "pointer", fontSize: 11, lineHeight: 1, padding: "0 2px", opacity: 0.7, flexShrink: 0 }}
                          >↑</button>
                        </div>
                      ))}
                    </>
                  )}

                  <button
                    className="btn btn-sm btn-primary"
                    style={{ width: "100%", marginTop: 8, height: "auto", minHeight: 26, whiteSpace: "normal", lineHeight: 1.35, padding: "5px 8px" }}
                    disabled={acceptStageMut.isPending}
                    onClick={() => {
                      const existingConfig = (ws.active_stage!.config as Record<string, unknown>) ?? {};
                      const newConfig = { ...existingConfig, official_accepted: true, accepted_at: new Date().toISOString() };
                      acceptStageMut.mutate({ stageId: ws.active_stage!.id, config: newConfig, nextStageId: nextStage?.id ?? null });
                    }}
                  >
                    {nextStage ? `Accept & Advance to ${nextStage.name} →` : "Accept Stage Results"}
                  </button>

                  {acceptStageMut.isError && (
                    <p style={{ fontSize: 11, color: "var(--danger-text)", margin: "4px 0 0" }}>Failed to save — try again.</p>
                  )}

                  <button
                    className="btn btn-sm"
                    style={{ width: "100%", opacity: 0.5, marginTop: 4 }}
                    disabled={runStageMut.isPending}
                    onClick={() => ws.active_stage && runStageMut.mutate({ stageId: ws.active_stage.id, force: true })}
                  >
                    {runStageMut.isPending ? "Running…" : "Re-run stage"}
                  </button>

                  <button
                    className="btn btn-sm"
                    style={{ width: "100%", opacity: 0.5, marginTop: 4, color: "var(--warning-text)" }}
                    disabled={clearStageOverridesMut.isPending}
                    onClick={() => {
                      if (ws.active_stage && window.confirm("Clear all overrides for all candidates in this stage? This cannot be undone.")) {
                        clearStageOverridesMut.mutate(ws.active_stage.id);
                      }
                    }}
                  >
                    {clearStageOverridesMut.isPending ? "Clearing…" : "Clear all overrides"}
                  </button>
                </div>
              );
            })() : (
              <div style={{ padding: "8px 10px" }}>
                {(() => {
                  const isNarrative = ws.active_stage?.template_key === "narrative_request";
                  const label = runStageMut.isPending
                    ? (isNarrative ? "Generating…" : "Running…")
                    : (isNarrative ? "Regenerate Request" : `Run ${ws.active_stage.name}`);
                  return (
                    <>
                      <button
                        className={`btn btn-sm${isNarrative && !runStageMut.isPending ? "" : " btn-primary"}`}
                        style={{ width: "100%", opacity: isNarrative && !runStageMut.isPending ? 0.65 : 1 }}
                        disabled={runStageMut.isPending}
                        onClick={() => ws.active_stage && runStageMut.mutate({ stageId: ws.active_stage.id, force: isNarrative })}
                      >
                        {label}
                      </button>
                      {runStageMut.isPending && isNarrative && (
                        <p style={{ fontSize: 11, color: "var(--text-dim)", textAlign: "center", marginTop: 6, marginBottom: 0 }}>
                          Generating narrative requests…
                        </p>
                      )}
                    </>
                  );
                })()}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Matrix */}
      <div className="panel panel-flex" style={{ overflow: "hidden", display: "flex", flexDirection: "column" }}>
        <div className="panel-head">
          <input
            className="input"
            style={{ height: 32, width: 210 }}
            placeholder="Search candidates…"
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
          <select className="select-input" style={{ height: 32 }} value={tierFilter} onChange={e => setTierFilter(e.target.value)}>
            <option value="all">All tiers</option>
            {TIER_ORDER.map(t => <option key={t} value={t}>Tier {t}</option>)}
          </select>
          <span className="text-muted text-sm" style={{ marginLeft: 8 }}>
            {filteredRows.length} candidate{filteredRows.length !== 1 ? "s" : ""}
          </span>
          {wsQuery.isLoading && <span className="text-muted text-sm" style={{ marginLeft: "auto" }}>Loading…</span>}
        </div>

        {ws?.active_stage?.template_key === "narrative_request" && ws.active_stage.id && (
          <StageQuestionPanel
            caseId={engagementId!}
            stageId={ws.active_stage.id}
            stageConfig={ws.active_stage.config}
            questionsKey="narrative_questions"
            panelLabel="Narrative Questions"
            subtitleText={(ws.active_stage.config.narrative_subject_line as string | undefined) ?? ""}
            secondaryAction={{
              label: "Regenerate from PD",
              onClick: async () => {
                if (!ws.active_stage) return;
                const clearedConfig = Object.fromEntries(
                  Object.entries(ws.active_stage.config).filter(
                    ([k]) => !["narrative_questions", "narrative_subject_line", "narrative_closing"].includes(k)
                  )
                );
                await updateWorkflowStage(engagementId!, ws.active_stage.id, { config: clearedConfig });
                runStageMut.mutate({ stageId: ws.active_stage.id, force: true });
              },
            }}
          />
        )}

        {ws?.active_stage?.template_key === "panel_interview" && ws.active_stage.id && (
          <StageQuestionPanel
            caseId={engagementId!}
            stageId={ws.active_stage.id}
            stageConfig={ws.active_stage.config}
            questionsKey="panel_questions"
            panelLabel="Panel Interview Questions"
            subtitleText="Applied to all candidates — derived from position requirements"
            secondaryAction={{
              label: "Regenerate from PD",
              onClick: async () => {
                if (!ws.active_stage) return;
                const clearedConfig = Object.fromEntries(
                  Object.entries(ws.active_stage.config).filter(([k]) => k !== "panel_questions")
                );
                await updateWorkflowStage(engagementId!, ws.active_stage.id, { config: clearedConfig });
                runStageMut.mutate({ stageId: ws.active_stage.id, force: true });
              },
            }}
          />
        )}


        {ws?.empty_state && filteredRows.length === 0 ? (
          <div className="empty-state">
            <div className="empty-state-title">{ws.empty_state.title}</div>
            <div className="empty-state-detail">{ws.empty_state.detail}</div>
            {ws.empty_state.action_label && ws.empty_state.target_stage_id && (
              <button
                className="btn btn-primary btn-sm"
                style={{ marginTop: 8 }}
                disabled={runStageMut.isPending}
                onClick={() => ws.empty_state?.target_stage_id && runStageMut.mutate({ stageId: ws.empty_state.target_stage_id, force: false })}
              >
                {ws.empty_state.action_label}
              </button>
            )}
          </div>
        ) : (
          <>
            {ws?.active_stage?.last_run_status === "completed" && !acceptStageMut.isPending && !(ws.active_stage.config as Record<string, unknown> | undefined)?.official_accepted && (
              <div style={{
                background: "color-mix(in srgb, var(--warning) 10%, transparent)",
                border: "1px solid color-mix(in srgb, var(--warning) 30%, transparent)",
                borderRadius: 3, padding: "8px 14px", marginBottom: 8, flexShrink: 0,
                display: "flex", alignItems: "center", gap: 10,
              }}>
                <span style={{ color: "var(--warning-text)", fontSize: 12, fontWeight: 600, whiteSpace: "nowrap" }}>Pending your review</span>
                <span style={{ color: "var(--text-muted)", fontSize: 12 }}>
                  AI has scored and tiered candidates. Review the results, make any changes, then accept in the stage panel on the left.
                </span>
              </div>
            )}
            <div style={{ overflowY: "auto", flex: 1 }}>
            <table className="tbl matrix-tbl">
              <thead>
                <tr>
                  <th style={{ width: 36, textAlign: "center" }}>#</th>
                  <th>Candidate</th>
                  <th style={{ color: "var(--text-muted)", fontWeight: 400 }}>Email</th>
                  <th style={{ width: 60, textAlign: "center" }}>Tier</th>
                  <th style={{ width: 70, textAlign: "center" }}>Score</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((item, i) => {
                  if ("type" in item) {
                    return (
                      <tr key={`div-${i}`} className="tier-divider">
                        <td colSpan={5} className="tier-divider-cell">{item.label}</td>
                      </tr>
                    );
                  }
                  const row = item;
                  const isSelected = (candidateParam ?? ws?.selected_candidate_id) === row.candidate_id;
                  return (
                    <tr
                      key={row.candidate_id}
                      className={`clickable ${isSelected ? "row-selected" : ""}`}
                      onClick={() => selectCandidate(row.candidate_id)}
                    >
                      <td style={{ textAlign: "center", color: "var(--text-muted)" }}>{row.rank && row.rank < 900 ? row.rank : "—"}</td>
                      <td>
                        <span style={{ fontWeight: isSelected ? 600 : 400 }}>{row.candidate_name}</span>
                        {row.override_count > 0 && (
                          <span style={{ display: "inline-block", width: 6, height: 6, borderRadius: "50%", background: "var(--warning)", marginLeft: 6, verticalAlign: "middle" }} title={`${row.override_count} override${row.override_count !== 1 ? "s" : ""}`} />
                        )}
                      </td>
                      <td style={{ color: "var(--text-muted)", fontSize: 12 }}>{row.candidate_email || "—"}</td>
                      <td style={{ textAlign: "center" }}>
                        {tierChip(row.final_tier ?? row.proposed_tier ?? "")}
                      </td>
                      <td style={{ textAlign: "center", fontWeight: 600 }}>{row.stage_score || "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          </>
        )}
      </div>

      {/* Dossier — slide in as flex sibling so matrix stays visible */}
      <div style={{
        width: activeDossier ? 480 : 0,
        minWidth: 0,
        flexShrink: 0,
        overflow: "hidden",
        transition: "width 0.18s ease",
        borderLeft: activeDossier ? "1px solid var(--border)" : "none",
        background: "var(--bg-elevated)",
        display: "flex",
        flexDirection: "column",
      }}>
        {activeDossier && activeStageId && (
          <Dossier
            key={activeDossier.candidate_id}
            caseId={engagementId!}
            dossier={activeDossier}
            stageId={activeStageId}
            stageTemplateKey={ws?.active_stage?.template_key ?? null}
            stageConfig={ws?.active_stage?.config ?? {}}
            onClose={closeCandidate}
          />
        )}
      </div>
    </div>
  );
}
