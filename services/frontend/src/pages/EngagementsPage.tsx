import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { useCaseContext } from "../app/case-context";
import { createCase, deleteCase, listCases, type CaseCreatePayload } from "../lib/api";
import { formatLabel } from "../lib/format";

const GOVT_ACTIONS = new Set([
  "Merit Promotion", "Competitive Service", "Excepted Service",
  "Schedule A", "Senior Executive Service (SES)",
  "Direct Hire Authority", "Delegated Examining",
]);

const blank: CaseCreatePayload = {
  title: "",
  series: "",
  grade: "",
  organization: "",
  hiring_action_type: "",
  certificate_number: "",
  selecting_official: "",
  panel_members: [],
  data_sensitivity: "moderate",
  retention_settings: { policy: "default" },
  model_provider_settings: { provider: "ollama" },
  outside_enrichment_allowed: false,
};

function statusChip(status: string) {
  const s = status.toLowerCase();
  if (s === "review")   return <span className="chip chip-brand">{formatLabel(status)}</span>;
  if (s === "intake")   return <span className="chip chip-warning">{formatLabel(status)}</span>;
  if (s === "selection" || s === "closed") return <span className="chip chip-success">{formatLabel(status)}</span>;
  return <span className="chip chip-neutral">{formatLabel(status)}</span>;
}

export function EngagementsPage() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { setActiveCase } = useCaseContext();
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState(blank);

  const casesQuery = useQuery({ queryKey: ["cases"], queryFn: listCases });

  const createMut = useMutation({
    mutationFn: createCase,
    onSuccess(rec) {
      qc.invalidateQueries({ queryKey: ["cases"] });
      setActiveCase({ id: rec.id, title: rec.title });
      setShowCreate(false);
      setForm(blank);
      navigate(`/engagements/${rec.id}/prep`);
    },
  });

  const deleteMut = useMutation({
    mutationFn: deleteCase,
    onSuccess() { qc.invalidateQueries({ queryKey: ["cases"] }); },
  });

  function open(id: string, title: string, mode: "prep" | "review" | "decision") {
    setActiveCase({ id, title });
    navigate(`/engagements/${id}/${mode}`);
  }

  function handleDelete(id: string, title: string) {
    if (!window.confirm(`Delete "${title}" and all related data?`)) return;
    deleteMut.mutate(id);
  }

  function set<K extends keyof CaseCreatePayload>(k: K, v: CaseCreatePayload[K]) {
    setForm(f => ({ ...f, [k]: v }));
  }

  const cases = casesQuery.data ?? [];
  const isGovt = GOVT_ACTIONS.has(form.hiring_action_type ?? "");

  return (
    <div className="engagements-page">
      <div className="engagement-list-pane">
        <div className="engagement-list-head">
          <span className="panel-head-title">Engagements · {cases.length}</span>
          <button className="btn btn-primary btn-sm" onClick={() => setShowCreate(true)}>+ New</button>
        </div>
        <div className="tbl-wrap">
          <table className="tbl">
            <thead>
              <tr>
                <th>Title</th>
                <th>Status</th>
                <th>Job Family / Level</th>
                <th>Organization</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {cases.length === 0 && (
                <tr className="empty-row"><td colSpan={5}>No engagements — click + New to create the first</td></tr>
              )}
              {cases.map(c => (
                <tr key={c.id} className="clickable" onClick={() => open(c.id, c.title, "prep")}>
                  <td style={{ fontWeight: 600, maxWidth: 280 }}>{c.title}</td>
                  <td>{statusChip(c.status)}</td>
                  <td className="text-muted">—</td>
                  <td className="text-muted truncate" style={{ maxWidth: 160 }}>—</td>
                  <td onClick={e => e.stopPropagation()}>
                    <span style={{ display: "flex", gap: 4 }}>
                      <button className="btn btn-ghost btn-sm" onClick={() => open(c.id, c.title, "prep")}>Intake</button>
                      <button className="btn btn-ghost btn-sm" onClick={() => open(c.id, c.title, "review")}>Review</button>
                      <button className="btn btn-ghost btn-sm" onClick={() => open(c.id, c.title, "decision")}>Decision</button>
                      <button className="btn btn-danger btn-sm" onClick={() => handleDelete(c.id, c.title)}>✕</button>
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {showCreate && (
        <div className="slide-pane">
          <div className="slide-pane-head">
            <span className="panel-head-title">New Engagement</span>
            <button className="btn btn-ghost btn-sm" onClick={() => setShowCreate(false)}>✕</button>
          </div>
          <form
            className="form-section"
            onSubmit={e => { e.preventDefault(); createMut.mutate(form); }}
          >
            <div className="field">
              <span className="field-label">Title *</span>
              <input className="input" value={form.title} onChange={e => set("title", e.target.value)} placeholder="Director, Business Technology and Innovation" required />
            </div>
            <div className="field">
              <span className="field-label">Organization</span>
              <input className="input" value={form.organization ?? ""} onChange={e => set("organization", e.target.value)} placeholder="Office, bureau, or division" />
            </div>
            <div className="field">
              <span className="field-label">Hiring Action</span>
              <select className="select-input" value={form.hiring_action_type ?? ""} onChange={e => set("hiring_action_type", e.target.value)}>
                <option value="">— Select —</option>
                <optgroup label="New Position">
                  <option>External Open Recruitment</option>
                  <option>Targeted Hire</option>
                  <option>Executive / Leadership Search</option>
                  <option>Contract-to-Hire</option>
                  <option>Temporary / Seasonal</option>
                  <option>Part-Time / Flex</option>
                </optgroup>
                <optgroup label="Internal Movement">
                  <option>Internal Promotion</option>
                  <option>Lateral Transfer</option>
                  <option>Reassignment</option>
                  <option>Backfill / Replacement</option>
                  <option>Succession Planning</option>
                </optgroup>
                <optgroup label="Special Cases">
                  <option>Rehire / Alumni</option>
                  <option>Return from Leave</option>
                </optgroup>
                <optgroup label="Government / Civil Service">
                  <option>Merit Promotion</option>
                  <option>Competitive Service</option>
                  <option>Excepted Service</option>
                  <option>Schedule A</option>
                  <option>Senior Executive Service (SES)</option>
                  <option>Direct Hire Authority</option>
                  <option>Delegated Examining</option>
                </optgroup>
                <optgroup label="Other">
                  <option>Other</option>
                </optgroup>
              </select>
            </div>
            <div className="field">
              <span className="field-label">Selecting Official</span>
              <input className="input" value={form.selecting_official ?? ""} onChange={e => set("selecting_official", e.target.value)} />
            </div>
            <div className="field">
              <span className="field-label">{isGovt ? "Occupational Series" : "Job Family"}</span>
              <input className="input" value={form.series ?? ""} onChange={e => set("series", e.target.value)}
                placeholder={isGovt ? "e.g. 2210 (IT Management), 0301 (Misc Admin)" : "e.g. Engineering, Finance, IT, Human Resources"} />
            </div>
            <div className="field">
              <span className="field-label">{isGovt ? "Grade" : "Level / Band"}</span>
              <input className="input" value={form.grade ?? ""} onChange={e => set("grade", e.target.value)}
                placeholder={isGovt ? "e.g. GS-15, GS-14, SES" : "e.g. Senior, Director, L5, Band 4"} />
            </div>
            {createMut.isError && <p className="feedback-error">Could not create engagement — check required fields.</p>}
            <div style={{ display: "flex", gap: 8 }}>
              <button className="btn btn-primary" type="submit" disabled={createMut.isPending}>
                {createMut.isPending ? "Creating…" : "Create engagement"}
              </button>
              <button className="btn" type="button" onClick={() => setShowCreate(false)}>Cancel</button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
