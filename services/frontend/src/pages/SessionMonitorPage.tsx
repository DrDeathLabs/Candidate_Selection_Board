import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { listAllSessions, revokeSession, type GlobalSessionRecord } from "../lib/api";

function sessionStatus(session: GlobalSessionRecord): { label: string; color: string } {
  const now = Date.now();
  const idleMs = new Date(session.idle_expires_at).getTime() - now;
  const absMs = new Date(session.absolute_expires_at).getTime() - now;
  if (idleMs < 5 * 60 * 1000) return { label: "idle expiring", color: "var(--warning-text, #d69e2e)" };
  if (absMs < 30 * 60 * 1000) return { label: "near expiry", color: "var(--warning-text, #d69e2e)" };
  return { label: "active", color: "var(--success-text, #38a169)" };
}

function fmtTime(iso: string) {
  return new Date(iso).toLocaleString();
}

function minUntil(iso: string) {
  const diff = new Date(iso).getTime() - Date.now();
  if (diff <= 0) return "expired";
  const m = Math.floor(diff / 60000);
  if (m < 60) return `${m}m`;
  return `${Math.floor(m / 60)}h ${m % 60}m`;
}

export function SessionMonitorPage() {
  const qc = useQueryClient();

  const { data, isLoading, isError } = useQuery({
    queryKey: ["sessions"],
    queryFn: () => listAllSessions({ limit: 500 }),
    refetchInterval: 60_000,
  });

  const revokeMutation = useMutation({
    mutationFn: (sessionId: string) => revokeSession(sessionId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sessions"] }),
  });

  const sessions = data?.data ?? [];
  const total = data?.total ?? 0;

  const uniqueUsers = new Set(sessions.map(s => s.user_id)).size;
  const expiringSoon = sessions.filter(s => {
    const ms = new Date(s.idle_expires_at).getTime() - Date.now();
    return ms > 0 && ms < 30 * 60 * 1000;
  }).length;

  return (
    <div style={{ padding: "20px 24px", maxWidth: 1400 }}>
      <div style={{ marginBottom: 16 }}>
        <h2 style={{ margin: 0, fontSize: 18, fontWeight: 600 }}>Session Monitor</h2>
        <p style={{ margin: "4px 0 0", fontSize: 12, color: "var(--text-dim)" }}>
          All active sessions across all users. Auto-refreshes every 60 seconds.
        </p>
      </div>

      {/* Stats row */}
      <div style={{ display: "flex", gap: 12, marginBottom: 18 }}>
        {[
          { label: "Total Active", value: isLoading ? "…" : total },
          { label: "Unique Users", value: isLoading ? "…" : uniqueUsers },
          { label: "Idle Expiring Soon", value: isLoading ? "…" : expiringSoon, warn: expiringSoon > 0 },
        ].map(stat => (
          <div key={stat.label} style={{
            padding: "10px 16px", background: "var(--surface)", border: "1px solid var(--border)",
            borderRadius: 6, minWidth: 120,
          }}>
            <div style={{ fontSize: 22, fontWeight: 700, color: stat.warn ? "var(--warning-text, #d69e2e)" : "var(--text)" }}>
              {stat.value}
            </div>
            <div style={{ fontSize: 11, color: "var(--text-dim)", marginTop: 2 }}>{stat.label}</div>
          </div>
        ))}
      </div>

      {isError && (
        <div style={{ padding: 12, background: "rgba(229,62,62,0.1)", border: "1px solid rgba(229,62,62,0.3)", borderRadius: 4, color: "var(--danger-text, #e53e3e)", fontSize: 13, marginBottom: 12 }}>
          Failed to load sessions.
        </div>
      )}

      <div style={{ overflowX: "auto" }}>
        <table className="tbl" style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
          <thead>
            <tr style={{ background: "var(--surface)", borderBottom: "2px solid var(--border)" }}>
              {["Username", "Roles", "IP", "User Agent", "Created", "Last Activity", "Idle Expires", "Abs Expires", "Status", ""].map(h => (
                <th key={h} style={{ padding: "6px 8px", textAlign: "left", fontWeight: 600, color: "var(--text-dim)", whiteSpace: "nowrap" }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr><td colSpan={10} style={{ padding: 24, textAlign: "center", color: "var(--text-dim)" }}>Loading…</td></tr>
            )}
            {!isLoading && sessions.length === 0 && (
              <tr><td colSpan={10} style={{ padding: 24, textAlign: "center", color: "var(--text-dim)" }}>No active sessions.</td></tr>
            )}
            {sessions.map(s => {
              const st = sessionStatus(s);
              return (
                <tr key={s.id} style={{ borderBottom: "1px solid var(--border)" }}>
                  <td style={{ padding: "5px 8px", fontWeight: 500 }}>{s.username}</td>
                  <td style={{ padding: "5px 8px", color: "var(--text-dim)", fontSize: 11 }}>
                    {s.roles.map(r => r.replace(/_/g, " ")).join(", ")}
                  </td>
                  <td style={{ padding: "5px 8px", fontFamily: "monospace", fontSize: 11, color: "var(--text-dim)" }}>
                    {s.ip_address ?? "—"}
                  </td>
                  <td style={{ padding: "5px 8px", maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", color: "var(--text-dim)", fontSize: 11 }}>
                    <span title={s.user_agent ?? ""}>{(s.user_agent ?? "—").slice(0, 40)}{(s.user_agent?.length ?? 0) > 40 ? "…" : ""}</span>
                  </td>
                  <td style={{ padding: "5px 8px", whiteSpace: "nowrap", color: "var(--text-dim)", fontSize: 11 }}>{fmtTime(s.created_at)}</td>
                  <td style={{ padding: "5px 8px", whiteSpace: "nowrap", color: "var(--text-dim)", fontSize: 11 }}>{fmtTime(s.last_activity_at)}</td>
                  <td style={{ padding: "5px 8px", whiteSpace: "nowrap", fontFamily: "monospace", fontSize: 11, color: "var(--text-dim)" }}>
                    {minUntil(s.idle_expires_at)}
                  </td>
                  <td style={{ padding: "5px 8px", whiteSpace: "nowrap", fontFamily: "monospace", fontSize: 11, color: "var(--text-dim)" }}>
                    {minUntil(s.absolute_expires_at)}
                  </td>
                  <td style={{ padding: "5px 8px", whiteSpace: "nowrap" }}>
                    <span style={{ fontSize: 11, fontWeight: 500, color: st.color }}>{st.label}</span>
                  </td>
                  <td style={{ padding: "5px 8px" }}>
                    <button
                      onClick={() => {
                        if (confirm(`Revoke session for ${s.username}?`)) revokeMutation.mutate(s.id);
                      }}
                      disabled={revokeMutation.isPending}
                      style={{ fontSize: 11, padding: "2px 8px", background: "transparent", border: "1px solid rgba(229,62,62,0.5)", borderRadius: 4, color: "var(--danger-text, #e53e3e)", cursor: "pointer" }}
                    >
                      Revoke
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
