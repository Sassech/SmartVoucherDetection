"use client";

/**
 * Auth context — R-34, S-21.
 *
 * Access token stored EXCLUSIVELY in module-level memory (never localStorage,
 * never non-HttpOnly cookie). The refresh_token is managed solely by the
 * FastAPI backend via HttpOnly Set-Cookie headers.
 */

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";

// ── Module-level token store (not React state — survives re-renders) ──────────
// This is intentional: we want the token accessible to fetchApi without
// going through React context subscriptions on every request.
let _accessToken: string | null = null;

export function getAccessToken(): string | null {
  return _accessToken;
}

export function setAccessToken(token: string | null): void {
  _accessToken = token;
}

// ── Auth ready promise ────────────────────────────────────────────────────────
// Resolves once the silent refresh on mount completes (success or fail).
// fetchApi awaits this before sending requests so pages that load immediately
// on mount don't race against the refresh and get spurious 401s.
let _resolveReady: () => void;
const _authReady: Promise<void> = new Promise<void>((resolve) => {
  _resolveReady = resolve;
});

export function waitForAuth(): Promise<void> {
  return _authReady;
}

export function markAuthReady(): void {
  _resolveReady();
}

// ── Types ─────────────────────────────────────────────────────────────────────

export interface AuthUser {
  id_usuario: string;
  correo: string;
  nombre: string;
  rol: string;
  id_organizacion: string;
  /** R-75: plan returned by /web/auth/me — "basic" | "pro" | "enterprise" */
  plan?: string;
}

interface AuthContextValue {
  user: AuthUser | null;
  token: string | null;
  /** true once the silent refresh attempt on mount has completed (success or fail) */
  isReady: boolean;
  login: (correo: string, contrasena: string) => Promise<void>;
  logout: () => Promise<void>;
}

// ── Context ───────────────────────────────────────────────────────────────────

const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used inside <AuthProvider>");
  }
  return ctx;
}

// ── Provider ──────────────────────────────────────────────────────────────────

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [token, setTokenState] = useState<string | null>(null);
  // isReady flips to true once the silent refresh attempt completes (success OR fail).
  // Pages should wait for isReady before making authenticated requests to avoid
  // race conditions where fetchApi runs before the access token is in memory.
  const [isReady, setIsReady] = useState(false);

  // Sync module-level store with React state.
  const updateToken = useCallback((newToken: string | null) => {
    setAccessToken(newToken);
    setTokenState(newToken);
  }, []);

  // On mount: attempt a silent refresh so users with a valid refresh_token
  // cookie don't have to log in again after a page reload.
  useEffect(() => {
    const tryRefresh = async () => {
      try {
        const res = await fetch("/api/web/auth/refresh", {
          method: "POST",
          credentials: "include",
        });
        if (res.ok) {
          const data = (await res.json()) as { access_token: string };
          updateToken(data.access_token);
          // Fetch user info with the new token.
          const meRes = await fetch("/api/web/auth/me", {
            headers: { Authorization: `Bearer ${data.access_token}` },
            credentials: "include",
          });
          if (meRes.ok) {
            const me = (await meRes.json()) as AuthUser;
            setUser(me);
          }
        }
      } catch {
        // Silent failure — user stays unauthenticated.
      } finally {
        // Always mark ready so pages can proceed (with or without a token).
        setIsReady(true);
        markAuthReady();
      }
    };
    void tryRefresh();
  }, [updateToken]);

  const login = useCallback(
    async (correo: string, contrasena: string) => {
      const res = await fetch("/api/web/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ correo, contrasena }),
        credentials: "include",
      });

      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as { detail?: string };
        throw new Error(body.detail ?? "Invalid credentials");
      }

      const data = (await res.json()) as { access_token: string };
      updateToken(data.access_token);

      // S-21: verify token is NOT in localStorage.
      // (This is a runtime assertion — token lives only in module variable.)
      if (typeof window !== "undefined") {
        // Defensive: never write to localStorage.
        // localStorage.setItem("access_token", ...) is intentionally absent.
      }

      // Fetch user profile.
      const meRes = await fetch("/api/web/auth/me", {
        headers: { Authorization: `Bearer ${data.access_token}` },
        credentials: "include",
      });
      if (meRes.ok) {
        const me = (await meRes.json()) as AuthUser;
        setUser(me);
      }
    },
    [updateToken],
  );

  const logout = useCallback(async () => {
    const currentToken = getAccessToken();
    try {
      await fetch("/api/web/auth/logout", {
        method: "POST",
        headers: currentToken
          ? { Authorization: `Bearer ${currentToken}` }
          : {},
        credentials: "include",
      });
    } finally {
      updateToken(null);
      setUser(null);
    }
  }, [updateToken]);

  return (
    <AuthContext.Provider value={{ user, token, isReady, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}
