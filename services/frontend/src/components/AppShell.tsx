import { Outlet, NavLink, useMatch, useNavigate } from "react-router-dom";
import { useCaseContext } from "../app/case-context";
import { useAuth } from "../app/auth-context";

export function AppShell() {
  const { activeCase } = useCaseContext();
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const engagementMatch = useMatch("/engagements/:engagementId/*");
  const engagementId = engagementMatch?.params.engagementId;
  const engagementName = activeCase?.title ?? null;

  async function handleLogout() {
    await logout();
    navigate("/login", { replace: true });
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <NavLink to="/engagements" className="topbar-brand" style={{ textDecoration: "none" }}>CANDIDATE SELECTION BOARD</NavLink>
        <nav className="topbar-nav">
          <NavLink to="/engagements" className={({ isActive }) => isActive ? "active" : ""}>
            Engagements
          </NavLink>
          <NavLink to="/admin" className={({ isActive }) => isActive ? "active" : ""}>
            Admin
          </NavLink>
        </nav>
        <div className="topbar-right">
          {engagementId && engagementName && (
            <>
              <span className="topbar-engagement-name">{engagementName}</span>
              <nav className="topbar-tabs">
                <NavLink to={`/engagements/${engagementId}/prep`} className={({ isActive }) => isActive ? "active" : ""}>
                  Intake
                </NavLink>
                <NavLink to={`/engagements/${engagementId}/review`} className={({ isActive }) => isActive ? "active" : ""}>
                  Review
                </NavLink>
                <NavLink to={`/engagements/${engagementId}/decision`} className={({ isActive }) => isActive ? "active" : ""}>
                  Decision
                </NavLink>
                <NavLink to={`/expert-council?caseId=${engagementId}`} className={({ isActive }) => isActive ? "active" : ""}>
                  Council
                </NavLink>
              </nav>
            </>
          )}
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginLeft: 16, paddingLeft: 16, borderLeft: "1px solid var(--border)" }}>
            {user && (
              <span style={{ fontSize: 12, color: "var(--text-dim)" }}>
                {user.display_name || user.username}
                <span style={{ marginLeft: 6, fontSize: 11, color: "var(--text-muted, var(--text-dim))", opacity: 0.7 }}>
                  [{(user.roles[0] ?? "").replace(/_/g, " ")}]
                </span>
              </span>
            )}
            <button
              onClick={handleLogout}
              style={{
                fontSize: 11,
                padding: "3px 10px",
                background: "transparent",
                border: "1px solid var(--border)",
                borderRadius: 4,
                color: "var(--text-dim)",
                cursor: "pointer",
              }}
            >
              Sign out
            </button>
          </div>
        </div>
      </header>
      <Outlet />
    </div>
  );
}
