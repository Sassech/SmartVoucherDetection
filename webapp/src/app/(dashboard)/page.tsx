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
      {/* Page header */}
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-[var(--color-on-surface)]">
            Resumen Administrativo
          </h1>
          <p className="mt-1 text-sm text-[var(--color-secondary)]">
            Métricas de reconocimiento y verificación en tiempo real.
          </p>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            className="flex items-center gap-1.5 rounded-lg border border-[var(--color-outline-variant)] bg-white px-3 py-2 text-xs font-medium text-[var(--color-on-surface)] hover:bg-[var(--color-surface-container-low)] transition-colors"
          >
            <span className="material-symbols-outlined text-[16px]">calendar_today</span>
            Últimos 30 días
          </button>
          <button
            type="button"
            className="flex items-center gap-1.5 rounded-lg bg-[var(--color-primary)] px-3 py-2 text-xs font-medium text-white hover:opacity-90 transition-opacity"
          >
            <span className="material-symbols-outlined text-[16px]">download</span>
            Exportar
          </button>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard
          label="Total Procesados"
          value={stats.total_comprobantes}
          icon="analytics"
          iconBgClass="bg-[var(--color-surface-container)]"
          iconColorClass="text-[var(--color-primary)]"
          badge="+12.5%"
          badgeColorClass="text-[var(--color-secondary)]"
        />
        <KpiCard
          label="Validados"
          value={stats.procesados_hoy}
          icon="check_circle"
          iconBgClass="bg-green-50"
          iconColorClass="text-green-600"
          valueColorClass="text-green-600"
          badge="94% Tasa"
          badgeColorClass="text-green-600"
        />
        <KpiCard
          label="Duplicados"
          value={stats.duplicados_detectados}
          icon="content_copy"
          iconBgClass="bg-red-50"
          iconColorClass="text-red-600"
          valueColorClass="text-red-600"
          badge="2.1% Error"
          badgeColorClass="text-red-600"
        />
        <KpiCard
          label="Pendientes"
          value={stats.pendientes}
          icon="warning"
          iconBgClass="bg-orange-50"
          iconColorClass="text-orange-600"
          valueColorClass="text-orange-600"
          badge="Acción Requerida"
          badgeColorClass="text-orange-600"
        />
      </div>

      {/* Processing Volume Chart + Recent Activity */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Chart — lg:col-span-2 */}
        <div className="lg:col-span-2 rounded-xl border border-[var(--color-outline-variant)] bg-white overflow-hidden">
          <div className="px-5 py-4 border-b border-[var(--color-outline-variant)] flex items-center justify-between">
            <h2 className="text-sm font-semibold text-[var(--color-on-surface)]">
              Volumen de Procesamiento (30 Días)
            </h2>
            <div className="flex items-center gap-4">
              <span className="flex items-center gap-1.5 text-[11px] text-[var(--color-secondary)]">
                <span className="w-2.5 h-2.5 rounded-sm bg-[var(--color-primary)] inline-block" />
                Exitosos
              </span>
              <span className="flex items-center gap-1.5 text-[11px] text-[var(--color-secondary)]">
                <span className="w-2.5 h-2.5 rounded-sm bg-orange-400 inline-block" />
                Problemas
              </span>
            </div>
          </div>
          <div className="px-5 py-4">
            <svg
              viewBox="0 0 420 110"
              className="w-full"
              preserveAspectRatio="none"
              aria-hidden="true"
            >
              {/* Background bars (decorative) */}
              {[0,20,40,60,80,100,120,140,160,180,200,220,240,260,280,300,320,340,360,380,400].map((x, i) => (
                <rect
                  key={i}
                  x={x + 2}
                  y={40 + (i % 3) * 8}
                  width={14}
                  height={70 - (i % 3) * 8}
                  fill="#E2E8F0"
                  rx={2}
                />
              ))}
              {/* Trend line */}
              <polyline
                points="0,80 20,70 40,85 60,40 80,60 100,50 120,30 140,75 160,45 180,55 200,20 220,60 240,40 260,30 280,10 300,50 320,40 340,60 360,30 380,20 400,25"
                fill="none"
                stroke="#003d9b"
                strokeWidth="2"
                strokeLinejoin="round"
                strokeLinecap="round"
              />
              {/* Gradient fill under the line */}
              <defs>
                <linearGradient id="chartGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#003d9b" stopOpacity="0.15" />
                  <stop offset="100%" stopColor="#003d9b" stopOpacity="0" />
                </linearGradient>
              </defs>
              <polygon
                points="0,80 20,70 40,85 60,40 80,60 100,50 120,30 140,75 160,45 180,55 200,20 220,60 240,40 260,30 280,10 300,50 320,40 340,60 360,30 380,20 400,25 400,110 0,110"
                fill="url(#chartGrad)"
              />
            </svg>
            {/* Date labels */}
            <div className="flex justify-between mt-1 px-1">
              {["1 May", "8 May", "15 May", "22 May", "29 May"].map((d) => (
                <span key={d} className="text-[10px] text-[var(--color-secondary)]">
                  {d}
                </span>
              ))}
            </div>
          </div>
        </div>

        {/* Recent Activity — lg:col-span-1 */}
        <div className="lg:col-span-1">
          <RecentActivity items={recentItems.items} />
        </div>
      </div>

      {/* OCR Banner */}
      <div className="bg-[var(--color-primary-container)] text-[var(--color-on-primary-container)] rounded-xl overflow-hidden flex flex-col md:flex-row">
        {/* Left content */}
        <div className="flex-1 p-6 flex flex-col justify-center gap-4">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse inline-block" />
            <span className="text-[11px] font-bold uppercase tracking-wider">
              Motor Optimizado
            </span>
          </div>
          <div>
            <h2 className="text-xl font-bold leading-snug">
              Inteligencia OCR Avanzada
            </h2>
            <p className="mt-2 text-sm opacity-80 leading-relaxed max-w-md">
              Motor de reconocimiento óptico entrenado con millones de comprobantes bancarios. Precisión superior al 99% en condiciones estándar de digitalización.
            </p>
          </div>
          <div className="flex flex-wrap gap-3">
            <button
              type="button"
              className="flex items-center gap-2 px-4 py-2 rounded-lg bg-[var(--color-primary)] text-white text-sm font-semibold hover:opacity-90 transition-opacity"
            >
              <span className="material-symbols-outlined text-[18px]">tune</span>
              Configurar Motor
            </button>
            <button
              type="button"
              className="flex items-center gap-2 px-4 py-2 rounded-lg border border-[var(--color-on-primary-container)]/30 text-[var(--color-on-primary-container)] text-sm font-semibold hover:bg-white/10 transition-colors"
            >
              <span className="material-symbols-outlined text-[18px]">list_alt</span>
              Ver Registros
            </button>
          </div>
        </div>

        {/* Right decorative */}
        <div className="w-full md:w-1/3 min-h-[200px] relative flex items-center justify-center bg-gradient-to-br from-[var(--color-primary)] via-[var(--color-primary-container)] to-[var(--color-surface-tint)]">
          <div className="p-6 rounded-2xl bg-white/10 backdrop-blur-sm flex items-center justify-center">
            <span
              className="material-symbols-outlined text-white"
              style={{ fontSize: "64px" }}
            >
              memory
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
