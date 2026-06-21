import axios from "axios";
import { useEffect, useState } from "react";

const BASE = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";

type UserRecord = {
  id: string;
  username: string;
  email: string;
  display_name: string | null;
  roles: string[];
  is_active: boolean;
  is_mfa_required: boolean;
  totp_enrolled: boolean;
  failed_login_count: number;
  is_locked: boolean;
  last_login_at: string | null;
};

type CreateUserForm = {
  username: string;
  email: string;
  display_name: string;
  password: string;
  roles: string;
  is_mfa_required: boolean;
};

const ALL_ROLES = [
  "system_administrator",
  "case_owner",
  "selecting_official",
  "panel_reviewer",
  "hr_reviewer",
  "read_only_auditor",
  "security_administrator",
];

export function AdminUsersPage() {
  const [users, setUsers] = useState<UserRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState<CreateUserForm>({
    username: "",
    email: "",
    display_name: "",
    password: "",
    roles: "panel_reviewer",
    is_mfa_required: true,
  });
  const [createError, setCreateError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const res = await axios.get<UserRecord[]>(`${BASE}/admin/users/`, { withCredentials: true });
      setUsers(res.data);
    } catch {
      setError("Failed to load users. You may not have administrator access.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  async function createUser(e: React.FormEvent) {
    e.preventDefault();
    setCreateError(null);
    try {
      await axios.post(
        `${BASE}/admin/users/`,
        {
          username: form.username,
          email: form.email,
          display_name: form.display_name || null,
          password: form.password,
          roles: form.roles.split(",").map((r) => r.trim()).filter(Boolean),
          is_mfa_required: form.is_mfa_required,
        },
        { withCredentials: true },
      );
      setShowCreate(false);
      setForm({ username: "", email: "", display_name: "", password: "", roles: "panel_reviewer", is_mfa_required: true });
      await load();
    } catch (err: any) {
      setCreateError(err?.response?.data?.detail ?? "Failed to create user.");
    }
  }

  async function doAction(userId: string, action: "disable" | "enable" | "unlock") {
    setActionError(null);
    try {
      await axios.post(`${BASE}/admin/users/${userId}/${action}`, {}, { withCredentials: true });
      await load();
    } catch (err: any) {
      setActionError(err?.response?.data?.detail ?? `Action "${action}" failed.`);
    }
  }

  const tdStyle: React.CSSProperties = { padding: "6px 10px", borderBottom: "1px solid var(--border)", fontSize: 12 };
  const thStyle: React.CSSProperties = { ...tdStyle, fontWeight: 600, textAlign: "left", color: "var(--text-dim)", fontSize: 11, textTransform: "uppercase" as const, letterSpacing: "0.04em" };

  return (
    <div style={{ padding: "24px 32px" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 20 }}>
        <div>
          <div style={{ fontWeight: 700, fontSize: 16 }}>User Management</div>
          <div style={{ fontSize: 12, color: "var(--text-dim)", marginTop: 2 }}>
            Manage system accounts, roles, and access.
          </div>
        </div>
        <button className="btn btn-primary" onClick={() => setShowCreate(!showCreate)}>
          {showCreate ? "Cancel" : "+ New User"}
        </button>
      </div>

      {showCreate && (
        <form onSubmit={createUser} style={{ background: "var(--bg-elevated)", border: "1px solid var(--border)", borderRadius: 6, padding: 16, marginBottom: 20, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <div className="field">
            <span className="field-label">Username</span>
            <input className="input" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} required />
          </div>
          <div className="field">
            <span className="field-label">Email</span>
            <input className="input" type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} required />
          </div>
          <div className="field">
            <span className="field-label">Display Name</span>
            <input className="input" value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} />
          </div>
          <div className="field">
            <span className="field-label">Password</span>
            <input className="input" type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} required autoComplete="new-password" />
          </div>
          <div className="field" style={{ gridColumn: "1 / -1" }}>
            <span className="field-label">Role</span>
            <select className="input" value={form.roles} onChange={(e) => setForm({ ...form, roles: e.target.value })}>
              {ALL_ROLES.map((r) => <option key={r} value={r}>{r.replace(/_/g, " ")}</option>)}
            </select>
          </div>
          <div style={{ gridColumn: "1 / -1", display: "flex", alignItems: "center", gap: 8 }}>
            <input type="checkbox" id="mfa_req" checked={form.is_mfa_required} onChange={(e) => setForm({ ...form, is_mfa_required: e.target.checked })} />
            <label htmlFor="mfa_req" style={{ fontSize: 12 }}>Require MFA</label>
          </div>
          {createError && <p style={{ gridColumn: "1/-1", fontSize: 12, color: "var(--danger, #e53e3e)", margin: 0 }}>{createError}</p>}
          <button className="btn btn-primary" type="submit" style={{ gridColumn: "1/-1" }}>Create User</button>
        </form>
      )}

      {error && <p style={{ color: "var(--danger, #e53e3e)", fontSize: 12 }}>{error}</p>}
      {actionError && <p style={{ color: "var(--danger, #e53e3e)", fontSize: 12 }}>{actionError}</p>}

      {loading ? (
        <p style={{ color: "var(--text-dim)", fontSize: 13 }}>Loading…</p>
      ) : (
        <div style={{ border: "1px solid var(--border)", borderRadius: 6, overflow: "hidden" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ background: "var(--bg-elevated)" }}>
                <th style={thStyle}>Username</th>
                <th style={thStyle}>Email</th>
                <th style={thStyle}>Roles</th>
                <th style={thStyle}>Status</th>
                <th style={thStyle}>MFA</th>
                <th style={thStyle}>Last Login</th>
                <th style={thStyle}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id}>
                  <td style={tdStyle}>{u.username}</td>
                  <td style={tdStyle}>{u.email}</td>
                  <td style={tdStyle}>{(u.roles || []).map((r) => r.replace(/_/g, " ")).join(", ")}</td>
                  <td style={tdStyle}>
                    {u.is_locked ? (
                      <span style={{ color: "var(--danger, #e53e3e)", fontWeight: 600 }}>Locked</span>
                    ) : u.is_active ? (
                      <span style={{ color: "var(--success, #38a169)" }}>Active</span>
                    ) : (
                      <span style={{ color: "var(--text-dim)" }}>Disabled</span>
                    )}
                  </td>
                  <td style={tdStyle}>{u.totp_enrolled ? "TOTP" : u.is_mfa_required ? "Required" : "—"}</td>
                  <td style={tdStyle}>{u.last_login_at ? new Date(u.last_login_at).toLocaleDateString() : "Never"}</td>
                  <td style={tdStyle}>
                    <div style={{ display: "flex", gap: 4 }}>
                      {u.is_active ? (
                        <button className="btn" style={{ fontSize: 11, padding: "2px 8px" }} onClick={() => doAction(u.id, "disable")}>Disable</button>
                      ) : (
                        <button className="btn" style={{ fontSize: 11, padding: "2px 8px" }} onClick={() => doAction(u.id, "enable")}>Enable</button>
                      )}
                      {u.is_locked && (
                        <button className="btn btn-primary" style={{ fontSize: 11, padding: "2px 8px" }} onClick={() => doAction(u.id, "unlock")}>Unlock</button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
              {users.length === 0 && (
                <tr><td colSpan={7} style={{ ...tdStyle, textAlign: "center", color: "var(--text-dim)" }}>No users found.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
