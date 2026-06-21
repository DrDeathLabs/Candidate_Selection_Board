import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import {
  createRubricFromAnalysis,
  listCases,
  listRubrics,
  setRubricLock,
  updateRubric,
  type RubricDimensionInput,
} from "../lib/api";
import { useResolvedCaseId } from "../lib/cases";

export function RubricBuilderPage() {
  const qc = useQueryClient();
  const casesQuery = useQuery({ queryKey: ["cases"], queryFn: listCases });
  const { caseId, selectCase } = useResolvedCaseId(casesQuery.data);

  const rubricsQuery = useQuery({
    queryKey: ["rubrics", caseId],
    queryFn: () => listRubrics(caseId!),
    enabled: Boolean(caseId),
  });

  const activeRubric = rubricsQuery.data?.[0] ?? null;
  const [dims, setDims] = useState<RubricDimensionInput[]>([]);
  const [rubricName, setRubricName] = useState("");

  useEffect(() => {
    if (activeRubric) {
      setDims(activeRubric.dimensions.map(d => ({ title: d.title, description: d.description, weight: Number(d.weight), order_index: d.order_index, evidence_links: d.evidence_links })));
      setRubricName(activeRubric.name);
    }
  }, [activeRubric]);

  const createMut = useMutation({
    mutationFn: () => createRubricFromAnalysis(caseId!),
    onSuccess() { qc.invalidateQueries({ queryKey: ["rubrics", caseId] }); },
  });

  const saveMut = useMutation({
    mutationFn: () => updateRubric(caseId!, activeRubric!.id, { name: rubricName, is_locked: activeRubric!.is_locked, dimensions: dims }),
    onSuccess() { qc.invalidateQueries({ queryKey: ["rubrics", caseId] }); },
  });

  const lockMut = useMutation({
    mutationFn: () => setRubricLock(caseId!, activeRubric!.id, !activeRubric!.is_locked),
    onSuccess() { qc.invalidateQueries({ queryKey: ["rubrics", caseId] }); },
  });

  function updateDim(idx: number, field: keyof RubricDimensionInput, val: string | number) {
    setDims(d => d.map((dim, i) => i === idx ? { ...dim, [field]: field === "weight" ? Number(val) : val } : dim));
  }

  function addDim() {
    setDims(d => [...d, { title: "New Dimension", description: "", weight: 1, order_index: d.length + 1, evidence_links: [] }]);
  }

  function removeDim(idx: number) {
    setDims(d => d.filter((_, i) => i !== idx));
  }

  const totalWeight = dims.reduce((s, d) => s + Number(d.weight), 0);

  return (
    <div className="workspace">
      <div className="panel panel-flex" style={{ overflow: "hidden", display: "flex", flexDirection: "column" }}>
        <div className="panel-head">
          <span className="panel-head-title">Rubric Builder</span>
          <select className="select-input" style={{ height: 26, maxWidth: 240 }} value={caseId ?? ""} onChange={e => selectCase(e.target.value || null)}>
            <option value="">— Select engagement —</option>
            {(casesQuery.data ?? []).map(c => <option key={c.id} value={c.id}>{c.title}</option>)}
          </select>
          {caseId && !activeRubric && (
            <button className="btn btn-primary btn-sm" disabled={createMut.isPending} onClick={() => createMut.mutate()}>
              {createMut.isPending ? "Generating…" : "Generate from PD"}
            </button>
          )}
          {activeRubric && (
            <>
              <button className="btn btn-primary btn-sm" disabled={saveMut.isPending || activeRubric.is_locked} onClick={() => saveMut.mutate()}>
                {saveMut.isPending ? "Saving…" : "Save"}
              </button>
              <button className="btn btn-sm" disabled={lockMut.isPending} onClick={() => lockMut.mutate()}>
                {activeRubric.is_locked ? "Unlock" : "Lock"}
              </button>
            </>
          )}
        </div>

        {activeRubric && (
          <div className="action-row action-row-border">
            <input
              className="input"
              style={{ maxWidth: 320 }}
              value={rubricName}
              onChange={e => setRubricName(e.target.value)}
              disabled={activeRubric.is_locked}
              placeholder="Rubric name"
            />
            <span className="text-muted text-sm">
              {dims.length} dimensions · wt {totalWeight} · max {totalWeight * 3}
            </span>
            {activeRubric.is_locked && <span className="chip chip-warning">Locked</span>}
          </div>
        )}

        <div style={{ overflowY: "auto", flex: 1 }}>
          {!caseId && <p className="loading-text">Select an engagement</p>}
          {caseId && !activeRubric && (
            <p className="loading-text">{rubricsQuery.isLoading ? "Loading…" : "No rubric — generate one from PD analysis"}</p>
          )}
          {activeRubric && (
            <>
              <table className="rubric-tbl">
                <thead>
                  <tr>
                    <th>Dimension</th>
                    <th className="col-wt">Wt</th>
                    <th className="col-max">Max</th>
                    <th className="col-rat">PD Rationale</th>
                    <th className="col-act">—</th>
                  </tr>
                </thead>
                <tbody>
                  {dims.map((d, i) => (
                    <tr key={i}>
                      <td>
                        {activeRubric.is_locked ? (
                          <span>{d.title}</span>
                        ) : (
                          <input className="input" value={d.title} onChange={e => updateDim(i, "title", e.target.value)} style={{ height: 24, fontSize: 11 }} />
                        )}
                      </td>
                      <td className="col-wt">
                        {activeRubric.is_locked ? (
                          <span>×{d.weight}</span>
                        ) : (
                          <input className="input" type="number" min={1} max={5} value={d.weight} onChange={e => updateDim(i, "weight", e.target.value)} style={{ height: 24, fontSize: 11, textAlign: "center" }} />
                        )}
                      </td>
                      <td className="col-max" style={{ textAlign: "center", color: "var(--text-muted)" }}>{Number(d.weight) * 3}</td>
                      <td className="col-rat">
                        {activeRubric.is_locked ? (
                          <span className="rubric-rat-text">{d.description || "—"}</span>
                        ) : (
                          <textarea className="textarea-input" value={d.description} onChange={e => updateDim(i, "description", e.target.value)} style={{ minHeight: 40, fontSize: 11 }} />
                        )}
                      </td>
                      <td className="col-act" style={{ textAlign: "right" }}>
                        {!activeRubric.is_locked && (
                          <button className="btn btn-ghost btn-sm" onClick={() => removeDim(i)} style={{ color: "var(--danger-text)" }}>✕</button>
                        )}
                      </td>
                    </tr>
                  ))}
                  <tr>
                    <td style={{ fontWeight: 600 }}>Total</td>
                    <td style={{ textAlign: "center", fontWeight: 700 }}>×{totalWeight}</td>
                    <td style={{ textAlign: "center", fontWeight: 700 }}>{totalWeight * 3}</td>
                    <td colSpan={2} />
                  </tr>
                </tbody>
              </table>
              {!activeRubric.is_locked && (
                <div className="action-row action-row-border">
                  <button className="btn btn-sm" onClick={addDim}>+ Add dimension</button>
                </div>
              )}
            </>
          )}
          {saveMut.isError && <p className="feedback-error" style={{ padding: "8px 12px" }}>Save failed.</p>}
          {saveMut.isSuccess && <p className="feedback-success" style={{ padding: "8px 12px" }}>Saved.</p>}
        </div>
      </div>
    </div>
  );
}
