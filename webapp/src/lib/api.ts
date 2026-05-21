/**
 * Typed fetch client with refresh mutex — R-35, S-20.
 *
 * - Attaches Authorization: Bearer <token> to every request.
 * - On 401: acquires a Promise-based mutex, calls POST /api/web/auth/refresh
 *   ONCE, releases the mutex, retries the original request.
 * - Concurrent 401s share one in-flight refresh (not N parallel refreshes).
 */

import { getAccessToken, setAccessToken } from "./auth-context";

// ── Mutex ─────────────────────────────────────────────────────────────────────

let _refreshPromise: Promise<string | null> | null = null;

async function refreshToken(): Promise<string | null> {
  if (_refreshPromise) {
    // Another caller already started a refresh — share it.
    return _refreshPromise;
  }

  _refreshPromise = (async () => {
    try {
      const res = await fetch("/api/web/auth/refresh", {
        method: "POST",
        credentials: "include",
      });
      if (!res.ok) return null;
      const data = (await res.json()) as { access_token: string };
      setAccessToken(data.access_token);
      return data.access_token;
    } catch {
      return null;
    } finally {
      _refreshPromise = null;
    }
  })();

  return _refreshPromise;
}

// ── fetchApi ──────────────────────────────────────────────────────────────────

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export async function fetchApi<T>(
  url: string,
  options: RequestInit = {},
): Promise<T> {
  const token = getAccessToken();
  const headers = new Headers(options.headers);
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const res = await fetch(url, {
    ...options,
    headers,
    credentials: "include",
  });

  if (res.status === 401) {
    // Acquire mutex — at most one refresh in flight across all concurrent callers.
    const newToken = await refreshToken();

    if (!newToken) {
      // Refresh failed — redirect to login.
      if (typeof window !== "undefined") {
        window.location.href = "/login";
      }
      throw new ApiError(401, "Session expired");
    }

    // Retry original request with new token.
    const retryHeaders = new Headers(options.headers);
    retryHeaders.set("Authorization", `Bearer ${newToken}`);
    const retryRes = await fetch(url, {
      ...options,
      headers: retryHeaders,
      credentials: "include",
    });

    if (!retryRes.ok) {
      const body = await retryRes.json().catch(() => ({})) as { detail?: string };
      throw new ApiError(retryRes.status, body.detail ?? retryRes.statusText);
    }

    return retryRes.json() as Promise<T>;
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({})) as { detail?: string };
    throw new ApiError(res.status, body.detail ?? res.statusText);
  }

  return res.json() as Promise<T>;
}
