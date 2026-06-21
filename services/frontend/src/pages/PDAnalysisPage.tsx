import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { getPositionAnalysis, listCases, runPositionAnalysis } from "../lib/api";
import { useResolvedCaseId } from "../lib/cases";
import { formatLabel } from "../lib/format";

export function PDAnalysisPage() {
  const qc = useQueryClient();
  const casesQuery = useQuery({ queryKey: ["cases"], queryFn: listCases });
  const { caseId, selectCase } = useResolvedCaseId(casesQuery.data);

  const analysisQuery = useQuery({
    queryKey: ["position-analysis", caseId],
    queryFn: () => getPositionAnalysis(caseId!),
    enabled: Boolean(caseId),
    retry: false,
  });

  const runMut = useMutation({
    mutationFn: () => runPositionAnalysis(caseId!),
    onSuccess() { qc.invalidateQueries({ queryKey: ["position-analysis", caseId] }); },
  });

  const analysis = analysisQuery.data;

  return (
    <div className="workspace">
      <div className="panel panel-flex" style={{ overflow: "hidden", display: "flex", flexDirection: "column" }}>
        <div className="panel-head">
          <span className="panel-head-title">PD Analysis</span>
          <select className="select-input" style={{ height: 26, maxWidth: 240 }} value={caseId ?? ""} onChange={e => selectCase(e.target.value || null)}>
            <option value="">— Select engagement —</option>
            {(casesQuery.data ?? []).map(c => <option key={c.id} value={c.id}>{c.title}</option>)}
          </select>
          {caseId && (
            <button className="btn btn-primary btn-sm" disabled={runMut.isPending} onClick={() => runMut.mutate()}>
              {runMut.isPending ? "Running…" : "Run PD Analysis"}
            </button>
          )}
        </div>
        <div style={{ overflowY: "auto", flex: 1, padding: "0 16px 16px" }}>
          {!caseId && <p className="loading-text">Select an engagement</p>}
          {caseId && !analysis && <p className="loading-text">{analysisQuery.isLoading ? "Loading…" : "No PD analysis — run analysis first"}</p>}

          {analysis && (
            <>
              <div className="settings-section" style={{ paddingTop: 12 }}>
                <div className="settings-section-head">
                  Analysis — {formatLabel(analysis.status)}
                  <span style={{ marginLeft: 8, color: "var(--text-dim)", fontWeight: 400 }}>
                    {analysis.role_type && `${analysis.role_type} · `}
                    {new Date(analysis.updated_at).toLocaleString()}
                  </span>
                </div>
              </div>

              {analysis.duties.length > 0 && (
                <div className="settings-section">
                  <div className="settings-section-head">Duties ({analysis.duties.length})</div>
                  {analysis.duties.map((d, i) => (
                    <div key={i} className="settings-row">
                      <span className="settings-key">{String((d as Record<string, unknown>).title ?? `Duty ${i + 1}`)}</span>
                      <span className="settings-val" style={{ color: "var(--text-muted)" }}>
                        {String((d as Record<string, unknown>).description ?? (d as Record<string, unknown>).detail ?? "")}
                      </span>
                    </div>
                  ))}
                </div>
              )}

              {analysis.critical_factors.length > 0 && (
                <div className="settings-section">
                  <div className="settings-section-head">Critical Factors</div>
                  {analysis.critical_factors.map((f, i) => (
                    <div key={i} className="settings-row">
                      <span className="settings-key">{String((f as Record<string, unknown>).title ?? `Factor ${i + 1}`)}</span>
                      <span className="settings-val" style={{ color: "var(--text-muted)" }}>
                        {String((f as Record<string, unknown>).description ?? "")}
                      </span>
                    </div>
                  ))}
                </div>
              )}

              {analysis.recommended_dimensions.length > 0 && (
                <div className="settings-section">
                  <div className="settings-section-head">Recommended Dimensions ({analysis.recommended_dimensions.length})</div>
                  <table className="rubric-tbl">
                    <thead>
                      <tr>
                        <th>Dimension</th>
                        <th className="col-wt">Wt</th>
                        <th>PD Rationale</th>
                      </tr>
                    </thead>
                    <tbody>
                      {analysis.recommended_dimensions.map((d, i) => {
                        const dim = d as Record<string, unknown>;
                        return (
                          <tr key={i}>
                            <td style={{ fontWeight: 600 }}>{String(dim.title ?? "")}</td>
                            <td className="col-wt">×{String(dim.weight ?? 1)}</td>
                            <td className="col-rat">
                              <span className="rubric-rat-text">{String(dim.description ?? dim.pd_rationale ?? "")}</span>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
