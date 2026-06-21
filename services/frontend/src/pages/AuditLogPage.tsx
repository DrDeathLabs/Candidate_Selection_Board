import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { listAuditEvents, listCases } from "../lib/api";
import { useResolvedCaseId } from "../lib/cases";
import { formatLabel } from "../lib/format";

export function AuditLogPage() {
  const casesQuery = useQuery({ queryKey: ["cases"], queryFn: listCases });
  const { caseId, selectedCase, selectCase } = useResolvedCaseId(casesQuery.data);
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState("");

  const eventsQuery = useQuery({
    queryKey: ["audit-events", caseId],
    queryFn: () => listAuditEvents(caseId!),
    enabled: Boolean(caseId),
  });

  const events = (eventsQuery.data ?? []).filter(e => {
    if (typeFilter && e.event_type !== typeFilter) return false;
    if (search && !e.event_type.toLowerCase().includes(search.toLowerCase()) && !e.entity_type.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  const eventTypes = [...new Set((eventsQuery.data ?? []).map(e => e.event_type))].sort();

  return (
    <div className="workspace">
      <div className="panel panel-flex" style={{ overflow: "hidden", display: "flex", flexDirection: "column" }}>
        <div className="panel-head">
          <span className="panel-head-title">Audit Log</span>
          <select className="select-input" style={{ height: 26, maxWidth: 200 }} value={caseId ?? ""} onChange={e => selectCase(e.target.value || null)}>
            <option value="">— Select engagement —</option>
            {(casesQuery.data ?? []).map(c => <option key={c.id} value={c.id}>{c.title}</option>)}
          </select>
          <input className="input" style={{ height: 26, width: 180 }} placeholder="Search events…" value={search} onChange={e => setSearch(e.target.value)} />
          <select className="select-input" style={{ height: 26, maxWidth: 200 }} value={typeFilter} onChange={e => setTypeFilter(e.target.value)}>
            <option value="">All event types</option>
            {eventTypes.map(t => <option key={t} value={t}>{formatLabel(t)}</option>)}
          </select>
          <span className="text-muted text-sm">{events.length} events</span>
        </div>
        <div style={{ overflowY: "auto", flex: 1 }}>
          <table className="tbl">
            <thead>
              <tr>
                <th>Time</th>
                <th>Event Type</th>
                <th>Entity Type</th>
                <th>Entity ID</th>
                <th>Actor</th>
                <th>Hash</th>
              </tr>
            </thead>
            <tbody>
              {!caseId && <tr className="empty-row"><td colSpan={6}>Select an engagement to view its audit log</td></tr>}
              {caseId && events.length === 0 && (
                <tr className="empty-row"><td colSpan={6}>{eventsQuery.isLoading ? "Loading…" : "No audit events"}</td></tr>
              )}
              {events.map(e => (
                <tr key={e.id}>
                  <td style={{ color: "var(--text-muted)", whiteSpace: "nowrap" }}>{new Date(e.occurred_at).toLocaleString()}</td>
                  <td style={{ fontWeight: 600 }}>{formatLabel(e.event_type)}</td>
                  <td style={{ color: "var(--text-muted)" }}>{e.entity_type}</td>
                  <td style={{ color: "var(--text-dim)", fontFamily: "monospace", fontSize: 10 }}>{e.entity_id.slice(0, 12)}…</td>
                  <td style={{ color: "var(--text-muted)" }}>{e.actor_id || "system"}</td>
                  <td style={{ color: "var(--text-dim)", fontFamily: "monospace", fontSize: 10 }}>{e.immutable_hash?.slice(0, 12)}…</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
