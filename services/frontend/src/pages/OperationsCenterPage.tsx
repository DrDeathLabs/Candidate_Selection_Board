import { useQuery } from "@tanstack/react-query";

import { getOperationsOverview, getServiceHealth, type ServiceStatusRecord } from "../lib/api";

function StatusDot({ status }: { status: ServiceStatusRecord["status"] }) {
  const color = status === "up" ? "var(--success-text, #38a169)" : status === "degraded" ? "var(--warning-text, #d69e2e)" : "var(--danger-text, #e53e3e)";
  return <span style={{ display: "inline-block", width: 8, height: 8, borderRadius: "50%", background: color, marginRight: 6, flexShrink: 0 }} />;
}

export function OperationsCenterPage() {
  const overviewQuery = useQuery({ queryKey: ["ops-overview"], queryFn: getOperationsOverview });
  const healthQuery = useQuery({ queryKey: ["service-health"], queryFn: getServiceHealth, refetchInterval: 60_000 });

  const ops = overviewQuery.data;
  const health = healthQuery.data;

  return (
    <div className="workspace">
      <div className="panel panel-flex" style={{ overflowY: "auto" }}>
        <div className="panel-head">
          <span className="panel-head-title">Operations Center</span>
        </div>
        <div className="admin-content">

          {/* Service Health */}
          <div className="settings-section">
            <div className="settings-section-head" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span>Service Health</span>
              {health && <span style={{ fontSize: 10, color: "var(--text-dim)", fontWeight: 400 }}>checked {new Date(health.checked_at).toLocaleTimeString()}</span>}
            </div>
            {healthQuery.isLoading && <div style={{ padding: "8px 0", fontSize: 12, color: "var(--text-dim)" }}>Checking services…</div>}
            {healthQuery.isError && <div style={{ padding: "8px 0", fontSize: 12, color: "var(--danger-text, #e53e3e)" }}>Health check failed.</div>}
            {health && health.services.map(svc => (
              <div key={svc.name} className="settings-row" style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <StatusDot status={svc.status} />
                <span className="settings-key" style={{ fontFamily: "monospace", textTransform: "lowercase" }}>{svc.name}</span>
                <span style={{ fontSize: 11, fontWeight: 600, color: svc.status === "up" ? "var(--success-text, #38a169)" : svc.status === "degraded" ? "var(--warning-text, #d69e2e)" : "var(--danger-text, #e53e3e)", textTransform: "uppercase" }}>
                  {svc.status}
                </span>
                {svc.latency_ms != null && (
                  <span style={{ fontSize: 11, color: "var(--text-dim)" }}>{svc.latency_ms}ms</span>
                )}
                <span style={{ fontSize: 11, color: "var(--text-dim)", marginLeft: 4 }}>{svc.detail}</span>
              </div>
            ))}
          </div>

          {ops && (
            <>
              <div className="settings-section">
                <div className="settings-section-head">System Status</div>
                <div className="settings-row"><span className="settings-key">Active Engagements</span><span className="settings-val">{ops.active_case_count}</span></div>
                <div className="settings-row"><span className="settings-key">Default Provider</span><span className="settings-val">{ops.default_provider}</span></div>
                <div className="settings-row"><span className="settings-key">Enabled Agents</span><span className="settings-val">{ops.enabled_agent_count}</span></div>
                <div className="settings-row"><span className="settings-key">Export Queue</span><span className="settings-val">{ops.export_queue_count}</span></div>
              </div>

              <div className="settings-section">
                <div className="settings-section-head">Document Processing</div>
                {Object.entries(ops.document_status_counts).map(([k, v]) => (
                  <div key={k} className="settings-row">
                    <span className="settings-key">{k}</span>
                    <span className="settings-val">{v}</span>
                  </div>
                ))}
              </div>

            </>
          )}

        </div>
      </div>
    </div>
  );
}
