import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { listCases, listDocuments, uploadDocumentBinary } from "../lib/api";
import { useResolvedCaseId } from "../lib/cases";
import { formatLabel } from "../lib/format";

export function DocumentUploadPage() {
  const qc = useQueryClient();
  const casesQuery = useQuery({ queryKey: ["cases"], queryFn: listCases });
  const { caseId, selectCase } = useResolvedCaseId(casesQuery.data);

  const [file, setFile] = useState<File | null>(null);
  const [docType, setDocType] = useState("resume_bundle");

  const docsQuery = useQuery({
    queryKey: ["documents", caseId],
    queryFn: () => listDocuments(caseId!),
    enabled: Boolean(caseId),
  });

  const uploadMut = useMutation({
    mutationFn: () => uploadDocumentBinary(caseId!, { file: file!, documentType: docType, metadataSource: "manual-upload" }),
    onSuccess() { qc.invalidateQueries({ queryKey: ["documents", caseId] }); setFile(null); },
  });

  return (
    <div className="workspace">
      <div className="panel panel-flex" style={{ overflow: "hidden", display: "flex", flexDirection: "column" }}>
        <div className="panel-head">
          <span className="panel-head-title">Document Upload</span>
          <select className="select-input" style={{ height: 26, maxWidth: 240 }} value={caseId ?? ""} onChange={e => selectCase(e.target.value || null)}>
            <option value="">— Select engagement —</option>
            {(casesQuery.data ?? []).map(c => <option key={c.id} value={c.id}>{c.title}</option>)}
          </select>
        </div>

        <div className="action-row action-row-border">
          <select className="select-input" style={{ maxWidth: 180 }} value={docType} onChange={e => setDocType(e.target.value)}>
            <option value="position_description">Position Description</option>
            <option value="resume_bundle">Resume Bundle</option>
            <option value="certificate">Certificate</option>
            <option value="vacancy_announcement">Vacancy Announcement</option>
            <option value="transcript">Transcript</option>
            <option value="interview_notes">Interview Notes</option>
            <option value="other">Other</option>
          </select>
          <label className="upload-label" htmlFor="doc-upload">{file ? file.name : "Choose file"}</label>
          <input id="doc-upload" className="upload-input" type="file" accept=".pdf,.docx,.doc,.zip,.txt" onChange={e => setFile(e.target.files?.[0] ?? null)} />
          <button
            className="btn btn-primary btn-sm"
            disabled={!caseId || !file || uploadMut.isPending}
            onClick={() => uploadMut.mutate()}
          >
            {uploadMut.isPending ? "Uploading…" : "Upload"}
          </button>
          {uploadMut.isSuccess && <span className="feedback-success">Uploaded.</span>}
          {uploadMut.isError && <span className="feedback-error">Upload failed.</span>}
        </div>

        <div style={{ overflowY: "auto", flex: 1 }}>
          <table className="tbl">
            <thead>
              <tr>
                <th>File Name</th>
                <th>Type</th>
                <th>Status</th>
                <th style={{ width: 60, textAlign: "center" }}>Pages</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {!caseId && <tr className="empty-row"><td colSpan={5}>Select an engagement</td></tr>}
              {caseId && (docsQuery.data ?? []).length === 0 && (
                <tr className="empty-row"><td colSpan={5}>{docsQuery.isLoading ? "Loading…" : "No documents uploaded yet"}</td></tr>
              )}
              {(docsQuery.data ?? []).map(doc => (
                <tr key={doc.id}>
                  <td style={{ fontWeight: 500 }}>{doc.file_name}</td>
                  <td style={{ color: "var(--text-muted)" }}>{formatLabel(doc.document_type)}</td>
                  <td>
                    <span className={`chip ${doc.status === "ready" ? "chip-success" : doc.status === "processing" ? "chip-warning" : "chip-neutral"}`}>
                      {formatLabel(doc.status)}
                    </span>
                  </td>
                  <td style={{ textAlign: "center", color: "var(--text-muted)" }}>{doc.page_count ?? "—"}</td>
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
