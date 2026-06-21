import { useQuery } from "@tanstack/react-query";
import { NavLink } from "react-router-dom";

import { getAdminSettings, getOperationsOverview } from "../lib/api";

export function AdminPage() {
  const settingsQuery = useQuery({ queryKey: ["admin-settings"], queryFn: getAdminSettings });
  const opsQuery = useQuery({ queryKey: ["ops-overview"], queryFn: getOperationsOverview });

  const ops = opsQuery.data;

  return (
    <div className="workspace">
      <div className="panel panel-200">
        <div className="panel-head">
          <span className="panel-head-title">Admin</span>
        </div>
        <nav style={{ padding: "8px 0" }}>
          {[
            { to: "/admin/ai", label: "AI Settings" },
            { to: "/admin/agents", label: "Agent Config" },
            { to: "/admin/operations", label: "Operations" },
            { to: "/admin/security", label: "Security" },
          ].map(item => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) => `admin-nav-item${isActive ? " active" : ""}`}
            >
              {item.label}
            </NavLink>
          ))}
          <div style={{ height: 1, background: "var(--border)", margin: "4px 8px" }} />
          {[
            { to: "/admin/users", label: "User Management" },
            { to: "/admin/soc-log", label: "SOC Log" },
            { to: "/admin/sessions", label: "Session Monitor" },
          ].map(item => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) => `admin-nav-item${isActive ? " active" : ""}`}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      </div>

      <div className="panel panel-flex" style={{ overflowY: "auto" }}>
        <div className="panel-head">
          <span className="panel-head-title">System Overview</span>
        </div>
        <div className="admin-content">
          {ops ? (
            <>
              <div className="settings-section">
                <div className="settings-section-head">Engagement Status</div>
                {Object.entries(ops.case_status_counts).map(([k, v]) => (
                  <div key={k} className="settings-row">
                    <span className="settings-key">{k}</span>
                    <span className="settings-val">{v}</span>
                  </div>
                ))}
                <div className="settings-row">
                  <span className="settings-key">Active Engagements</span>
                  <span className="settings-val">{ops.active_case_count}</span>
                </div>
              </div>

              <div className="settings-section">
                <div className="settings-section-head">Agents &amp; AI</div>
                <div className="settings-row">
                  <span className="settings-key">Default Provider</span>
                  <span className="settings-val">{ops.default_provider}</span>
                </div>
                <div className="settings-row">
                  <span className="settings-key">Enabled Agents</span>
                  <span className="settings-val">{ops.enabled_agent_count}</span>
                </div>
                <div className="settings-row">
                  <span className="settings-key">Export Queue</span>
                  <span className="settings-val">{ops.export_queue_count}</span>
                </div>
              </div>

            </>
          ) : (
            <p className="loading-text">{opsQuery.isLoading ? "Loading…" : "Could not load operations overview"}</p>
          )}

          {settingsQuery.data && (
            <div className="settings-section">
              <div className="settings-section-head">Session</div>
              <div className="settings-row">
                <span className="settings-key">User</span>
                <span className="settings-val">{settingsQuery.data.user}</span>
              </div>
              <div className="settings-row">
                <span className="settings-key">Permissions</span>
                <span className="settings-val">{settingsQuery.data.allowed_actions.join(", ")}</span>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
