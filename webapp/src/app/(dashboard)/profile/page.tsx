"use client";

/**
 * Profile page — R-81.
 *
 * Authenticated dashboard page showing:
 *   - Plan & Usage (QuotaCard)
 *   - API Key management (ApiKeyCard)
 *
 * Data fetching:
 *   - GET /web/auth/quota → { used, limit, plan, reset_date, unlimited }
 *   - GET /web/auth/api-key/status → { has_key, prefix }
 */

import { useEffect, useState, useCallback } from "react";
import { useAuth } from "@/lib/auth-context";
import { fetchApi, ApiError } from "@/lib/api";
import { QuotaCard } from "./_components/QuotaCard";
import { ApiKeyCard } from "./_components/ApiKeyCard";

// ── Types ─────────────────────────────────────────────────────────────────────

interface ApiKeyStatus {
  has_key: boolean;
  prefix: string | null;
}

interface QuotaUsage {
  used: number;
  limit: number;
  plan: string;
  reset_date: string | null;
  unlimited: boolean;
}

// ── Page component ────────────────────────────────────────────────────────────

export default function ProfilePage() {
  const { user } = useAuth();

  const [keyStatus, setKeyStatus] = useState<ApiKeyStatus | null>(null);
  const [loadingStatus, setLoadingStatus] = useState(true);
  const [statusError, setStatusError] = useState<string | null>(null);

  const [quota, setQuota] = useState<QuotaUsage | null>(null);
  const [loadingQuota, setLoadingQuota] = useState(true);

  // Fetch API key status
  const fetchKeyStatus = useCallback(async () => {
    setLoadingStatus(true);
    setStatusError(null);
    try {
      const data = await fetchApi<ApiKeyStatus>("/api/web/auth/api-key/status");
      setKeyStatus(data);
    } catch (err) {
      if (err instanceof ApiError) {
        setStatusError(`Could not load API key status (${err.status})`);
      } else {
        setStatusError("Network error loading API key status.");
      }
    } finally {
      setLoadingStatus(false);
    }
  }, []);

  // Fetch quota usage
  const fetchQuota = useCallback(async () => {
    setLoadingQuota(true);
    try {
      const data = await fetchApi<QuotaUsage>("/api/web/auth/quota");
      setQuota(data);
    } catch {
      // non-blocking — QuotaCard shows fallback if null
    } finally {
      setLoadingQuota(false);
    }
  }, []);

  useEffect(() => {
    void fetchKeyStatus();
    void fetchQuota();
  }, [fetchKeyStatus, fetchQuota]);

  // Callbacks from ApiKeyCard — refresh status after generate or revoke
  const handleKeyGenerated = useCallback(() => {
    void fetchKeyStatus();
  }, [fetchKeyStatus]);

  const handleKeyRevoked = useCallback(() => {
    void fetchKeyStatus();
  }, [fetchKeyStatus]);

  return (
    <div className="flex flex-col gap-6">

      {/* Page header */}
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-[var(--color-on-surface)]">
          My Profile
        </h1>
        <p className="mt-1 text-sm text-[var(--color-on-surface-variant)]">
          Manage your plan, usage, and API credentials.
        </p>
      </div>

      {/* User info row */}
      {user && (
        <div className="flex items-center gap-4 p-5 bg-white border border-[var(--color-outline-variant)] rounded-xl">
          {/* Avatar */}
          <div
            style={{
              width: 48, height: 48, borderRadius: "50%", flexShrink: 0,
              background: "linear-gradient(135deg, #003d9b, #0052cc)",
              display: "flex", alignItems: "center", justifyContent: "center",
            }}
            aria-hidden="true"
          >
            <span style={{ color: "white", fontWeight: 700, fontSize: "1.125rem" }}>
              {user.nombre.charAt(0).toUpperCase()}
            </span>
          </div>

          {/* Name & email */}
          <div className="min-w-0">
            <p className="text-sm font-semibold text-[var(--color-on-surface)] truncate">
              {user.nombre}
            </p>
            <p className="text-xs text-[var(--color-on-surface-variant)] truncate">
              {user.correo}
            </p>
          </div>
        </div>
      )}

      {/* Cards grid */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">

        {/* Quota card */}
        <QuotaCard
          plan={quota?.plan ?? user?.plan ?? "basic"}
          used={loadingQuota ? null : (quota?.used ?? 0)}
          limit={quota?.unlimited ? -1 : (quota?.limit ?? 100)}
          resetDate={quota?.reset_date ?? null}
        />

        {/* API Key card */}
        {loadingStatus ? (
          <div
            className="bg-white border border-[var(--color-outline-variant)] rounded-xl p-8 flex items-center justify-center"
            aria-label="Loading API key status"
          >
            <div style={{ display: "flex", alignItems: "center", gap: 10, color: "var(--color-on-surface-variant)" }}>
              <svg
                style={{ animation: "spin 1s linear infinite" }}
                width="20" height="20" viewBox="0 0 20 20" fill="none"
                aria-hidden="true"
              >
                <circle cx="10" cy="10" r="8" stroke="currentColor" strokeOpacity="0.25" strokeWidth="2.5" />
                <path d="M18 10A8 8 0 0 0 10 2" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
              </svg>
              <span className="text-sm">Loading…</span>
            </div>
          </div>
        ) : statusError ? (
          <div
            role="alert"
            className="bg-white border border-[var(--color-outline-variant)] rounded-xl p-6"
          >
            <p className="text-sm font-medium text-red-700">{statusError}</p>
            <button
              type="button"
              onClick={() => void fetchKeyStatus()}
              className="mt-2 text-xs text-[var(--color-primary)] hover:underline"
            >
              Retry
            </button>
          </div>
        ) : (
          <ApiKeyCard
            hasKey={keyStatus?.has_key ?? false}
            prefix={keyStatus?.prefix ?? null}
            onGenerate={handleKeyGenerated}
            onRevoke={handleKeyRevoked}
          />
        )}
      </div>
    </div>
  );
}
