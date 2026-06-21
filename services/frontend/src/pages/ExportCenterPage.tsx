import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { listCases, listExports, requestExport } from "../lib/api";
import { useResolvedCaseId } from "../lib/cases";
import { formatLabel } from "../lib/format";

export function ExportCenterPage() {
  const qc = useQueryClient();
  const casesQuery = useQuery({ queryKey: ["cases"], queryFn: listCases });
  const { caseId, selectCase } = useResolvedCaseId(casesQuery.data);
  const [exportType, setExportType] = useState("decision_package");

  const exportsQuery = useQuery({
    queryKey: ["exports", caseId],
    queryFn: () => listExports(caseId!),
    enabled: Boolean(caseId),
  });

  const exportMut = useMutation({
    mutationFn: () => requestExport(caseId!, exportType),
    onSuccess() { qc.invalidateQueries({ queryKey: ["exports", caseId] }); },
  });

  return (
    <div className="workspace">
      <div className="panel panel-flex" style={{ overflow: "hidden", display: "flex", flexDirection: "column" }}>
        <div className="panel-head">
          <span className="panel-head-title">Export Center</span>
          <select className="select-input" style={{ height: 26, maxWidth: 240 }} value={caseId ?? ""} onChange={e => selectCase(e.target.value || null)}>
            <option value="">— Select engagement —</option>
            {(casesQuery.data ?? []).map(c => <option key={c.id} value={c.id}>{c.title}</option>)}
          </select>
          <select className="select-input" style={{ height: 26, maxWidth: 200 }} value={exportType} onChange={e => setExportType(e.target.value)}>
            <option value="decision_package">Decision Package</option>
            <option value="candidate_matrix">Candidate Matrix</option>
            <option value="audit_report">Audit Report</option>
            <option value="rubric_export">Rubric Export</option>
          </select>
          <button className="btn btn-primary btn-sm" disabled={!caseId || exportMut.isPending} onClick={() => exportMut.mutate()}>
            {exportMut.isPending ? "Queuing…" : "Request Export"}
          </button>
        </div>
        <div style={{ overflowY: "auto", flex: 1 }}>
          <table className="tbl">
            <thead>
              <tr>
                <th>Export Type</th>
                <th>Status</th>
                <th>ID</th>
                <th>Download</th>
              </tr>
            </thead>
            <tbody>
              {!caseId && <tr className="empty-row"><td colSpan={4}>Select an engagement to view exports</td></tr>}
              {caseId && (exportsQuery.data ?? []).length === 0 && (
                <tr className="empty-row"><td colSpan={4}>{exportsQuery.isLoading ? "Loading…" : "No exports yet"}</td></tr>
              )}
              {(exportsQuery.data ?? []).map(exp => (
                <tr key={exp.id}>
                  <td style={{ fontWeight: 600 }}>{formatLabel(exp.export_type)}</td>
                  <td>
                    <span className={`chip ${exp.status === "ready" ? "chip-success" : exp.status === "processing" ? "chip-warning" : "chip-neutral"}`}>
                      {formatLabel(exp.status)}
                    </span>
                  </td>
                  <td style={{ fontFamily: "monospace", fontSize: 10, color: "var(--text-muted)" }}>{exp.id.slice(0, 12)}…</td>
                  <td>
                    {exp.storage_key ? (
                      <span style={{ color: "var(--brand)", fontSize: 11 }}>{exp.storage_key}</span>
                    ) : (
                      <span style={{ color: "var(--text-dim)", fontSize: 11 }}>—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {exportMut.isSuccess && <p className="feedback-success" style={{ padding: "8px 12px" }}>Export queued.</p>}
          {exportMut.isError && <p className="feedback-error" style={{ padding: "8px 12px" }}>Export request failed.</p>}
        </div>
      </div>
    </div>
  );
}
