import axios from "axios";
import { createContext, useContext, useEffect, useRef, useState } from "react";
import type { PropsWithChildren } from "react";

type AuthUser = {
  user_id: string;
  username: string;
  email: string;
  display_name: string | null;
  roles: string[];
  is_mfa_required: boolean;
  totp_enrolled: boolean;
};

type AuthContextValue = {
  isAuthenticated: boolean;
  isLoading: boolean;
  user: AuthUser | null;
  csrfToken: string | null;
  login: (csrfToken: string, user: AuthUser) => void;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

const BASE = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";

export function AuthProvider({ children }: PropsWithChildren) {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [user, setUser] = useState<AuthUser | null>(null);
  // CSRF token stored in memory only — never in storage (XSS protection)
  const csrfRef = useRef<string | null>(null);
  const [csrfToken, setCsrfToken] = useState<string | null>(null);

  // On mount, verify session with the server via GET /auth/me
  useEffect(() => {
    axios
      .get<AuthUser>(`${BASE}/auth/me`, { withCredentials: true })
      .then((res) => {
        setUser(res.data);
        setIsAuthenticated(true);
        // Read CSRF token from cookie (server sets it as non-HttpOnly)
        const csrf = document.cookie
          .split("; ")
          .find((c) => c.startsWith("sb_csrf="))
          ?.split("=")[1] ?? null;
        csrfRef.current = csrf;
        setCsrfToken(csrf);
      })
      .catch(() => {
        setIsAuthenticated(false);
        setUser(null);
      })
      .finally(() => setIsLoading(false));
  }, []);

  function login(token: string, userData: AuthUser) {
    csrfRef.current = token;
    setCsrfToken(token);
    setUser(userData);
    setIsAuthenticated(true);
  }

  async function logout() {
    try {
      await axios.post(`${BASE}/auth/logout`, {}, {
        withCredentials: true,
        headers: csrfRef.current ? { "X-CSRF-Token": csrfRef.current } : {},
      });
    } catch {
      // best-effort
    }
    csrfRef.current = null;
    setCsrfToken(null);
    setUser(null);
    setIsAuthenticated(false);
  }

  return (
    <AuthContext.Provider value={{ isAuthenticated, isLoading, user, csrfToken, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider.");
  return ctx;
}
