/**
 * Dashboard root page — RSC with server-side data fetch.
 * Fetches stats and recent comprobantes using the access_token cookie.
 * R-37, R-38, S-23, S-24, S-25, S-26, 4.D.3
 */

import { cookies } from "next/headers";
import { KpiCard } from "@/components/dashboard/KpiCard";
import { RecentActivity } from "@/components/dashboard/RecentActivity";
import type { StatsResponse, WebListResponse } from "@/lib/types";

async function fetchWithToken<T>(url: string, token: string | undefined): Promise<T> {
  const headers: Record<string, string> = {};
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  const res = await fetch(url, { headers, cache: "no-store" });
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}: ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

export default async function DashboardPage() {
  let stats: StatsResponse | null = null;
  let recentItems: WebListResponse | null = null;
  let error: string | null = null;

  try {
    const cookieStore = await cookies();
    const token = cookieStore.get("access_token")?.value;

    const baseUrl = process.env.BACKEND_URL ?? "http://localhost:8000";

    [stats, recentItems] = await Promise.all([
      fetchWithToken<StatsResponse>(`${baseUrl}/api/web/stats/`, token),
      fetchWithToken<WebListResponse>(`${baseUrl}/api/web/comprobantes/?limit=10`, token),
    ]);
  } catch (err) {
    error = err instanceof Error ? err.message : "Error desconocido";
  }

  if (error || !stats || !recentItems) {
    return (
      <div className="flex flex-col gap-6">
        <h1 className="text-2xl font-semibold tracking-tight text-[var(--color-on-surface)]">
          Dashboard
        </h1>
        <div className="rounded-[var(--radius-lg)] bg-red-50 border border-red-200 p-5">
          <p className="text-sm font-medium text-red-700">
            No se pudieron cargar los datos del dashboard
          </p>
          {error && (
            <p className="mt-1 text-xs text-red-500">{error}</p>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-semibold tracking-tight text-[var(--color-on-surface)]">
        Dashboard
      </h1>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard label="Total Comprobantes" value={stats.total_comprobantes} icon="📋" />
        <KpiCard label="Pendientes" value={stats.pendientes} icon="⏳" />
        <KpiCard label="Procesados Hoy" value={stats.procesados_hoy} icon="✅" />
        <KpiCard label="Duplicados Detectados" value={stats.duplicados_detectados} icon="⚠️" />
      </div>

      {/* Recent Activity */}
      <RecentActivity items={recentItems.items} />
    </div>
  );
}
