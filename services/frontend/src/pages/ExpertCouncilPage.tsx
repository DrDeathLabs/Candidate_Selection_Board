import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  BoardMeetingRecord,
  DeliberationTurnRecord,
  DimensionAssessment,
  deleteBoardMeeting,
  deleteAllBoardMeetings,
  getBoardMeeting,
  listBoardMeetings,
  listCases,
  listExpertReviewsForCase,
  queueExpertCouncil,
  stopCouncil,
} from "../lib/api";
import { useResolvedCaseId } from "../lib/cases";

type MeetingTab = "transcript" | "notes" | "opening";

const PHASE_COLOR: Record<string, string> = {
  opening: "var(--brand)",
  deliberation: "var(--warning-text)",
  synthesis: "var(--success-text)",
};

function phaseLabel(phase: string) {
  if (phase === "opening") return "Phase I";
  if (phase === "deliberation") return "Phase II";
  if (phase === "synthesis") return "Phase III";
  return phase;
}

function confChip(conf: number) {
  const pct = Math.round((conf ?? 0) * 100);
  const cls = pct >= 80 ? "chip-success" : pct >= 60 ? "chip-warning" : "chip-dim";
  return <span className={`chip ${cls}`}>{pct}%</span>;
}

function eqBadge(eq: string) {
  if (!eq) return null;
  const q = eq.toUpperCase();
  if (q === "DOCUMENTED") return <span className="chip chip-success" style={{ fontSize: 10 }}>DOCUMENTED</span>;
  if (q === "ABSENT")     return <span className="chip chip-danger"  style={{ fontSize: 10 }}>ABSENT</span>;
  return <span className="chip chip-warning" style={{ fontSize: 10 }}>INFERRED</span>;
}

function dimAssessChip(a: string) {
  const v = (a ?? "").toUpperCase();
  if (v === "EXCEEDS") return <span className="chip chip-success" style={{ fontSize: 10 }}>EX</span>;
  if (v === "MEETS")   return <span className="chip chip-warning" style={{ fontSize: 10 }}>MQ</span>;
  if (v === "PARTIAL") return <span className="chip chip-dim"     style={{ fontSize: 10 }}>PQ</span>;
  return <span className="chip chip-danger" style={{ fontSize: 10 }}>NQ</span>;
}

function TurnCard({ turn }: { turn: DeliberationTurnRecord }) {
  const [open, setOpen] = useState(false);
  const color = PHASE_COLOR[turn.phase] ?? "var(--text-muted)";
  const isChair = turn.speaker === "council_chair";
  const hasDims = (turn.dimension_assessments?.length ?? 0) > 0;
  const hasDetails = hasDims || (turn.strengths?.length ?? 0) + (turn.concerns?.length ?? 0) + (turn.findings?.length ?? 0) > 0;

  return (
    <div style={{
      borderLeft: `3px solid ${color}`,
      paddingLeft: 12,
      marginBottom: 12,
      opacity: isChair ? 0.7 : 1,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4, flexWrap: "wrap" }}>
        <span style={{ fontWeight: 700, fontSize: 12, color, textTransform: "uppercase", letterSpacing: "0.04em" }}>
          {turn.display_name}
        </span>
        <span className="chip chip-dim" style={{ fontSize: 10 }}>{phaseLabel(turn.phase)}</span>
        {turn.confidence > 0 && confChip(turn.confidence)}
        {turn.evidence_quality && eqBadge(turn.evidence_quality)}
        {turn.responding_to?.length > 0 && (
          <span className="chip chip-warning" style={{ fontSize: 10 }}>↩ response</span>
        )}
        {hasDetails && (
          <button
            onClick={() => setOpen(o => !o)}
            style={{ marginLeft: "auto", background: "none", border: "none", color: "var(--text-muted)", cursor: "pointer", fontSize: 11 }}
          >
            {open ? "▲ less" : "▼ details"}
          </button>
        )}
      </div>
      <div style={{ fontSize: 13, lineHeight: 1.65, color: "var(--text)", whiteSpace: "pre-wrap" }}>
        {turn.content}
      </div>
      {open && hasDetails && (
        <div style={{ marginTop: 8, display: "grid", gap: 8 }}>
          {hasDims && (
            <div>
              <div style={{ fontSize: 10, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}>
                Dimension Analysis
              </div>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                <tbody>
                  {turn.dimension_assessments.map((d: DimensionAssessment, i: number) => (
                    <tr key={i} style={{ borderBottom: "1px solid var(--border)" }}>
                      <td style={{ padding: "4px 6px 4px 0", width: 28, verticalAlign: "top" }}>
                        {dimAssessChip(d.assessment)}
                      </td>
                      <td style={{ padding: "4px 8px 4px 0", fontWeight: 600, verticalAlign: "top", whiteSpace: "nowrap", color: "var(--text)" }}>
                        {d.dimension}
                      </td>
                      <td style={{ padding: "4px 0", color: d.evidence_quote === "NOT DOCUMENTED" ? "var(--danger-text)" : "var(--text-muted)", fontStyle: d.evidence_quote === "NOT DOCUMENTED" ? "normal" : "italic", verticalAlign: "top" }}>
                        {d.evidence_quote}
                        {d.gap && <span style={{ display: "block", color: "var(--warning-text)", fontStyle: "normal", marginTop: 2 }}>Gap: {d.gap}</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {turn.strengths?.length > 0 && (
            <div>
              <div style={{ fontSize: 10, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 2 }}>
                Strengths
              </div>
              <ul className="bullet-list" style={{ marginLeft: 12 }}>
                {turn.strengths.map((s, i) => <li key={i}>{s}</li>)}
              </ul>
            </div>
          )}
          {turn.concerns?.length > 0 && (
            <div>
              <div style={{ fontSize: 10, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 2 }}>
                Concerns
              </div>
              <ul className="bullet-list concern" style={{ marginLeft: 12 }}>
                {turn.concerns.map((c, i) => <li key={i}>{c}</li>)}
              </ul>
            </div>
          )}
          {turn.findings?.length > 0 && (
            <div>
              <div style={{ fontSize: 10, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 2 }}>
                Findings
              </div>
              {turn.findings.map((f, i) => (
                <div key={i} style={{ fontSize: 12, marginBottom: 3 }}>
                  <span className={`chip chip-${f.severity === "high" ? "warning" : "dim"}`} style={{ fontSize: 10, marginRight: 6 }}>
                    {f.severity?.toUpperCase()}
                  </span>
                  <strong>{f.title}</strong> — {f.detail}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function MeetingNotes({ notes }: { notes: Record<string, unknown> }) {
  const ph1 = (notes.phase_1 ?? {}) as Record<string, unknown>;
  const ph2 = (notes.phase_2 ?? {}) as Record<string, unknown>;
  const ph3 = (notes.phase_3 ?? {}) as Record<string, unknown>;

  return (
    <div style={{ display: "grid", gap: 16 }}>
      <section>
        <div className="dossier-section-label">Phase I — Opening Statements</div>
        <table className="mini-table">
          <tbody>
            <tr><td className="mini-key">Agents</td><td>{String(ph1.agents_participated ?? "—")}</td></tr>
            <tr><td className="mini-key">Avg Confidence</td><td>{typeof ph1.average_confidence === "number" ? `${Math.round(ph1.average_confidence * 100)}%` : "—"}</td></tr>
          </tbody>
        </table>
        {Array.isArray(ph1.initial_strengths) && ph1.initial_strengths.length > 0 && (
          <div style={{ marginTop: 8 }}>
            <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 4 }}>Initial Strengths</div>
            <ul className="bullet-list">{(ph1.initial_strengths as string[]).map((s, i) => <li key={i}>{s}</li>)}</ul>
          </div>
        )}
        {Array.isArray(ph1.initial_concerns) && ph1.initial_concerns.length > 0 && (
          <div style={{ marginTop: 8 }}>
            <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 4 }}>Initial Concerns</div>
            <ul className="bullet-list concern">{(ph1.initial_concerns as string[]).map((c, i) => <li key={i}>{c}</li>)}</ul>
          </div>
        )}
      </section>

      <section>
        <div className="dossier-section-label">Phase II — Deliberation</div>
        {Boolean(ph2.skeptic_summary) && (
          <div style={{ fontSize: 13, marginBottom: 8, color: "var(--text)" }}>{String(ph2.skeptic_summary)}</div>
        )}
        {Array.isArray(ph2.challenges_raised) && ph2.challenges_raised.length > 0 && (
          <div>
            <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 4 }}>Challenges Raised</div>
            <ul className="bullet-list concern">{(ph2.challenges_raised as string[]).map((c, i) => <li key={i}>{c}</li>)}</ul>
          </div>
        )}
        <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 6 }}>
          Domain responses: {String(ph2.domain_responses ?? 0)}
        </div>
      </section>

      <section>
        <div className="dossier-section-label">Phase III — Chair Conclusion</div>
        <table className="mini-table">
          <tbody>
            <tr><td className="mini-key">Recommendation</td>
              <td><strong style={{ color: ph3.recommendation === "ADVANCE" ? "var(--success-text)" : ph3.recommendation === "DECLINE" ? "var(--danger-text)" : "var(--warning-text)" }}>
                {String(ph3.recommendation ?? "—")}
              </strong></td>
            </tr>
            <tr><td className="mini-key">Tier</td><td>{String(ph3.tier ?? "—")}</td></tr>
            <tr><td className="mini-key">Confidence</td>
              <td>{typeof ph3.final_confidence === "number" ? `${Math.round((ph3.final_confidence as number) * 100)}%` : "—"}</td>
            </tr>
          </tbody>
        </table>
        {Array.isArray(ph3.board_agreements) && ph3.board_agreements.length > 0 && (
          <div style={{ marginTop: 8 }}>
            <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 4 }}>Board Agreements</div>
            <ul className="bullet-list">{(ph3.board_agreements as string[]).map((a, i) => <li key={i}>{a}</li>)}</ul>
          </div>
        )}
        {Array.isArray(ph3.unresolved_questions) && ph3.unresolved_questions.length > 0 && (
          <div style={{ marginTop: 8 }}>
            <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 4 }}>Unresolved Questions</div>
            <ul className="bullet-list concern">{(ph3.unresolved_questions as string[]).map((q, i) => <li key={i}>{q}</li>)}</ul>
          </div>
        )}
      </section>
    </div>
  );
}

function escapeHtml(str: string): string {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function formatMeetingNotesHTML(notes: Record<string, unknown>): string {
  const sections: string[] = [];
  for (const [key, val] of Object.entries(notes)) {
    if (val && typeof val === "object" && !Array.isArray(val)) {
      sections.push(`<h3>${escapeHtml(key.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase()))}</h3>`);
      for (const [k2, v2] of Object.entries(val as Record<string, unknown>)) {
        const label = escapeHtml(k2.replace(/_/g, " "));
        if (Array.isArray(v2) && v2.length) {
          sections.push(`<p><strong>${label}:</strong></p><ul>${v2.map(i => `<li>${escapeHtml(String(i))}</li>`).join("")}</ul>`);
        } else if (typeof v2 === "string" || typeof v2 === "number") {
          sections.push(`<p><strong>${label}:</strong> ${escapeHtml(String(v2))}</p>`);
        }
      }
    }
  }
  return sections.join("\n");
}

function exportTranscriptPDF(meeting: BoardMeetingRecord, caseTitle: string) {
  const synthesis = meeting.phase3_synthesis ?? {};
  const notes = (meeting.meeting_notes ?? {}) as Record<string, unknown>;
  const date = new Date(meeting.created_at).toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" });

  const agentBlocks = (turns: typeof meeting.phase1_turns) =>
    turns.filter(t => t.speaker !== "council_chair").map(t => `
<div class="agent-block">
  <div class="agent-name">${escapeHtml(t.display_name ?? t.speaker)}</div>
  <div class="agent-meta">Confidence: ${Math.round((t.confidence ?? 0) * 100)}%${t.evidence_quality ? ` &nbsp;·&nbsp; Evidence: ${escapeHtml(t.evidence_quality)}` : ""}</div>
  <p>${escapeHtml(t.content ?? t.summary ?? "").replace(/\n/g, "<br>")}</p>
  ${(t.strengths?.length) ? `<p><strong>Strengths:</strong> ${t.strengths.map(escapeHtml).join("; ")}</p>` : ""}
  ${(t.concerns?.length) ? `<p><strong>Concerns:</strong> ${t.concerns.map(escapeHtml).join("; ")}</p>` : ""}
</div>`).join("");

  const agreements = synthesis.agreements as string[] | undefined;
  const questions = synthesis.open_questions as string[] | undefined;
  const notesHTML = Object.keys(notes).length ? `<h2>Meeting Notes</h2>${formatMeetingNotesHTML(notes)}` : "";

  const html = `<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Board Meeting — ${escapeHtml(meeting.candidate_name)}</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: Georgia, "Times New Roman", serif; font-size: 11pt; color: #1a1a1a; padding: 0.75in; }
  h1 { font-size: 13pt; font-weight: bold; letter-spacing: 0.04em; margin-bottom: 4pt; }
  h2 { font-size: 10pt; font-weight: bold; text-transform: uppercase; letter-spacing: 0.09em;
       border-bottom: 1.5px solid #333; padding-bottom: 3pt; margin: 20pt 0 10pt; }
  h3 { font-size: 10pt; font-weight: bold; margin: 12pt 0 4pt; color: #333; }
  p  { font-size: 10pt; line-height: 1.65; margin-bottom: 5pt; }
  ul { margin: 3pt 0 8pt 18pt; }
  li { font-size: 10pt; line-height: 1.55; margin-bottom: 2pt; }
  .meta { font-size: 9pt; color: #555; border-bottom: 1px solid #ccc; padding-bottom: 10pt; margin-bottom: 14pt; }
  .summary { font-size: 10.5pt; line-height: 1.7; font-style: italic; margin-bottom: 4pt; }
  .agent-block { border-left: 2.5px solid #bbb; padding: 5pt 0 5pt 10pt; margin-bottom: 12pt; page-break-inside: avoid; }
  .agent-name { font-size: 9.5pt; font-weight: bold; text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 1pt; }
  .agent-meta { font-size: 8.5pt; color: #666; margin-bottom: 4pt; }
  .synthesis-box { border: 1.5px solid #333; padding: 10pt 14pt; margin: 8pt 0 16pt; page-break-inside: avoid; }
  .verdict { font-size: 12pt; font-weight: bold; margin-bottom: 8pt; letter-spacing: 0.02em; }
  .divider { border: none; border-top: 1px solid #ccc; margin: 16pt 0; }
  @media print { @page { margin: 0.75in; size: letter; } body { padding: 0; } }
</style>
</head>
<body>
<h1>CANDIDATE SELECTION BOARD MEETING TRANSCRIPT</h1>
<div class="meta">
  <strong>Case:</strong> ${escapeHtml(caseTitle)} &nbsp;·&nbsp;
  <strong>Candidate:</strong> ${escapeHtml(meeting.candidate_name)} &nbsp;·&nbsp;
  <strong>Date:</strong> ${escapeHtml(date)}<br>
  ${escapeHtml(String(meeting.agent_count))} agents &nbsp;·&nbsp; ${escapeHtml(String(meeting.round_count))} deliberation rounds
</div>

${meeting.meeting_summary ? `<h2>Executive Summary</h2><p class="summary">${escapeHtml(meeting.meeting_summary).replace(/\n/g, "<br>")}</p>` : ""}

<h2>Phase I — Opening Statements</h2>
${agentBlocks(meeting.phase1_turns ?? [])}

${(meeting.phase2_turns?.length ?? 0) > 0 ? `<h2>Phase II — Board Deliberation</h2>${agentBlocks(meeting.phase2_turns ?? [])}` : ""}

<h2>Phase III — Chair Synthesis</h2>
<div class="synthesis-box">
  <div class="verdict">
    ${escapeHtml(String(synthesis.recommendation ?? "—"))} &nbsp;·&nbsp; Tier ${escapeHtml(String(synthesis.tier ?? "—"))} &nbsp;·&nbsp; ${synthesis.confidence != null ? Math.round((synthesis.confidence as number) * 100) + "% confidence" : "—"}
  </div>
  ${agreements?.length ? `<p><strong>Board agreements:</strong></p><ul>${agreements.map(a => `<li>${escapeHtml(a)}</li>`).join("")}</ul>` : ""}
  ${questions?.length ? `<p><strong>Interview targets:</strong></p><ul>${questions.map(q => `<li>${escapeHtml(q)}</li>`).join("")}</ul>` : ""}
</div>

${notesHTML}
</body>
</html>`;

  const blob = new Blob([html], { type: "text/html;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const win = window.open(url, "_blank");
  if (!win) { URL.revokeObjectURL(url); alert("Allow pop-ups to export PDF"); return; }
  setTimeout(() => { win.print(); URL.revokeObjectURL(url); }, 400);
}

function MeetingDetail({
  caseId,
  candidateId,
  isRunning,
  caseTitle,
}: {
  caseId: string;
  candidateId: string;
  isRunning: boolean;
  caseTitle: string;
}) {
  const [tab, setTab] = useState<MeetingTab>("transcript");
  const transcriptRef = useRef<HTMLDivElement>(null);

  const meetingQ = useQuery({
    queryKey: ["board-meeting", caseId, candidateId],
    queryFn: () => getBoardMeeting(caseId, candidateId),
    refetchInterval: isRunning ? 3_000 : false,
    refetchIntervalInBackground: true,
  });
  const meeting = meetingQ.data;

  const isLive = meeting?.status === "in_progress";
  const turnCount = (meeting?.phase1_turns?.length ?? 0) + (meeting?.phase2_turns?.length ?? 0);

  // Auto-scroll transcript to bottom when new turns arrive
  useEffect(() => {
    if (isLive && transcriptRef.current) {
      transcriptRef.current.scrollTop = transcriptRef.current.scrollHeight;
    }
  }, [turnCount, isLive]);

  if (meetingQ.isLoading) return <p className="loading-text">Loading meeting transcript…</p>;
  if (!meeting) {
    return (
      <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 8 }}>
        <div style={{ fontSize: 13, color: "var(--text-muted)" }}>
          {isRunning ? "Board convening… first agent speaks in ~30 seconds" : "No board meeting on record — run Expert Council first."}
        </div>
        {isRunning && (
          <span style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12, color: "var(--warning-text)" }}>
            <span style={{
              width: 8, height: 8, borderRadius: "50%",
              background: "var(--warning-text)",
              boxShadow: "0 0 0 3px color-mix(in srgb, var(--warning) 20%, transparent)",
              animation: "pulse 1.5s ease-in-out infinite",
            }} />
            Waiting for first agent
          </span>
        )}
      </div>
    );
  }

  const synth = meeting.phase3_synthesis;

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      {/* Meeting header */}
      <div style={{ padding: "10px 14px", borderBottom: "1px solid var(--border)", flexShrink: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
          <span style={{ fontWeight: 700, fontSize: 15 }}>{meeting.candidate_name}</span>
          {isLive && (
            <span style={{ display: "inline-flex", alignItems: "center", gap: 5, fontSize: 11, fontWeight: 700, color: "var(--warning-text)", border: "1px solid var(--warning-text)", borderRadius: 3, padding: "1px 7px" }}>
              <span style={{
                width: 6, height: 6, borderRadius: "50%",
                background: "var(--warning-text)",
                animation: "pulse 1.2s ease-in-out infinite",
              }} />
              LIVE
            </span>
          )}
          {synth?.tier && (
            <span className={`chip chip-tier-${(synth.tier ?? "").toLowerCase()}`}>
              Tier {synth.tier}
            </span>
          )}
          {synth?.recommendation && (
            <span className={`chip ${synth.recommendation === "ADVANCE" ? "chip-success" : synth.recommendation === "DECLINE" ? "chip-danger" : "chip-warning"}`}>
              {synth.recommendation}
            </span>
          )}
          <span className="chip chip-dim">{meeting.agent_count} agents</span>
          {meeting.status === "complete" && (
            <button
              onClick={() => exportTranscriptPDF(meeting, caseTitle)}
              style={{ marginLeft: "auto", background: "none", border: "1px solid var(--border)", color: "var(--text-muted)", cursor: "pointer", fontSize: 11, padding: "3px 10px", borderRadius: 3, flexShrink: 0 }}
              title="Export transcript as PDF"
            >
              Export PDF
            </button>
          )}
        </div>
        {meeting.meeting_summary && !isLive && (
          <div style={{ fontSize: 12, color: "var(--text-muted)", lineHeight: 1.5 }}>
            {meeting.meeting_summary}
          </div>
        )}
        {isLive && (
          <div style={{ fontSize: 12, color: "var(--text-dim)", lineHeight: 1.5 }}>
            Phase I: {meeting.phase1_turns?.filter(t => t.speaker !== "council_chair").length ?? 0} agents spoken
            {(meeting.phase2_turns?.length ?? 0) > 0 && ` · Phase II: ${meeting.phase2_turns?.length} turns`}
          </div>
        )}
      </div>

      {/* Tabs */}
      <div style={{ display: "flex", borderBottom: "1px solid var(--border)", flexShrink: 0 }}>
        {(["transcript", "notes", "opening"] as MeetingTab[]).map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`dossier-tab${tab === t ? " dossier-tab-active" : ""}`}
          >
            {t === "transcript" ? "Transcript" : t === "notes" ? "Meeting Notes" : "Opening Statements"}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div ref={transcriptRef} style={{ overflowY: "auto", flex: 1, padding: "12px 14px" }}>
        {tab === "transcript" && (
          <>
            {/* Phase I */}
            {(meeting.phase1_turns?.length ?? 0) > 0 && (
              <div style={{ marginBottom: 20 }}>
                <div style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: PHASE_COLOR.opening, marginBottom: 10, paddingBottom: 4, borderBottom: "1px solid var(--border)" }}>
                  Phase I — Opening Statements
                </div>
                {meeting.phase1_turns.map((t, i) => <TurnCard key={i} turn={t} />)}
              </div>
            )}
            {/* Phase II */}
            {(meeting.phase2_turns?.length ?? 0) > 0 && (
              <div style={{ marginBottom: 20 }}>
                <div style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: PHASE_COLOR.deliberation, marginBottom: 10, paddingBottom: 4, borderBottom: "1px solid var(--border)" }}>
                  Phase II — Board Deliberation
                </div>
                {meeting.phase2_turns.map((t, i) => <TurnCard key={i} turn={t} />)}
              </div>
            )}
            {/* Phase III synthesis */}
            {synth?.recommendation && (
              <div style={{ marginBottom: 20 }}>
                <div style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: PHASE_COLOR.synthesis, marginBottom: 10, paddingBottom: 4, borderBottom: "1px solid var(--border)" }}>
                  Phase III — Chair Synthesis
                </div>
                <div style={{ border: "1px solid var(--border)", borderRadius: 3, padding: 12 }}>
                  <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
                    <span style={{ fontWeight: 700, fontSize: 12, color: "var(--success-text)", textTransform: "uppercase" }}>
                      Chair — Selection Reviewer
                    </span>
                    {confChip(synth.confidence ?? 0)}
                  </div>
                  <div style={{ fontSize: 14, fontWeight: 700, color: synth.recommendation === "ADVANCE" ? "var(--success-text)" : synth.recommendation === "DECLINE" ? "var(--danger-text)" : "var(--warning-text)", marginBottom: 8 }}>
                    {synth.recommendation} — TIER {synth.tier}
                  </div>
                  {(synth.agreements ?? []).length > 0 && (
                    <div style={{ marginBottom: 8 }}>
                      <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 3 }}>Agreements</div>
                      <ul className="bullet-list">{(synth.agreements ?? []).map((a, i) => <li key={i}>{a}</li>)}</ul>
                    </div>
                  )}
                  {(synth.open_questions ?? []).length > 0 && (
                    <div>
                      <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 3 }}>Open Questions</div>
                      <ul className="bullet-list concern">{(synth.open_questions ?? []).map((q, i) => <li key={i}>{q}</li>)}</ul>
                    </div>
                  )}
                </div>
              </div>
            )}
            {/* Live deliberating indicator */}
            {isLive && (
              <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "10px 0", color: "var(--warning-text)", fontSize: 12 }}>
                <span style={{
                  width: 8, height: 8, borderRadius: "50%", flexShrink: 0,
                  background: "var(--warning-text)",
                  boxShadow: "0 0 0 3px color-mix(in srgb, var(--warning) 20%, transparent)",
                  animation: "pulse 1.5s ease-in-out infinite",
                }} />
                Board is deliberating…
              </div>
            )}
          </>
        )}

        {tab === "notes" && (
          Object.keys(meeting.meeting_notes ?? {}).length > 0
            ? <MeetingNotes notes={meeting.meeting_notes} />
            : <p style={{ fontSize: 12, color: "var(--text-muted)" }}>
                {isLive ? "Meeting notes will appear when the board concludes." : "No meeting notes available."}
              </p>
        )}

        {tab === "opening" && (
          <div>
            {isLive && (meeting.phase1_turns?.filter(t => t.speaker !== "council_chair").length ?? 0) === 0 && (
              <p style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 12 }}>
                Opening statements will appear as each board member speaks.
              </p>
            )}
            {!isLive && (
              <p style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 12 }}>
                Individual opening statements from Phase I specialist agents.
              </p>
            )}
            {(meeting.phase1_turns ?? []).filter(t => t.speaker !== "council_chair").map((t, i) => (
              <div key={i} style={{ borderBottom: "1px solid var(--border)", paddingBottom: 10, marginBottom: 10 }}>
                <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 4 }}>
                  <span style={{ fontWeight: 600, fontSize: 12 }}>{t.display_name}</span>
                  {confChip(t.confidence)}
                </div>
                <div style={{ fontSize: 13, color: "var(--text)", marginBottom: 6 }}>{t.summary || t.content?.slice(0, 300)}</div>
                {t.strengths?.length > 0 && (
                  <div style={{ fontSize: 11, color: "var(--success-text)" }}>{t.strengths.slice(0, 2).join(" · ")}</div>
                )}
                {t.concerns?.length > 0 && (
                  <div style={{ fontSize: 11, color: "var(--warning-text)", marginTop: 2 }}>{t.concerns.slice(0, 2).join(" · ")}</div>
                )}
              </div>
            ))}
            {isLive && (meeting.phase1_turns?.filter(t => t.speaker !== "council_chair").length ?? 0) > 0 && (
              <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 0", color: "var(--warning-text)", fontSize: 12 }}>
                <span style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--warning-text)", animation: "pulse 1.5s ease-in-out infinite" }} />
                More agents speaking…
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export function ExpertCouncilPage() {
  const qc = useQueryClient();
  const casesQuery = useQuery({ queryKey: ["cases"], queryFn: listCases });
  const { caseId, selectCase } = useResolvedCaseId(casesQuery.data);
  const [selectedCandidateId, setSelectedCandidateId] = useState<string | null>(null);
  const [polling, setPolling] = useState(false);

  const reviewsQuery = useQuery({
    queryKey: ["expert-reviews", caseId],
    queryFn: () => listExpertReviewsForCase(caseId!),
    enabled: Boolean(caseId),
  });

  const meetingsQuery = useQuery({
    queryKey: ["board-meetings", caseId],
    queryFn: () => listBoardMeetings(caseId!),
    enabled: Boolean(caseId),
    refetchInterval: polling ? 5_000 : false,
    refetchIntervalInBackground: true,
  });

  const runMut = useMutation({
    mutationFn: () => queueExpertCouncil(caseId!),
    onSuccess() {
      setPolling(true);
      qc.invalidateQueries({ queryKey: ["expert-reviews", caseId] });
      qc.invalidateQueries({ queryKey: ["board-meetings", caseId] });
    },
  });

  const stopMut = useMutation({
    mutationFn: () => stopCouncil(caseId!),
    onSuccess() {
      setPolling(false);
      qc.invalidateQueries({ queryKey: ["board-meetings", caseId] });
    },
  });

  const deleteOneMut = useMutation({
    mutationFn: (candidateId: string) => deleteBoardMeeting(caseId!, candidateId),
    onSuccess(_data, candidateId) {
      if (selectedCandidateId === candidateId) setSelectedCandidateId(null);
      qc.invalidateQueries({ queryKey: ["board-meetings", caseId] });
      qc.invalidateQueries({ queryKey: ["board-meeting", caseId, candidateId] });
    },
  });

  const deleteAllMut = useMutation({
    mutationFn: () => deleteAllBoardMeetings(caseId!),
    onSuccess() {
      setSelectedCandidateId(null);
      setPolling(false);
      qc.invalidateQueries({ queryKey: ["board-meetings", caseId] });
    },
  });

  const meetings = meetingsQuery.data ?? [];
  const reviews = reviewsQuery.data ?? [];
  const reviewCount = reviews.length;

  // Auto-select first complete meeting when results load and nothing is selected
  useEffect(() => {
    if (!selectedCandidateId && meetings.length > 0 && !polling && !runMut.isPending) {
      const first = meetings.find(m => m.status === "complete") ?? meetings[0];
      if (first) setSelectedCandidateId(first.candidate_id);
    }
  }, [meetings, selectedCandidateId, polling, runMut.isPending]);

  const candidateCount = new Set(reviews.map(r => r.candidate_id)).size;
  // Stop polling once all candidates have COMPLETE transcripts
  const completeCount = meetings.filter(m => m.status === "complete").length;
  useEffect(() => {
    if (polling && completeCount > 0 && candidateCount > 0 && completeCount >= candidateCount) {
      setPolling(false);
    }
  }, [polling, completeCount, candidateCount]);

  const isRunning = polling || runMut.isPending;

  const meetingByCandidateId = new Map(meetings.map(m => [m.candidate_id, m]));
  const candidatesFromReviews = Object.values(
    reviews.reduce<Record<string, { id: string; name: string }>>((acc, r) => {
      if (!acc[r.candidate_id]) acc[r.candidate_id] = { id: r.candidate_id, name: r.candidate_name };
      return acc;
    }, {})
  );
  const meetingCandidates = meetings.map(m => ({ id: m.candidate_id, name: m.candidate_name }));
  const allCandidateIds = new Set([...meetingCandidates.map(c => c.id), ...candidatesFromReviews.map(c => c.id)]);
  const candidates = Array.from(allCandidateIds).map(id => {
    const fromMeeting = meetingCandidates.find(c => c.id === id);
    const fromReview = candidatesFromReviews.find(c => c.id === id);
    return { id, name: fromMeeting?.name ?? fromReview?.name ?? id };
  });

  return (
    <div className="workspace" style={{ display: "flex", flexDirection: "row", overflow: "hidden" }}>
      {/* Left: candidate list */}
      <div style={{
        width: 240,
        flexShrink: 0,
        display: "flex",
        flexDirection: "column",
        height: "100%",
        overflow: "hidden",
        borderRight: "1px solid var(--border)",
      }}>
        <div className="panel-head" style={{ flexShrink: 0 }}>
          <span className="panel-head-title">Board Meetings</span>
        </div>
        <div style={{ padding: "8px 10px", borderBottom: "1px solid var(--border)", flexShrink: 0 }}>
          <select
            className="select-input"
            style={{ width: "100%", height: 26 }}
            value={caseId ?? ""}
            onChange={e => { selectCase(e.target.value || null); setSelectedCandidateId(null); }}
          >
            <option value="">— Select engagement —</option>
            {(casesQuery.data ?? []).map(c => <option key={c.id} value={c.id}>{c.title}</option>)}
          </select>
        </div>

        {/* Candidate list */}
        <div style={{ overflowY: "auto", flex: 1, minHeight: 0 }}>
          {!caseId && <p className="loading-text" style={{ fontSize: 12 }}>Select an engagement</p>}
          {caseId && candidates.length === 0 && (
            <p className="loading-text" style={{ fontSize: 12 }}>
              {meetingsQuery.isLoading ? "Loading…" : "No candidates found"}
            </p>
          )}
          {candidates.map(c => {
            const meeting = meetingByCandidateId.get(c.id);
            const isActive = c.id === selectedCandidateId;
            const isLive = meeting?.status === "in_progress";
            const isDone = meeting?.status === "complete";
            return (
              <div
                key={c.id}
                onClick={() => setSelectedCandidateId(c.id)}
                style={{
                  padding: "8px 12px",
                  cursor: "pointer",
                  borderBottom: "1px solid var(--border)",
                  background: isActive ? "var(--row-selected)" : "transparent",
                  borderLeft: isActive ? "2px solid var(--brand)" : "2px solid transparent",
                  position: "relative",
                }}
              >
                <div style={{ display: "flex", alignItems: "center" }}>
                  <span style={{ fontWeight: 600, fontSize: 13, flex: 1 }}>{c.name}</span>
                  {meeting && !isRunning && (
                    <button
                      onClick={e => { e.stopPropagation(); deleteOneMut.mutate(c.id); }}
                      title="Delete transcript"
                      style={{ background: "none", border: "none", color: "var(--text-dim)", cursor: "pointer", fontSize: 14, lineHeight: 1, padding: "0 2px", flexShrink: 0 }}
                    >×</button>
                  )}
                </div>
                {isDone ? (
                  <div style={{ display: "flex", gap: 6, marginTop: 3, flexWrap: "wrap" }}>
                    <span className="chip chip-success" style={{ fontSize: 10 }}>complete</span>
                    {meeting?.phase3_synthesis?.tier && (
                      <span className={`chip chip-tier-${(meeting.phase3_synthesis.tier ?? "").toLowerCase()}`} style={{ fontSize: 10 }}>
                        Tier {meeting.phase3_synthesis.tier}
                      </span>
                    )}
                    {meeting?.phase3_synthesis?.recommendation && (
                      <span className={`chip ${meeting.phase3_synthesis.recommendation === "ADVANCE" ? "chip-success" : "chip-dim"}`} style={{ fontSize: 10 }}>
                        {meeting.phase3_synthesis.recommendation}
                      </span>
                    )}
                  </div>
                ) : isLive ? (
                  <div style={{ display: "flex", alignItems: "center", gap: 5, marginTop: 3 }}>
                    <span style={{
                      width: 6, height: 6, borderRadius: "50%",
                      background: "var(--warning-text)",
                      animation: "pulse 1.5s ease-in-out infinite",
                    }} />
                    <span style={{ fontSize: 11, color: "var(--warning-text)" }}>
                      live · {meeting?.phase1_turns?.filter(t => t.speaker !== "council_chair").length ?? 0} agents spoken
                    </span>
                  </div>
                ) : (
                  <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 2 }}>
                    {isRunning ? "waiting…" : "reviews only"}
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* Footer */}
        <div style={{ flexShrink: 0, padding: "10px 12px", borderTop: "1px solid var(--border)", display: "flex", flexDirection: "column", gap: 6, background: "var(--panel-bg)" }}>
          <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
            {isRunning
              ? `${completeCount}/${candidateCount || "?"} complete · updates every 5s`
              : `${meetings.length} meeting${meetings.length !== 1 ? "s" : ""} · ${reviewCount} reviews`
            }
          </div>
          {caseId && !isRunning && meetings.length === 0 && (
            <>
              <div style={{ fontSize: 11, color: "var(--text-dim)", lineHeight: 1.4 }}>
                The Expert Council runs automatically with Resume Review. Use this to run it separately or re-run after changes.
              </div>
              <button
                className="btn btn-primary"
                style={{ width: "100%" }}
                onClick={() => runMut.mutate()}
              >
                Run Expert Council
              </button>
            </>
          )}
          {caseId && !isRunning && meetings.length > 0 && (
            <button
              className="btn"
              style={{ width: "100%", opacity: 0.7 }}
              onClick={() => runMut.mutate()}
            >
              Re-run Expert Council
            </button>
          )}
          {caseId && isRunning && (
            <button
              className="btn btn-danger"
              style={{ width: "100%" }}
              disabled={stopMut.isPending}
              onClick={() => stopMut.mutate()}
            >
              {stopMut.isPending ? "Stopping…" : "Stop Council"}
            </button>
          )}
          {caseId && meetings.length > 0 && !isRunning && (
            <button
              className="btn"
              style={{ width: "100%", fontSize: 11 }}
              disabled={deleteAllMut.isPending}
              onClick={() => { if (confirm("Delete all board meeting transcripts for this engagement?")) deleteAllMut.mutate(); }}
            >
              {deleteAllMut.isPending ? "Deleting…" : "Clear all transcripts"}
            </button>
          )}
          {(isRunning) && (
            <div style={{ fontSize: 11, color: "var(--warning-text)", lineHeight: 1.4 }}>
              Click any candidate to watch live · ~3–4 min per candidate
            </div>
          )}
          {runMut.isError && (
            <div className="feedback-error" style={{ fontSize: 11 }}>Council run failed</div>
          )}
          {stopMut.isError && (
            <div className="feedback-error" style={{ fontSize: 11 }}>Stop request failed</div>
          )}
        </div>
      </div>

      {/* Right: meeting detail or progress screen */}
      <div style={{ flex: 1, overflow: "hidden", display: "flex", flexDirection: "column" }}>
        {!caseId && (
          <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
            <p className="select-prompt">Select an engagement to view board meetings</p>
          </div>
        )}
        {caseId && selectedCandidateId && (
          <MeetingDetail
            caseId={caseId}
            candidateId={selectedCandidateId}
            isRunning={isRunning}
            caseTitle={(casesQuery.data ?? []).find(c => c.id === caseId)?.title ?? ""}
          />
        )}
        {caseId && !selectedCandidateId && (
          <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 16 }}>
            {isRunning ? (
              <div style={{ width: "100%", maxWidth: 520, padding: "0 24px" }}>
                <div style={{ fontSize: 15, fontWeight: 600, color: "var(--warning-text)", marginBottom: 4 }}>
                  Board deliberating…
                </div>
                <div style={{ fontSize: 12, color: "var(--text-dim)", marginBottom: 20 }}>
                  {completeCount}/{candidateCount || "?"} complete · updates every 5s · click any candidate to watch live
                </div>
                {candidates.map(c => {
                  const meeting = meetingByCandidateId.get(c.id);
                  const isDone = meeting?.status === "complete";
                  const isLive = meeting?.status === "in_progress";
                  return (
                    <div
                      key={c.id}
                      onClick={() => setSelectedCandidateId(c.id)}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 10,
                        padding: "8px 12px",
                        marginBottom: 6,
                        border: "1px solid var(--border)",
                        borderRadius: 3,
                        cursor: "pointer",
                        background: isDone
                          ? "color-mix(in srgb, var(--success) 6%, transparent)"
                          : isLive
                          ? "color-mix(in srgb, var(--warning) 6%, transparent)"
                          : "transparent",
                      }}
                    >
                      <span style={{
                        width: 8, height: 8, borderRadius: "50%", flexShrink: 0,
                        background: isDone ? "var(--success-text)" : isLive ? "var(--warning-text)" : "var(--text-dim)",
                        boxShadow: isLive ? "0 0 0 3px color-mix(in srgb, var(--warning) 20%, transparent)" : "none",
                        animation: isLive ? "pulse 1.5s ease-in-out infinite" : "none",
                      }} />
                      <span style={{ flex: 1, fontSize: 13, fontWeight: 600 }}>{c.name}</span>
                      {isDone ? (
                        <div style={{ display: "flex", gap: 6 }}>
                          <span className="chip chip-success" style={{ fontSize: 10 }}>done</span>
                          {meeting?.phase3_synthesis?.tier && (
                            <span className={`chip chip-tier-${(meeting.phase3_synthesis.tier ?? "").toLowerCase()}`} style={{ fontSize: 10 }}>
                              Tier {meeting.phase3_synthesis.tier}
                            </span>
                          )}
                          {meeting?.phase3_synthesis?.recommendation && (
                            <span className={`chip ${meeting.phase3_synthesis.recommendation === "ADVANCE" ? "chip-success" : "chip-dim"}`} style={{ fontSize: 10 }}>
                              {meeting.phase3_synthesis.recommendation}
                            </span>
                          )}
                        </div>
                      ) : isLive ? (
                        <span style={{ fontSize: 11, color: "var(--warning-text)" }}>
                          {meeting?.phase1_turns?.filter(t => t.speaker !== "council_chair").length ?? 0} agents · click to watch
                        </span>
                      ) : (
                        <span style={{ fontSize: 11, color: "var(--text-dim)" }}>waiting…</span>
                      )}
                    </div>
                  );
                })}
                {candidates.length === 0 && (
                  <div style={{ fontSize: 12, color: "var(--text-muted)" }}>Waiting for first candidate…</div>
                )}
              </div>
            ) : meetings.length > 0 ? (
              <p className="select-prompt">Select a candidate to view their board meeting transcript</p>
            ) : (
              <>
                <p className="select-prompt">No board meetings yet — run Expert Council or launch Resume Review</p>
                <button
                  className="btn btn-primary btn-lg"
                  disabled={isRunning}
                  onClick={() => runMut.mutate()}
                >
                  Run Expert Council
                </button>
                {runMut.isError && (
                  <div className="feedback-error">Council run failed. Check logs.</div>
                )}
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
