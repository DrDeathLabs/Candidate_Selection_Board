import axios from "axios";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { useAuth } from "../app/auth-context";

const BASE = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";

type LoginStep = "credentials" | "totp";

export function LoginPage() {
  const navigate = useNavigate();
  const { login } = useAuth();

  const [step, setStep] = useState<LoginStep>("credentials");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [totpCode, setTotpCode] = useState("");
  const [pendingToken, setPendingToken] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleCredentials(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const res = await axios.post(
        `${BASE}/auth/login`,
        { username, password },
        { withCredentials: true },
      );
      const data = res.data;
      if (data.mfa_required) {
        setPendingToken(data.pending_token ?? "");
        setStep("totp");
      } else {
        login(data.csrf_token ?? "", {
          user_id: data.user_id,
          username,
          email: "",
          display_name: data.display_name,
          roles: data.roles ?? [],
          is_mfa_required: false,
          totp_enrolled: false,
        });
        navigate("/engagements");
      }
    } catch (err: any) {
      const status = err?.response?.status;
      if (status === 423) {
        setError("Account is locked. Contact an administrator.");
      } else if (status === 429) {
        setError("Too many login attempts. Wait a minute and try again.");
      } else {
        setError("Invalid username or password.");
      }
    } finally {
      setLoading(false);
    }
  }

  async function handleTotp(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const res = await axios.post(
        `${BASE}/auth/login/totp`,
        { pending_token: pendingToken, totp_code: totpCode },
        { withCredentials: true },
      );
      const data = res.data;
      login(data.csrf_token ?? "", {
        user_id: data.user_id,
        username,
        email: "",
        display_name: data.display_name,
        roles: data.roles ?? [],
        is_mfa_required: true,
        totp_enrolled: true,
      });
      navigate("/engagements");
    } catch {
      setError("Invalid authentication code.");
    } finally {
      setLoading(false);
    }
  }

  function handleOIDCLogin() {
    window.location.href = `${BASE}/auth/oidc/login`;
  }

  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100vh", background: "var(--bg)" }}>
      <div style={{ width: 340, display: "flex", flexDirection: "column", gap: 16 }}>
        <div style={{ fontFamily: "monospace", fontSize: 13, fontWeight: 700, letterSpacing: "0.08em", color: "var(--text)", marginBottom: 8 }}>
          CANDIDATE SELECTION BOARD
        </div>

        {step === "credentials" && (
          <form onSubmit={handleCredentials} style={{ display: "flex", flexDirection: "column", gap: 10, background: "var(--bg-elevated)", border: "1px solid var(--border)", borderRadius: 6, padding: 20 }}>
            <div className="field">
              <span className="field-label">Username</span>
              <input
                className="input"
                autoFocus
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                required
                disabled={loading}
              />
            </div>
            <div className="field">
              <span className="field-label">Password</span>
              <input
                className="input"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                required
                disabled={loading}
              />
            </div>
            {error && (
              <p style={{ fontSize: 12, color: "var(--danger, #e53e3e)", margin: 0 }}>{error}</p>
            )}
            <button className="btn btn-primary" type="submit" disabled={loading} style={{ marginTop: 4 }}>
              {loading ? "Signing in…" : "Sign in"}
            </button>
            <button
              type="button"
              className="btn"
              onClick={handleOIDCLogin}
              style={{ marginTop: 4, fontSize: 12 }}
            >
              Sign in with Agency SSO
            </button>
          </form>
        )}

        {step === "totp" && (
          <form onSubmit={handleTotp} style={{ display: "flex", flexDirection: "column", gap: 10, background: "var(--bg-elevated)", border: "1px solid var(--border)", borderRadius: 6, padding: 20 }}>
            <p style={{ fontSize: 12, color: "var(--text-dim)", margin: 0 }}>
              Enter the 6-digit code from your authenticator app.
            </p>
            <div className="field">
              <span className="field-label">Authentication Code</span>
              <input
                className="input"
                autoFocus
                value={totpCode}
                onChange={(e) => setTotpCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                autoComplete="one-time-code"
                inputMode="numeric"
                pattern="[0-9]{6}"
                required
                disabled={loading}
                placeholder="000000"
              />
            </div>
            {error && (
              <p style={{ fontSize: 12, color: "var(--danger, #e53e3e)", margin: 0 }}>{error}</p>
            )}
            <button className="btn btn-primary" type="submit" disabled={loading || totpCode.length !== 6}>
              {loading ? "Verifying…" : "Verify"}
            </button>
            <button
              type="button"
              className="btn"
              onClick={() => { setStep("credentials"); setError(null); setTotpCode(""); }}
              style={{ fontSize: 12 }}
            >
              Back
            </button>
          </form>
        )}

        <p style={{ fontSize: 11, color: "var(--text-dim)", textAlign: "center" }}>
          This system contains sensitive federal information. Unauthorized access is prohibited.
        </p>
      </div>
    </div>
  );
}
