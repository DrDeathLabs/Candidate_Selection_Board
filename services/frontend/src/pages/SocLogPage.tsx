import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { listGlobalAuditEvents, type GlobalAuditQueryParams } from "../lib/api";

const EVENT_TYPES = [
  "login", "login_failed", "logout", "account_locked", "password_changed", "mfa_enrolled",
  "case_created", "case_updated", "file_upload", "admin_setting_change", "data_export",
  "audit_export", "candidate_override", "score_override",
];

const PAGE_SIZE = 100;

function rowBg(eventType: string): string {
  if (eventType === "login_failed" || eventType === "account_locked") return "rgba(229,62,62,0.07)";
  if (eventType === "login" || eventType === "logout" || eventType === "mfa_enrolled" || eventType === "password_changed") return "rgba(49,130,206,0.06)";
  return "transparent";
}

export function SocLogPage() {
  const [page, setPage] = useState(0);
  const [filters, setFilters] = useState<GlobalAuditQueryParams>({});
  const [draft, setDraft] = useState({ event_type: "", actor_id: "", source_ip: "", start_date: "", end_date: "" });

  const { data, isLoading, isError } = useQuery({
    queryKey: ["soc-log", filters, page],
    queryFn: () => listGlobalAuditEvents({ ...filters, limit: PAGE_SIZE, offset: page * PAGE_SIZE }),
  });

  const total = data?.total ?? 0;
  const events = data?.data ?? [];
  const start = page * PAGE_SIZE + 1;
  const end = Math.min(page * PAGE_SIZE + events.length, total);

  function applyFilters() {
    const f: GlobalAuditQueryParams = {};
    if (draft.event_type) f.event_type = draft.event_type;
    if (draft.actor_id) f.actor_id = draft.actor_id;
    if (draft.source_ip) f.source_ip = draft.source_ip;
    if (draft.start_date) f.start_date = draft.start_date;
    if (draft.end_date) f.end_date = draft.end_date;
    setFilters(f);
    setPage(0);
  }

  function clearFilters() {
    setDraft({ event_type: "", actor_id: "", source_ip: "", start_date: "", end_date: "" });
    setFilters({});
    setPage(0);
  }

  return (
    <div style={{ padding: "20px 24px", maxWidth: 1400 }}>
      <div style={{ marginBottom: 16 }}>
        <h2 style={{ margin: 0, fontSize: 18, fontWeight: 600 }}>SOC Audit Log</h2>
        <p style={{ margin: "4px 0 0", fontSize: 12, color: "var(--text-dim)" }}>
          Global cross-case audit log including all authentication events. Immutable.
        </p>
      </div>

      {/* Filter bar */}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "flex-end", marginBottom: 14, padding: "10px 12px", background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 6 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
          <label style={{ fontSize: 10, color: "var(--text-dim)", textTransform: "uppercase", letterSpacing: "0.05em" }}>Event Type</label>
          <select
            value={draft.event_type}
            onChange={e => setDraft(d => ({ ...d, event_type: e.target.value }))}
            style={{ fontSize: 12, padding: "3px 6px", background: "var(--input-bg)", border: "1px solid var(--border)", borderRadius: 4, color: "var(--text)", minWidth: 160 }}
          >
            <option value="">All</option>
            {EVENT_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
          </select>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
          <label style={{ fontSize: 10, color: "var(--text-dim)", textTransform: "uppercase", letterSpacing: "0.05em" }}>Actor ID</label>
          <input
            value={draft.actor_id}
            onChange={e => setDraft(d => ({ ...d, actor_id: e.target.value }))}
            placeholder="username or user-id"
            style={{ fontSize: 12, padding: "3px 6px", background: "var(--input-bg)", border: "1px solid var(--border)", borderRadius: 4, color: "var(--text)", width: 160 }}
          />
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
          <label style={{ fontSize: 10, color: "var(--text-dim)", textTransform: "uppercase", letterSpacing: "0.05em" }}>Source IP</label>
          <input
            value={draft.source_ip}
            onChange={e => setDraft(d => ({ ...d, source_ip: e.target.value }))}
            placeholder="x.x.x.x"
            style={{ fontSize: 12, padding: "3px 6px", background: "var(--input-bg)", border: "1px solid var(--border)", borderRadius: 4, color: "var(--text)", width: 120 }}
          />
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
          <label style={{ fontSize: 10, color: "var(--text-dim)", textTransform: "uppercase", letterSpacing: "0.05em" }}>From</label>
          <input
            type="datetime-local"
            value={draft.start_date}
            onChange={e => setDraft(d => ({ ...d, start_date: e.target.value }))}
            style={{ fontSize: 12, padding: "3px 6px", background: "var(--input-bg)", border: "1px solid var(--border)", borderRadius: 4, color: "var(--text)" }}
          />
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
          <label style={{ fontSize: 10, color: "var(--text-dim)", textTransform: "uppercase", letterSpacing: "0.05em" }}>To</label>
          <input
            type="datetime-local"
            value={draft.end_date}
            onChange={e => setDraft(d => ({ ...d, end_date: e.target.value }))}
            style={{ fontSize: 12, padding: "3px 6px", background: "var(--input-bg)", border: "1px solid var(--border)", borderRadius: 4, color: "var(--text)" }}
          />
        </div>
        <div style={{ display: "flex", gap: 6, alignItems: "flex-end", paddingBottom: 1 }}>
          <button onClick={applyFilters} style={{ fontSize: 12, padding: "4px 14px", background: "var(--accent)", border: "none", borderRadius: 4, color: "#fff", cursor: "pointer", fontWeight: 500 }}>
            Apply
          </button>
          <button onClick={clearFilters} style={{ fontSize: 12, padding: "4px 10px", background: "transparent", border: "1px solid var(--border)", borderRadius: 4, color: "var(--text-dim)", cursor: "pointer" }}>
            Clear
          </button>
        </div>
      </div>

      {/* Pagination header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
        <span style={{ fontSize: 12, color: "var(--text-dim)" }}>
          {isLoading ? "Loading…" : isError ? "Error loading events" : total === 0 ? "No events" : `${start}–${end} of ${total.toLocaleString()}`}
        </span>
        <div style={{ display: "flex", gap: 6 }}>
          <button
            onClick={() => setPage(p => Math.max(0, p - 1))}
            disabled={page === 0}
            style={{ fontSize: 11, padding: "3px 10px", background: "transparent", border: "1px solid var(--border)", borderRadius: 4, color: "var(--text-dim)", cursor: page === 0 ? "default" : "pointer", opacity: page === 0 ? 0.4 : 1 }}
          >← Prev</button>
          <button
            onClick={() => setPage(p => p + 1)}
            disabled={end >= total}
            style={{ fontSize: 11, padding: "3px 10px", background: "transparent", border: "1px solid var(--border)", borderRadius: 4, color: "var(--text-dim)", cursor: end >= total ? "default" : "pointer", opacity: end >= total ? 0.4 : 1 }}
          >Next →</button>
        </div>
      </div>

      {/* Table */}
      <div style={{ overflowX: "auto" }}>
        <table className="tbl" style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
          <thead>
            <tr style={{ background: "var(--surface)", borderBottom: "2px solid var(--border)" }}>
              <th style={{ padding: "6px 8px", textAlign: "left", fontWeight: 600, whiteSpace: "nowrap", color: "var(--text-dim)" }}>Time</th>
              <th style={{ padding: "6px 8px", textAlign: "left", fontWeight: 600, whiteSpace: "nowrap", color: "var(--text-dim)" }}>Event Type</th>
              <th style={{ padding: "6px 8px", textAlign: "left", fontWeight: 600, color: "var(--text-dim)" }}>Actor</th>
              <th style={{ padding: "6px 8px", textAlign: "left", fontWeight: 600, color: "var(--text-dim)" }}>Source IP</th>
              <th style={{ padding: "6px 8px", textAlign: "left", fontWeight: 600, color: "var(--text-dim)" }}>Session</th>
              <th style={{ padding: "6px 8px", textAlign: "left", fontWeight: 600, color: "var(--text-dim)" }}>Entity</th>
              <th style={{ padding: "6px 8px", textAlign: "left", fontWeight: 600, color: "var(--text-dim)" }}>Entity ID</th>
              <th style={{ padding: "6px 8px", textAlign: "left", fontWeight: 600, color: "var(--text-dim)" }}>Details</th>
              <th style={{ padding: "6px 8px", textAlign: "left", fontWeight: 600, color: "var(--text-dim)" }}>Hash</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr><td colSpan={9} style={{ padding: 24, textAlign: "center", color: "var(--text-dim)" }}>Loading…</td></tr>
            )}
            {!isLoading && events.length === 0 && (
              <tr><td colSpan={9} style={{ padding: 24, textAlign: "center", color: "var(--text-dim)" }}>No events match the current filters.</td></tr>
            )}
            {events.map(e => (
              <tr key={e.id} style={{ background: rowBg(e.event_type), borderBottom: "1px solid var(--border)" }}>
                <td style={{ padding: "5px 8px", whiteSpace: "nowrap", fontFamily: "monospace", color: "var(--text-dim)" }}>
                  {new Date(e.occurred_at).toLocaleString()}
                </td>
                <td style={{ padding: "5px 8px", whiteSpace: "nowrap" }}>
                  <span style={{
                    fontFamily: "monospace", fontSize: 11, fontWeight: 600,
                    color: e.event_type === "login_failed" || e.event_type === "account_locked" ? "var(--danger-text, #e53e3e)"
                      : e.event_type === "login" ? "var(--success-text, #38a169)"
                      : "var(--text)",
                  }}>
                    {e.event_type}
                  </span>
                </td>
                <td style={{ padding: "5px 8px", fontFamily: "monospace", fontSize: 11 }}>{e.actor_id}</td>
                <td style={{ padding: "5px 8px", fontFamily: "monospace", fontSize: 11, color: "var(--text-dim)" }}>{e.source_ip ?? "—"}</td>
                <td style={{ padding: "5px 8px", fontFamily: "monospace", fontSize: 11, color: "var(--text-dim)" }}>
                  {e.session_id ? e.session_id.slice(0, 8) + "…" : "—"}
                </td>
                <td style={{ padding: "5px 8px", color: "var(--text-dim)" }}>{e.entity_type}</td>
                <td style={{ padding: "5px 8px", fontFamily: "monospace", fontSize: 11, color: "var(--text-dim)", maxWidth: 160, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  <span title={e.entity_id}>{e.entity_id.length > 20 ? e.entity_id.slice(0, 8) + "…" : e.entity_id}</span>
                </td>
                <td style={{ padding: "5px 8px", fontFamily: "monospace", fontSize: 10, color: "var(--text-dim)", maxWidth: 240, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  <span title={JSON.stringify(e.details)}>{JSON.stringify(e.details).slice(0, 80)}</span>
                </td>
                <td style={{ padding: "5px 8px", fontFamily: "monospace", fontSize: 10, color: "var(--text-dim)" }}>
                  {e.immutable_hash.slice(0, 10)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
