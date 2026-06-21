import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";

import {
  addWorkflowStage,
  createRubricFromAnalysis,
  getPositionAnalysis,
  getPrepWorkspace,
  listRubrics,
  replaceWorkflowPlan,
  runCandidateReconciliation,
  runPositionAnalysis,
  runWorkflowStage,
  setRubricLock,
  updateRubric,
  updateWorkflowStage,
  uploadDocumentBinary,
  type RubricDimensionInput,
  type WorkflowStageInput,
} from "../lib/api";

type RubricDraft = { name: string; isLocked: boolean; dimensions: RubricDimensionInput[] };

function mkDim(d: Record<string, unknown>, idx: number): RubricDimensionInput {
  return {
    title: String(d.title ?? "Untitled"),
    description: String(d.description ?? d.pd_rationale ?? ""),
    weight: Number(d.weight ?? 1),
    order_index: idx + 1,
    evidence_links: Array.isArray(d.evidence_links) ? d.evidence_links : [],
  };
}

function invalidate(qc: ReturnType<typeof useQueryClient>, id: string | undefined) {
  if (!id) return;
  qc.invalidateQueries({ queryKey: ["prep-workspace", id] });
  qc.invalidateQueries({ queryKey: ["review-workspace", id] });
}

export function EngagementPrepPage() {
  const { engagementId } = useParams<{ engagementId: string }>();
  const qc = useQueryClient();

  const [pdFile, setPdFile] = useState<File | null>(null);
  const [resumeFile, setResumeFile] = useState<File | null>(null);
  const [supportingFile, setSupportingFile] = useState<File | null>(null);
  const [supportingType, setSupportingType] = useState("certificate");
  const [stageDrafts, setStageDrafts] = useState<WorkflowStageInput[]>([]);
  const [newStageTemplate, setNewStageTemplate] = useState("narrative_request");
  const [tierAThreshold, setTierAThreshold] = useState("82");
  const [tierBThreshold, setTierBThreshold] = useState("68");
  const [rubricDraft, setRubricDraft] = useState<RubricDraft | null>(null);
  const [editingDimIdx, setEditingDimIdx] = useState<number | null>(null);

  const wsQuery = useQuery({ queryKey: ["prep-workspace", engagementId], queryFn: () => getPrepWorkspace(engagementId!), enabled: Boolean(engagementId) });
  const analysisQuery = useQuery({ queryKey: ["position-analysis", engagementId], queryFn: () => getPositionAnalysis(engagementId!), enabled: Boolean(engagementId), retry: false });
  const rubricsQuery = useQuery({ queryKey: ["rubrics", engagementId], queryFn: () => listRubrics(engagementId!), enabled: Boolean(engagementId) });

  const activeRubric = rubricsQuery.data?.[0] ?? null;

  useEffect(() => {
    if (!wsQuery.data) return;
    setStageDrafts(wsQuery.data.stages.map(s => ({ template_key: s.template_key, name: s.name, description: s.description, workspace: s.workspace, order_index: s.order_index, enabled: s.enabled, config: s.config, guidance: s.guidance })));
    if (wsQuery.data.templates.length && !wsQuery.data.templates.some(t => t.key === newStageTemplate)) {
      setNewStageTemplate(wsQuery.data.templates[0].key);
    }
    const rrStage = wsQuery.data.stages.find(s => s.template_key === "resume_review");
    if (rrStage?.config) {
      if (rrStage.config.tier_a_threshold != null) setTierAThreshold(String(rrStage.config.tier_a_threshold));
      if (rrStage.config.tier_b_threshold != null) setTierBThreshold(String(rrStage.config.tier_b_threshold));
    }
  }, [wsQuery.data]);

  useEffect(() => {
    if (activeRubric) {
      setRubricDraft({ name: activeRubric.name, isLocked: activeRubric.is_locked, dimensions: activeRubric.dimensions.map((d, i) => ({ title: d.title, description: d.description, weight: Number(d.weight), order_index: d.order_index, evidence_links: d.evidence_links })) });
      return;
    }
    const rec = analysisQuery.data?.recommended_dimensions;
    if (rec?.length) {
      setRubricDraft({ name: "PD-based scoring model", isLocked: false, dimensions: rec.map((d, i) => mkDim(d as Record<string, unknown>, i)) });
    }
  }, [activeRubric, analysisQuery.data?.recommended_dimensions]);

  const uploadMut = useMutation({
    mutationFn: ({ file, documentType }: { file: File; documentType: string }) =>
      uploadDocumentBinary(engagementId!, { file, documentType, metadataSource: "prep-workspace" }),
    onSuccess(_, v) {
      if (v.documentType === "position_description") setPdFile(null);
      else if (v.documentType === "resume_bundle") setResumeFile(null);
      else setSupportingFile(null);
      invalidate(qc, engagementId);
    },
  });

  const savePlanMut = useMutation({
    mutationFn: () => replaceWorkflowPlan(engagementId!, { stages: stageDrafts }),
    onSuccess() { invalidate(qc, engagementId); },
  });

  const addStageMut = useMutation({
    mutationFn: () => {
      const tmpl = wsQuery.data?.templates.find(t => t.key === newStageTemplate);
      return addWorkflowStage(engagementId!, { template_key: newStageTemplate, name: tmpl?.name ?? "Custom Stage", description: tmpl?.description ?? "", workspace: tmpl?.default_workspace ?? "review", order_index: stageDrafts.length + 1, enabled: true, config: tmpl?.default_config ?? {} });
    },
    onSuccess() { qc.invalidateQueries({ queryKey: ["prep-workspace", engagementId] }); },
  });

  const saveThresholdsMut = useMutation({
    mutationFn: async () => {
      const stage = wsQuery.data?.stages.find(s => s.template_key === "resume_review");
      if (!stage) throw new Error("Resume review stage not found");
      const a = parseFloat(tierAThreshold);
      const b = parseFloat(tierBThreshold);
      if (isNaN(a) || isNaN(b) || b >= a) throw new Error("Invalid thresholds: Tier A must be > Tier B");
      return updateWorkflowStage(engagementId!, stage.id, { config: { ...(stage.config ?? {}), tier_a_threshold: a, tier_b_threshold: b } });
    },
    onSuccess() { invalidate(qc, engagementId); },
  });

  const runReviewMut = useMutation({
    mutationFn: async () => {
      const stage = wsQuery.data?.stages.find(s => s.template_key === "resume_review");
      if (!stage) throw new Error("Resume review stage not configured");
      return runWorkflowStage(engagementId!, stage.id);
    },
    onSuccess() { invalidate(qc, engagementId); },
  });

  const runMatchMut = useMutation({ mutationFn: () => runCandidateReconciliation(engagementId!), onSuccess() { invalidate(qc, engagementId); } });
  const runAnalysisMut = useMutation({ mutationFn: () => runPositionAnalysis(engagementId!), onSuccess() { qc.invalidateQueries({ queryKey: ["position-analysis", engagementId] }); invalidate(qc, engagementId); } });
  const createRubricMut = useMutation({ mutationFn: () => createRubricFromAnalysis(engagementId!), onSuccess() { qc.invalidateQueries({ queryKey: ["rubrics", engagementId] }); invalidate(qc, engagementId); } });

  const saveRubricMut = useMutation({
    mutationFn: () => {
      if (!activeRubric || !rubricDraft) throw new Error("No rubric");
      return updateRubric(engagementId!, activeRubric.id, { name: rubricDraft.name, status: rubricDraft.isLocked ? "locked" : "draft", is_locked: rubricDraft.isLocked, dimensions: rubricDraft.dimensions.map((d, i) => ({ ...d, order_index: i + 1 })) });
    },
    onSuccess() { qc.invalidateQueries({ queryKey: ["rubrics", engagementId] }); invalidate(qc, engagementId); },
  });

  const lockRubricMut = useMutation({
    mutationFn: () => {
      if (!activeRubric || !rubricDraft) throw new Error("No rubric");
      return setRubricLock(engagementId!, activeRubric.id, !rubricDraft.isLocked);
    },
    onSuccess(data) {
      qc.invalidateQueries({ queryKey: ["rubrics", engagementId] });
      setRubricDraft({ name: data.name, isLocked: data.is_locked, dimensions: data.dimensions.map((d, i) => ({ title: d.title, description: d.description, weight: Number(d.weight), order_index: d.order_index, evidence_links: d.evidence_links })) });
    },
  });

  const ws = wsQuery.data;
  const hasPd = (ws?.document_summary.position_descriptions ?? 0) > 0;
  const hasResumes = (ws?.document_summary.resume_files ?? 0) > 0;
  const hasMatched = (ws?.matching_summary.candidate_count ?? 0) > 0;
  const hasDuplicates = (ws?.matching_summary.duplicate_count ?? 0) > 0;
  const hasRubric = Boolean(rubricDraft?.dimensions.length);
  const canLaunch = hasPd && hasResumes && hasMatched && hasRubric && !hasDuplicates;

  const totalWeight = rubricDraft?.dimensions.reduce((s, d) => s + Number(d.weight), 0) ?? 0;
  const maxComposite = totalWeight * 3;

  const checkItems = [
    { key: "pd",    label: "PD uploaded",    ok: hasPd },
    { key: "res",   label: "Resumes uploaded", ok: hasResumes },
    { key: "parse", label: "Parsed",          ok: (ws?.document_summary.ready_documents ?? 0) > 0 },
    { key: "match", label: "Reconciled",      ok: hasMatched && !hasDuplicates },
    { key: "rub",   label: "Rubric exists",   ok: hasRubric },
    { key: "ready", label: "Ready to launch", ok: canLaunch },
  ];

  function updateDim(idx: number, field: keyof RubricDimensionInput, val: string | number) {
    setRubricDraft(d => d ? { ...d, dimensions: d.dimensions.map((dim, i) => i === idx ? { ...dim, [field]: field === "weight" ? Number(val) : val } : dim) } : d);
  }

  function removeDim(idx: number) {
    setRubricDraft(d => d ? { ...d, dimensions: d.dimensions.filter((_, i) => i !== idx) } : d);
  }

  function addDim() {
    setRubricDraft(d => d ? { ...d, dimensions: [...d.dimensions, { title: "New Dimension", description: "", weight: 1, order_index: d.dimensions.length + 1, evidence_links: [] }] } : d);
  }

  function toggleStage(idx: number) {
    setStageDrafts(s => s.map((stage, i) => i === idx ? { ...stage, enabled: !stage.enabled } : stage));
  }

  if (!engagementId) return <div className="error-state">No engagement selected.</div>;

  return (
    <div className="workspace">
      {/* Left: Checklist + exceptions */}
      <div className="panel panel-220">
        <div className="panel-head">
          <span className="panel-head-title">Intake Checklist</span>
        </div>
        <div className="checklist">
          {checkItems.map(c => (
            <div key={c.key} className={`checklist-item ${c.ok ? "ok" : "warn"}`}>
              <span className="check-icon">{c.ok ? "✓" : "○"}</span>
              <span>{c.label}</span>
            </div>
          ))}
        </div>

        {(ws?.issues?.length ?? 0) > 0 && (
          <>
            <div className="section-divider">Exceptions</div>
            <div className="issue-list">
              {ws!.issues.map((iss, i) => (
                <div key={i} className="issue-row">
                  <span className={`status-dot ${iss.severity === "error" ? "red" : "amber"}`} />
                  <div>
                    <div className="issue-label">{iss.title}</div>
                    <div className="issue-detail">{iss.detail}</div>
                  </div>
                </div>
              ))}
            </div>
          </>
        )}
      </div>

      {/* Center: Documents + rubric */}
      <div className="panel panel-flex" style={{ display: "flex", flexDirection: "column", overflow: "hidden" }}>
        <div className="panel-head">
          <span className="panel-head-title">Materials &amp; Scoring Model</span>
          <span className="text-muted text-sm">{ws?.case_title ?? "—"}</span>
        </div>

        {/* Metrics */}
        {ws && (
          <div className="metrics-bar">
            <span className="metric-item">Docs <span className="metric-val">{ws.document_summary.total_documents ?? 0}</span></span>
            <span className="metric-item">Ready <span className="metric-val">{ws.document_summary.ready_documents ?? 0}</span></span>
            <span className="metric-item">Candidates <span className="metric-val">{ws.matching_summary.candidate_count ?? 0}</span></span>
            <span className="metric-item">Unmatched <span className="metric-val">{ws.matching_summary.unmatched_segment_count ?? 0}</span></span>
          </div>
        )}

        {/* Upload rows */}
        <div style={{ overflowY: "auto", flex: 1 }}>
          <div className="section-divider">Documents</div>

          {/* PD */}
          <div className="upload-row">
            <span className={`status-dot ${hasPd ? "green" : "gray"}`} />
            <span className="upload-row-name">
              {hasPd ? "Position description uploaded" : pdFile ? pdFile.name : "No position description"}
            </span>
            {hasPd && <span className="upload-row-meta chip chip-success">✓</span>}
            {!hasPd && (
              <>
                <label className="upload-label" htmlFor="pd-upload">
                  {pdFile ? "Ready" : "Choose file"}
                </label>
                <input id="pd-upload" className="upload-input" type="file" accept=".pdf,.docx,.doc" onChange={e => setPdFile(e.target.files?.[0] ?? null)} />
                {pdFile && (
                  <button className="btn btn-primary btn-sm" disabled={uploadMut.isPending} onClick={() => uploadMut.mutate({ file: pdFile, documentType: "position_description" })}>
                    {uploadMut.isPending ? "Uploading…" : "Upload PD"}
                  </button>
                )}
              </>
            )}
          </div>

          {/* Resumes */}
          <div className="upload-row">
            <span className={`status-dot ${hasResumes ? "green" : "gray"}`} />
            <span className="upload-row-name">
              {hasResumes ? `Resume bundle uploaded (${ws?.document_summary.resume_files ?? 0} file${(ws?.document_summary.resume_files ?? 0) !== 1 ? "s" : ""})` : resumeFile ? resumeFile.name : "No resume bundle"}
            </span>
            <label className="upload-label" htmlFor="res-upload">{resumeFile ? "Ready" : hasResumes ? "Replace" : "Choose file"}</label>
            <input id="res-upload" className="upload-input" type="file" accept=".pdf,.zip" onChange={e => setResumeFile(e.target.files?.[0] ?? null)} />
            {resumeFile && (
              <button className="btn btn-primary btn-sm" disabled={uploadMut.isPending} onClick={() => uploadMut.mutate({ file: resumeFile, documentType: "resume_bundle" })}>
                {uploadMut.isPending ? "Uploading…" : "Upload"}
              </button>
            )}
          </div>

          {/* Supporting */}
          <div className="upload-row">
            <span className="status-dot gray" />
            <span className="upload-row-name">{supportingFile ? supportingFile.name : "Supporting files (optional)"}</span>
            <select className="select-input" style={{ width: 170, height: 30 }} value={supportingType} onChange={e => setSupportingType(e.target.value)}>
              <option value="certificate">Certificate</option>
              <option value="vacancy_announcement">Vacancy Announcement</option>
              <option value="transcript">Transcript</option>
              <option value="interview_notes">Interview Notes</option>
              <option value="other">Other</option>
            </select>
            <label className="upload-label" htmlFor="supp-upload">{supportingFile ? "Ready" : "Choose"}</label>
            <input id="supp-upload" className="upload-input" type="file" onChange={e => setSupportingFile(e.target.files?.[0] ?? null)} />
            {supportingFile && (
              <button className="btn btn-primary btn-sm" disabled={uploadMut.isPending} onClick={() => uploadMut.mutate({ file: supportingFile, documentType: supportingType })}>
                Upload
              </button>
            )}
          </div>

          {/* Action row for matching + analysis */}
          <div className="action-row action-row-border">
            {hasPd && (
              <button className="btn btn-sm" disabled={runAnalysisMut.isPending} onClick={() => runAnalysisMut.mutate()}>
                {runAnalysisMut.isPending ? "Analyzing…" : "Run PD analysis"}
              </button>
            )}
            {hasResumes && (
              <button className="btn btn-sm" disabled={runMatchMut.isPending} onClick={() => runMatchMut.mutate()}>
                {runMatchMut.isPending ? "Matching…" : "Run reconciliation"}
              </button>
            )}
            {analysisQuery.data && !activeRubric && (
              <button className="btn btn-primary btn-sm" disabled={createRubricMut.isPending} onClick={() => createRubricMut.mutate()}>
                {createRubricMut.isPending ? "Generating…" : "Generate rubric from PD"}
              </button>
            )}
          </div>

          {/* Rubric */}
          <div className="section-divider">
            Scoring Model
            {rubricDraft && (
              <span style={{ marginLeft: 8, fontWeight: 400, color: "var(--text-muted)" }}>
                {rubricDraft.dimensions.length} dimensions · wt {totalWeight} · max {maxComposite}
                {rubricDraft.isLocked && <span className="chip chip-neutral" style={{ marginLeft: 8 }}>Locked</span>}
              </span>
            )}
          </div>

          {rubricDraft ? (
            <>
              <table className="rubric-tbl">
                <thead>
                  <tr>
                    <th className="col-dim">Dimension</th>
                    <th className="col-wt">Wt</th>
                    <th className="col-max">Max</th>
                    <th className="col-rat">PD Rationale</th>
                    <th className="col-act">—</th>
                  </tr>
                </thead>
                <tbody>
                  {rubricDraft.dimensions.map((dim, i) => (
                    <tr key={i} className={editingDimIdx === i ? "editing" : ""}>
                      <td>
                        {editingDimIdx === i ? (
                          <input className="input" value={dim.title} onChange={e => updateDim(i, "title", e.target.value)} style={{ height: 30 }} />
                        ) : (
                          <span>{dim.title}</span>
                        )}
                      </td>
                      <td className="col-wt">
                        {editingDimIdx === i ? (
                          <input className="input" type="number" min={1} max={5} value={dim.weight} onChange={e => updateDim(i, "weight", e.target.value)} style={{ height: 30, textAlign: "center" }} />
                        ) : (
                          <span>×{dim.weight}</span>
                        )}
                      </td>
                      <td className="col-max" style={{ textAlign: "center", color: "var(--text-muted)" }}>{Number(dim.weight) * 3}</td>
                      <td className="col-rat">
                        {editingDimIdx === i ? (
                          <textarea className="textarea-input" value={dim.description} onChange={e => updateDim(i, "description", e.target.value)} style={{ minHeight: 60 }} />
                        ) : (
                          <span className="rubric-rat-text">{dim.description || "—"}</span>
                        )}
                      </td>
                      <td className="col-act" style={{ textAlign: "right" }}>
                        {!rubricDraft.isLocked && (
                          <>
                            <button className="btn btn-ghost btn-sm" onClick={() => setEditingDimIdx(editingDimIdx === i ? null : i)}>
                              {editingDimIdx === i ? "Done" : "✎"}
                            </button>
                            <button className="btn btn-ghost btn-sm" onClick={() => removeDim(i)} style={{ color: "var(--danger-text)" }}>✕</button>
                          </>
                        )}
                      </td>
                    </tr>
                  ))}
                  <tr>
                    <td style={{ fontWeight: 600 }}>Total</td>
                    <td style={{ textAlign: "center", fontWeight: 700, color: "var(--text)" }}>×{totalWeight}</td>
                    <td style={{ textAlign: "center", fontWeight: 700, color: "var(--text)" }}>{maxComposite}</td>
                    <td colSpan={2} />
                  </tr>
                </tbody>
              </table>
              {!rubricDraft.isLocked && (
                <div className="action-row action-row-border">
                  <button className="btn btn-sm" onClick={addDim}>+ Add dimension</button>
                  <button className="btn btn-primary btn-sm" disabled={saveRubricMut.isPending} onClick={() => saveRubricMut.mutate()}>
                    {saveRubricMut.isPending ? "Saving…" : "Save"}
                  </button>
                  <button className="btn btn-sm" disabled={lockRubricMut.isPending} onClick={() => lockRubricMut.mutate()}>
                    Lock model
                  </button>
                </div>
              )}
              {rubricDraft.isLocked && (
                <div className="action-row action-row-border">
                  <button className="btn btn-sm" disabled={lockRubricMut.isPending} onClick={() => lockRubricMut.mutate()}>Unlock model</button>
                </div>
              )}
            </>
          ) : (
            <p className="loading-text">{hasPd ? "Run PD analysis to generate dimensions" : "Upload a position description first"}</p>
          )}
        </div>
      </div>

      {/* Right: Stage plan + launch */}
      <div className="panel panel-260" style={{ overflow: "hidden" }}>
        <div className="panel-head">
          <span className="panel-head-title">Stage Plan</span>
        </div>

        <div style={{ overflowY: "auto", flex: 1 }}>
          {stageDrafts.length === 0 ? (
            <p className="loading-text">No stages configured</p>
          ) : (
            <div className="stage-rail">
              {stageDrafts.map((stage, i) => (
                <div key={i} className="stage-item" style={{ cursor: "default" }}>
                  <span className="stage-num">{stage.order_index}</span>
                  <span className="stage-name">{stage.name}</span>
                  <button
                    className={`toggle-btn ${stage.enabled ? "on" : ""}`}
                    onClick={() => toggleStage(i)}
                    title={stage.enabled ? "Enabled" : "Disabled"}
                  />
                </div>
              ))}
            </div>
          )}

          {wsQuery.data?.stages.some(s => s.template_key === "resume_review") && (
            <div style={{ padding: "8px 12px", borderTop: "1px solid var(--border)" }}>
              <div className="section-divider" style={{ marginBottom: 6 }}>Tier Thresholds</div>
              <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 6 }}>
                <div style={{ flex: 1 }}>
                  <div className="field-label" style={{ marginBottom: 2 }}>Tier A ≥</div>
                  <input className="input" type="number" min={1} max={100} step={0.5} value={tierAThreshold} onChange={e => setTierAThreshold(e.target.value)} style={{ width: "100%" }} />
                </div>
                <div style={{ flex: 1 }}>
                  <div className="field-label" style={{ marginBottom: 2 }}>Tier B ≥</div>
                  <input className="input" type="number" min={1} max={100} step={0.5} value={tierBThreshold} onChange={e => setTierBThreshold(e.target.value)} style={{ width: "100%" }} />
                </div>
              </div>
              <button className="btn btn-sm" style={{ width: "100%" }} disabled={saveThresholdsMut.isPending} onClick={() => saveThresholdsMut.mutate()}>
                {saveThresholdsMut.isPending ? "Saving…" : "Save thresholds"}
              </button>
              {saveThresholdsMut.isError && <p className="feedback-error" style={{ marginTop: 4 }}>{String((saveThresholdsMut.error as Error)?.message ?? "Save failed")}</p>}
              {saveThresholdsMut.isSuccess && <p className="feedback-success" style={{ marginTop: 4 }}>Thresholds saved.</p>}
            </div>
          )}

          {wsQuery.data?.templates && wsQuery.data.templates.length > 0 && (
            <div className="action-row action-row-border">
              <select className="select-input" style={{ flex: 1, height: 28 }} value={newStageTemplate} onChange={e => setNewStageTemplate(e.target.value)}>
                {wsQuery.data.templates.map(t => (
                  <option key={t.key} value={t.key}>{t.name}</option>
                ))}
              </select>
              <button className="btn btn-sm" disabled={addStageMut.isPending} onClick={() => addStageMut.mutate()}>
                + Add
              </button>
            </div>
          )}

          {stageDrafts.length > 0 && (
            <div className="action-row">
              <button className="btn btn-sm" disabled={savePlanMut.isPending} onClick={() => savePlanMut.mutate()}>
                {savePlanMut.isPending ? "Saving…" : "Save stage plan"}
              </button>
            </div>
          )}
        </div>

        {/* Readiness strip + launch */}
        <div style={{ borderTop: "1px solid var(--border)", padding: "10px 12px", display: "flex", flexDirection: "column", gap: 8, flexShrink: 0 }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 4 }}>
            {[["PD", hasPd], ["Resumes", hasResumes], ["Matching", hasMatched], ["Rubric", hasRubric]].map(([label, ok]) => (
              <div key={String(label)} style={{ display: "flex", alignItems: "center", gap: 5 }}>
                <span className={`status-dot ${ok ? "green" : "gray"}`} />
                <span style={{ color: ok ? "var(--text)" : "var(--text-dim)" }}>{label}</span>
              </div>
            ))}
          </div>
          <button
            className={`btn btn-lg ${canLaunch ? "btn-primary" : ""}`}
            style={{ width: "100%" }}
            disabled={!canLaunch || runReviewMut.isPending}
            onClick={() => runReviewMut.mutate()}
          >
            {runReviewMut.isPending ? "Launching…" : "Launch resume review"}
          </button>
          {runReviewMut.isError && <p className="feedback-error">Launch failed — check logs.</p>}
          {runReviewMut.isSuccess && <p className="feedback-success">Resume review started.</p>}
        </div>
      </div>
    </div>
  );
}
