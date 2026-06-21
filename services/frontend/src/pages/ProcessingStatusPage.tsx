import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { getProcessingSnapshot, listCases } from "../lib/api";
import { useResolvedCaseId } from "../lib/cases";
import { formatLabel } from "../lib/format";

export function ProcessingStatusPage() {
  const casesQuery = useQuery({ queryKey: ["cases"], queryFn: listCases });
  const { caseId, selectCase } = useResolvedCaseId(casesQuery.data);

  const snapshotQuery = useQuery({
    queryKey: ["processing-snapshot", caseId],
    queryFn: () => getProcessingSnapshot(caseId!),
    enabled: Boolean(caseId),
    refetchInterval: 5000,
  });

  const snap = snapshotQuery.data;

  return (
    <div className="workspace">
      <div className="panel panel-flex" style={{ overflow: "hidden", display: "flex", flexDirection: "column" }}>
        <div className="panel-head">
          <span className="panel-head-title">Document Processing</span>
          <select className="select-input" style={{ height: 26, maxWidth: 240 }} value={caseId ?? ""} onChange={e => selectCase(e.target.value || null)}>
            <option value="">— Select engagement —</option>
            {(casesQuery.data ?? []).map(c => <option key={c.id} value={c.id}>{c.title}</option>)}
          </select>
          {snap && (
            <div className="metrics-bar" style={{ border: "none", background: "none", padding: "0" }}>
              <span className="metric-item">Total <span className="metric-val">{snap.summary.total_documents}</span></span>
              {Object.entries(snap.summary.by_status).map(([k, v]) => (
                <span key={k} className="metric-item">{formatLabel(k)} <span className="metric-val">{v}</span></span>
              ))}
              {snap.summary.unreadable_or_flagged > 0 && (
                <span className="metric-item" style={{ color: "var(--danger-text)" }}>Flagged <span className="metric-val">{snap.summary.unreadable_or_flagged}</span></span>
              )}
            </div>
          )}
        </div>
        <div style={{ overflowY: "auto", flex: 1 }}>
          <table className="tbl">
            <thead>
              <tr>
                <th>File Name</th>
                <th>Type</th>
                <th>Status</th>
                <th style={{ width: 60, textAlign: "center" }}>Pages</th>
                <th>Scan</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {!caseId && <tr className="empty-row"><td colSpan={6}>Select an engagement</td></tr>}
              {caseId && (snap?.documents ?? []).length === 0 && (
                <tr className="empty-row"><td colSpan={6}>{snapshotQuery.isLoading ? "Loading…" : "No documents"}</td></tr>
              )}
              {(snap?.documents ?? []).map(doc => (
                <tr key={doc.id}>
                  <td style={{ fontWeight: 500 }}>{doc.file_name}</td>
                  <td style={{ color: "var(--text-muted)" }}>{formatLabel(doc.document_type)}</td>
                  <td>
                    <span className={`chip ${doc.status === "ready" ? "chip-success" : doc.status === "processing" ? "chip-warning" : doc.status === "error" ? "chip-danger" : "chip-neutral"}`}>
                      {formatLabel(doc.status)}
                    </span>
                  </td>
                  <td style={{ textAlign: "center", color: "var(--text-muted)" }}>{doc.page_count ?? "—"}</td>
                  <td>
                    <span className={`chip ${doc.malware_scan_status === "clean" ? "chip-success" : doc.malware_scan_status === "pending" ? "chip-neutral" : "chip-danger"}`}>
                      {doc.malware_scan_status}
                    </span>
                  </td>
                  <td style={{ color: "var(--text-dim)", whiteSpace: "nowrap" }}>{new Date(doc.created_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
