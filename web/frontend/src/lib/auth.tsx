/**
 * Auth context — token + user state, role-based guards.
 *
 * Token lives in localStorage (`pseint:token`), user in `pseint:user`.
 * The JWT itself carries only `sub`/`exp` (todo 17) — the role comes from
 * GET /api/me after login, so the frontend never verifies the token.
 * RequireRole redirects: no token → /login, role mismatch → /403.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { Navigate, useLocation } from "react-router-dom";
import { api, setAuthToken } from "./api";
import type { AuthUser } from "./types";

export type { AuthUser } from "./types";

const TOKEN_KEY = "pseint:token";
const USER_KEY = "pseint:user";

interface AuthContextValue {
  token: string | null;
  user: AuthUser | null;
  initializing: boolean;
  login: (username: string, password: string) => Promise<AuthUser>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

function readStoredUser(): AuthUser | null {
  try {
    const raw = localStorage.getItem(USER_KEY);
    return raw ? (JSON.parse(raw) as AuthUser) : null;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() =>
    localStorage.getItem(TOKEN_KEY),
  );
  const [user, setUser] = useState<AuthUser | null>(readStoredUser);
  const [initializing, setInitializing] = useState<boolean>(() => {
    return localStorage.getItem(TOKEN_KEY) !== null && readStoredUser() === null;
  });

  useEffect(() => {
    if (token) setAuthToken(token);
    if (!token) {
      setInitializing(false);
      return;
    }
    if (user) {
      setInitializing(false);
      return;
    }
    // Token present but no cached user — refresh from the server.
    let cancelled = false;
    api
      .get<AuthUser>("/me")
      .then((me) => {
        if (cancelled) return;
        setUser(me);
        localStorage.setItem(USER_KEY, JSON.stringify(me));
      })
      .catch(() => {
        if (cancelled) return;
        // Stale token — clear the session.
        localStorage.removeItem(TOKEN_KEY);
        localStorage.removeItem(USER_KEY);
        setAuthToken(null);
        setToken(null);
      })
      .finally(() => {
        if (!cancelled) setInitializing(false);
      });
    return () => {
      cancelled = true;
    };
  }, [token, user]);

  const login = useCallback(async (username: string, password: string) => {
    const res = await api.post<{ access_token: string }>("/api/login", {
      username,
      password,
    });
    setAuthToken(res.access_token);
    localStorage.setItem(TOKEN_KEY, res.access_token);
    const me = await api.get<AuthUser>("/api/me");
    setUser(me);
    localStorage.setItem(USER_KEY, JSON.stringify(me));
    setToken(res.access_token);
    return me;
  }, []);

  const logout = useCallback(() => {
    setAuthToken(null);
    setToken(null);
    setUser(null);
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({ token, user, initializing, login, logout }),
    [token, user, initializing, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (ctx === null) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

interface RequireRoleProps {
  roles: string[];
  children: ReactNode;
}

export function RequireRole({ roles, children }: RequireRoleProps) {
  const { token, user, initializing } = useAuth();
  const location = useLocation();

  if (initializing) return null;
  if (!token) return <Navigate to="/login" replace state={{ from: location }} />;
  if (!user || !roles.includes(user.role)) return <Navigate to="/403" replace />;
  return <>{children}</>;
}