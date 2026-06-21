import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { getAISettings, updateAISettings, type AISettingsRecord } from "../lib/api";

export function AISettingsPage() {
  const qc = useQueryClient();
  const query = useQuery({ queryKey: ["ai-settings"], queryFn: getAISettings });
  const [form, setForm] = useState<AISettingsRecord | null>(null);

  useEffect(() => { if (query.data) setForm(query.data); }, [query.data]);

  const saveMut = useMutation({
    mutationFn: (payload: AISettingsRecord) => updateAISettings(payload),
    onSuccess(data) { qc.setQueryData(["ai-settings"], data); setForm(data); },
  });

  if (!form) return <div className="workspace"><p className="loading-text">{query.isLoading ? "Loading…" : "Failed to load AI settings"}</p></div>;

  return (
    <div className="workspace">
      <div className="panel panel-flex" style={{ overflowY: "auto" }}>
        <div className="panel-head">
          <span className="panel-head-title">AI Settings</span>
          <button className="btn btn-primary btn-sm" disabled={saveMut.isPending} onClick={() => saveMut.mutate(form)}>
            {saveMut.isPending ? "Saving…" : "Save"}
          </button>
        </div>
        <div className="admin-content">
          <div className="settings-section">
            <div className="settings-section-head">Default Provider</div>
            <div className="settings-row">
              <span className="settings-key">Active Provider</span>
              <select
                className="select-input"
                style={{ maxWidth: 200 }}
                value={form.default_provider}
                onChange={e => setForm(f => f ? { ...f, default_provider: e.target.value } : f)}
              >
                {Object.keys(form.providers).map(p => (
                  <option key={p} value={p}>{p}</option>
                ))}
              </select>
            </div>
          </div>

          {Object.entries(form.providers).map(([providerKey, config]) => (
            <div key={providerKey} className="settings-section">
              <div className="settings-section-head">{providerKey}</div>
              <div className="settings-row">
                <span className="settings-key">Enabled</span>
                <input
                  type="checkbox"
                  checked={config.enabled}
                  onChange={e => setForm(f => f ? { ...f, providers: { ...f.providers, [providerKey]: { ...config, enabled: e.target.checked } } } : f)}
                />
              </div>
              <div className="settings-row">
                <span className="settings-key">Label</span>
                <span className="settings-val">{config.label}</span>
              </div>
              <div className="settings-row">
                <span className="settings-key">Base URL</span>
                <input
                  className="input"
                  style={{ maxWidth: 320 }}
                  value={config.base_url}
                  onChange={e => setForm(f => f ? { ...f, providers: { ...f.providers, [providerKey]: { ...config, base_url: e.target.value } } } : f)}
                />
              </div>
              <div className="settings-row">
                <span className="settings-key">Default Model</span>
                <input
                  className="input"
                  style={{ maxWidth: 240 }}
                  value={config.default_model}
                  onChange={e => setForm(f => f ? { ...f, providers: { ...f.providers, [providerKey]: { ...config, default_model: e.target.value } } } : f)}
                />
              </div>
              <div className="settings-row">
                <span className="settings-key">API Key Env Var</span>
                <span className="settings-val" style={{ color: "var(--text-muted)" }}>{config.api_key_env_var}</span>
              </div>
              {config.notes && (
                <div className="settings-row">
                  <span className="settings-key">Notes</span>
                  <span className="settings-val" style={{ color: "var(--text-muted)" }}>{config.notes}</span>
                </div>
              )}
            </div>
          ))}

          {saveMut.isError && <p className="feedback-error">Save failed.</p>}
          {saveMut.isSuccess && <p className="feedback-success">Saved.</p>}
        </div>
      </div>
    </div>
  );
}
