import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { listExpertAgents, updateExpertAgent, type ExpertAgentRecord, type ExpertAgentUpdatePayload } from "../lib/api";

export function AgentConfigPage() {
  const qc = useQueryClient();
  const query = useQuery({ queryKey: ["expert-agents"], queryFn: listExpertAgents });
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<ExpertAgentUpdatePayload | null>(null);

  const saveMut = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: ExpertAgentUpdatePayload }) => updateExpertAgent(id, payload),
    onSuccess() { qc.invalidateQueries({ queryKey: ["expert-agents"] }); setEditingId(null); setEditForm(null); },
  });

  function startEdit(agent: ExpertAgentRecord) {
    setEditingId(agent.id);
    setEditForm({ display_name: agent.display_name, description: agent.description, enabled: agent.enabled, config: agent.config });
  }

  return (
    <div className="workspace">
      <div className="panel panel-flex" style={{ overflowY: "auto" }}>
        <div className="panel-head">
          <span className="panel-head-title">Agent Configuration</span>
        </div>
        <div className="admin-content">
          {(query.data ?? []).length === 0 && (
            <p className="loading-text">{query.isLoading ? "Loading…" : "No agents configured"}</p>
          )}
          {(query.data ?? []).map(agent => (
            <div key={agent.id} className="settings-section">
              <div className="settings-section-head" style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <span>{agent.display_name}</span>
                <span style={{ display: "flex", gap: 6 }}>
                  <span className={`chip ${agent.enabled ? "chip-success" : "chip-neutral"}`}>{agent.enabled ? "Enabled" : "Disabled"}</span>
                  <button className="btn btn-ghost btn-sm" onClick={() => startEdit(agent)}>Edit</button>
                </span>
              </div>

              {editingId === agent.id && editForm ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 10, paddingTop: 10 }}>
                  <div className="settings-row">
                    <span className="settings-key">Enabled</span>
                    <input type="checkbox" checked={editForm.enabled} onChange={e => setEditForm(f => f ? { ...f, enabled: e.target.checked } : f)} />
                  </div>
                  <div className="settings-row">
                    <span className="settings-key">Display Name</span>
                    <input className="input" style={{ maxWidth: 280 }} value={editForm.display_name} onChange={e => setEditForm(f => f ? { ...f, display_name: e.target.value } : f)} />
                  </div>
                  <div className="settings-row">
                    <span className="settings-key">Description</span>
                    <textarea className="textarea-input" style={{ minHeight: 60, maxWidth: 400 }} value={editForm.description} onChange={e => setEditForm(f => f ? { ...f, description: e.target.value } : f)} />
                  </div>
                  <div style={{ display: "flex", gap: 6 }}>
                    <button className="btn btn-primary btn-sm" disabled={saveMut.isPending} onClick={() => saveMut.mutate({ id: agent.id, payload: editForm })}>
                      {saveMut.isPending ? "Saving…" : "Save"}
                    </button>
                    <button className="btn btn-sm" onClick={() => { setEditingId(null); setEditForm(null); }}>Cancel</button>
                  </div>
                </div>
              ) : (
                <>
                  <div className="settings-row">
                    <span className="settings-key">Type</span>
                    <span className="settings-val" style={{ color: "var(--text-muted)" }}>{agent.agent_type}</span>
                  </div>
                  <div className="settings-row">
                    <span className="settings-key">Description</span>
                    <span className="settings-val" style={{ color: "var(--text-muted)" }}>{agent.description}</span>
                  </div>
                </>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
