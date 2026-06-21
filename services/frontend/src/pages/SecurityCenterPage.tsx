import { useQuery } from "@tanstack/react-query";

import { getSecurityPosture, type FismaControlStatusRecord } from "../lib/api";

function ControlStatusChip({ status }: { status: FismaControlStatusRecord["status"] }) {
  const color = status === "pass" ? "var(--success-text, #38a169)" : status === "warn" ? "var(--warning-text, #d69e2e)" : "var(--danger-text, #e53e3e)";
  const bg = status === "pass" ? "rgba(56,161,105,0.12)" : status === "warn" ? "rgba(214,158,46,0.12)" : "rgba(229,62,62,0.12)";
  return (
    <span style={{ fontSize: 10, fontWeight: 700, padding: "2px 6px", borderRadius: 3, color, background: bg, textTransform: "uppercase", letterSpacing: "0.06em" }}>
      {status}
    </span>
  );
}

export function SecurityCenterPage() {
  const postureQuery = useQuery({ queryKey: ["security-posture"], queryFn: getSecurityPosture });
  const posture = postureQuery.data;

  return (
    <div className="workspace">
      <div className="panel panel-flex" style={{ overflowY: "auto" }}>
        <div className="panel-head">
          <span className="panel-head-title">Security Center</span>
        </div>
        <div className="admin-content">

          {/* FISMA Control Posture */}
          {posture && (
            <div className="settings-section">
              <div className="settings-section-head">FISMA Moderate Control Posture</div>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid var(--border)" }}>
                    <th style={{ padding: "4px 8px", textAlign: "left", color: "var(--text-dim)", fontWeight: 600, width: 60 }}>ID</th>
                    <th style={{ padding: "4px 8px", textAlign: "left", color: "var(--text-dim)", fontWeight: 600 }}>Control</th>
                    <th style={{ padding: "4px 8px", textAlign: "center", color: "var(--text-dim)", fontWeight: 600, width: 70 }}>Status</th>
                    <th style={{ padding: "4px 8px", textAlign: "left", color: "var(--text-dim)", fontWeight: 600 }}>Detail</th>
                  </tr>
                </thead>
                <tbody>
                  {posture.fisma_controls.map(c => (
                    <tr key={c.id} style={{ borderBottom: "1px solid var(--border)" }}>
                      <td style={{ padding: "5px 8px", fontFamily: "monospace", fontWeight: 700, fontSize: 12, color: "var(--text)" }}>{c.id}</td>
                      <td style={{ padding: "5px 8px" }}>{c.title}</td>
                      <td style={{ padding: "5px 8px", textAlign: "center" }}><ControlStatusChip status={c.status} /></td>
                      <td style={{ padding: "5px 8px", color: "var(--text-dim)", fontSize: 11 }}>{c.detail}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Account Security Health */}
          {posture && (
            <div className="settings-section">
              <div className="settings-section-head">Account Security Health</div>
              <div className="settings-row"><span className="settings-key">Total Users</span><span className="settings-val">{posture.account_stats.total_users}</span></div>
              <div className="settings-row"><span className="settings-key">Active Users</span><span className="settings-val">{posture.account_stats.active_users}</span></div>
              <div className="settings-row">
                <span className="settings-key">Locked Accounts</span>
                <span className="settings-val" style={{ color: posture.account_stats.locked_users > 0 ? "var(--warning-text, #d69e2e)" : undefined }}>
                  {posture.account_stats.locked_users}
                </span>
              </div>
              <div className="settings-row">
                <span className="settings-key">Users Without MFA</span>
                <span className="settings-val" style={{ color: posture.account_stats.users_without_mfa > 0 ? "var(--warning-text, #d69e2e)" : undefined }}>
                  {posture.account_stats.users_without_mfa}
                </span>
              </div>
              <div className="settings-row"><span className="settings-key">Users with TOTP Enrolled</span><span className="settings-val">{posture.account_stats.users_with_totp}</span></div>
              <div className="settings-row">
                <span className="settings-key">Stale Accounts (&gt;90 days)</span>
                <span className="settings-val" style={{ color: posture.account_stats.users_without_recent_login > 0 ? "var(--warning-text, #d69e2e)" : undefined }}>
                  {posture.account_stats.users_without_recent_login}
                </span>
              </div>
              <div className="settings-row"><span className="settings-key">Active Sessions</span><span className="settings-val">{posture.active_sessions}</span></div>
            </div>
          )}

          {/* Auth Activity */}
          {posture && (
            <div className="settings-section">
              <div className="settings-section-head">Authentication Activity (Last 24h)</div>
              <div className="settings-row"><span className="settings-key">Successful Logins</span><span className="settings-val">{posture.auth_events_24h.logins}</span></div>
              <div className="settings-row">
                <span className="settings-key">Failed Logins</span>
                <span className="settings-val" style={{ color: posture.auth_events_24h.failed_logins > 0 ? "var(--warning-text, #d69e2e)" : undefined }}>
                  {posture.auth_events_24h.failed_logins}
                </span>
              </div>
              <div className="settings-row">
                <span className="settings-key">Account Lockouts</span>
                <span className="settings-val" style={{ color: posture.auth_events_24h.lockouts > 0 ? "var(--danger-text, #e53e3e)" : undefined }}>
                  {posture.auth_events_24h.lockouts}
                </span>
              </div>
              <div className="settings-row"><span className="settings-key">Password Changes</span><span className="settings-val">{posture.auth_events_24h.password_changes}</span></div>
              <div className="settings-row"><span className="settings-key">MFA Enrollments</span><span className="settings-val">{posture.auth_events_24h.mfa_enrollments}</span></div>

              {posture.recent_auth_events.length > 0 && (
                <div style={{ marginTop: 10 }}>
                  <div style={{ fontSize: 11, color: "var(--text-dim)", fontWeight: 600, marginBottom: 6, textTransform: "uppercase", letterSpacing: "0.05em" }}>Recent Auth Events</div>
                  <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
                    <thead>
                      <tr style={{ borderBottom: "1px solid var(--border)" }}>
                        <th style={{ padding: "3px 6px", textAlign: "left", color: "var(--text-dim)", fontWeight: 600 }}>Time</th>
                        <th style={{ padding: "3px 6px", textAlign: "left", color: "var(--text-dim)", fontWeight: 600 }}>Event</th>
                        <th style={{ padding: "3px 6px", textAlign: "left", color: "var(--text-dim)", fontWeight: 600 }}>Actor</th>
                        <th style={{ padding: "3px 6px", textAlign: "left", color: "var(--text-dim)", fontWeight: 600 }}>IP</th>
                      </tr>
                    </thead>
                    <tbody>
                      {posture.recent_auth_events.slice(0, 5).map((e, i) => (
                        <tr key={i} style={{ borderBottom: "1px solid var(--border)" }}>
                          <td style={{ padding: "3px 6px", fontFamily: "monospace", color: "var(--text-dim)" }}>{new Date(String(e.occurred_at)).toLocaleTimeString()}</td>
                          <td style={{ padding: "3px 6px", fontFamily: "monospace", fontWeight: 600, color: String(e.event_type).includes("fail") || String(e.event_type).includes("lock") ? "var(--danger-text, #e53e3e)" : "var(--text)" }}>{String(e.event_type)}</td>
                          <td style={{ padding: "3px 6px", fontFamily: "monospace" }}>{String(e.actor_id)}</td>
                          <td style={{ padding: "3px 6px", fontFamily: "monospace", color: "var(--text-dim)" }}>{String(e.source_ip ?? "—")}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

        </div>
      </div>
    </div>
  );
}
