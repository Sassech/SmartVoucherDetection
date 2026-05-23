/**
 * Historial detail page — RSC.
 * Fetches comprobante by ID server-side, renders full validation result layout.
 * R-42, R-46, S-39, S-40, 4.D.7 — redesigned to match resultado_de_validacion/code.html
 */

import { cookies } from "next/headers";
import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import type { WebComprobanteItem } from "@/lib/types";
import type { BadgeProps } from "@/components/ui/badge";

function estadoToBadgeVariant(estado: WebComprobanteItem["estado"]): BadgeProps["variant"] {
  switch (estado) {
    case "procesado": return "valido";
    case "duplicado": return "duplicado";
    case "sospechoso": return "sospechoso";
    case "en_revision": return "en_revision";
    case "error": return "error";
    default: return "default";
  }
}

function estadoLabel(estado: WebComprobanteItem["estado"]): string {
  const map: Record<WebComprobanteItem["estado"], string> = {
    pendiente: "Pendiente",
    procesado: "Válido",
    duplicado: "Duplicado",
    error: "Error",
    sospechoso: "Sospechoso",
    en_revision: "En Revisión",
  };
  return map[estado] ?? estado;
}

function estadoIcon(estado: WebComprobanteItem["estado"]): string {
  switch (estado) {
    case "procesado": return "check_circle";
    case "duplicado": return "content_copy";
    case "sospechoso": return "warning";
    case "error": return "error";
    default: return "info";
  }
}

function estadoIconColor(estado: WebComprobanteItem["estado"]): string {
  switch (estado) {
    case "procesado": return "text-green-500";
    case "duplicado": return "text-red-500";
    case "sospechoso": return "text-orange-500";
    case "error": return "text-red-600";
    default: return "text-[var(--color-secondary)]";
  }
}

/** SVG gauge: circumference = 2π×28 ≈ 175.9 */
function SimilarityGauge({ value }: { value: number }) {
  const circumference = 175.9;
  const offset = circumference * (1 - value / 100);
  return (
    <div className="relative w-16 h-16">
      <svg className="w-full h-full -rotate-90" viewBox="0 0 64 64">
        <circle
          className="text-[var(--color-surface-container-high)]"
          cx="32" cy="32" r="28"
          fill="transparent"
          stroke="currentColor"
          strokeWidth="6"
        />
        <circle
          className="text-[var(--color-primary)]"
          cx="32" cy="32" r="28"
          fill="transparent"
          stroke="currentColor"
          strokeWidth="6"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
        />
      </svg>
      <div className="absolute inset-0 flex items-center justify-center">
        <span className="text-xs font-bold text-[var(--color-primary)]">{value}%</span>
      </div>
    </div>
  );
}

interface Props {
  params: Promise<{ id: string }>;
}

export default async function HistorialDetailPage({ params }: Props) {
  const { id } = await params;

  let item: WebComprobanteItem | null = null;
  let error: string | null = null;
  let status403 = false;

  try {
    const cookieStore = await cookies();
    const token = cookieStore.get("access_token")?.value;
    const baseUrl = process.env.BACKEND_URL ?? "http://localhost:8000";

    const headers: Record<string, string> = {};
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }

    const res = await fetch(`${baseUrl}/api/web/comprobantes/${id}`, {
      headers,
      cache: "no-store",
    });

    if (res.status === 403) {
      status403 = true;
    } else if (!res.ok) {
      error = `HTTP ${res.status}: ${res.statusText}`;
    } else {
      item = (await res.json()) as WebComprobanteItem;
    }
  } catch (err) {
    error = err instanceof Error ? err.message : "Error desconocido";
  }

  if (status403) {
    return (
      <div className="flex flex-col gap-4">
        <h1 className="text-2xl font-semibold tracking-tight text-[var(--color-on-surface)]">
          Detalle de Comprobante
        </h1>
        <div className="rounded-xl bg-red-50 border border-red-200 p-5">
          <p className="text-sm font-medium text-red-700">Acceso denegado</p>
          <p className="mt-1 text-xs text-red-500">No tienes permisos para ver este comprobante.</p>
        </div>
      </div>
    );
  }

  if (error || !item) {
    return (
      <div className="flex flex-col gap-4">
        <h1 className="text-2xl font-semibold tracking-tight text-[var(--color-on-surface)]">
          Detalle de Comprobante
        </h1>
        <div className="rounded-xl bg-red-50 border border-red-200 p-5">
          <p className="text-sm font-medium text-red-700">No se pudo cargar el comprobante</p>
          {error && <p className="mt-1 text-xs text-red-500">{error}</p>}
        </div>
      </div>
    );
  }

  // Mock similarity — no viene del backend aún, usamos 0 como fallback
  const similitud = 0;

  return (
    <div className="space-y-6">

      {/* Status & Score Header — 3 cols bento */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">

        {/* Status Badge Card */}
        <div className="bg-white border border-[var(--color-outline-variant)] rounded-xl p-6 flex items-center justify-between shadow-sm">
          <div className="space-y-1">
            <span className="text-xs font-bold text-[var(--color-secondary)] uppercase tracking-wider">
              ESTADO DEL ANÁLISIS
            </span>
            <div className="mt-2">
              <Badge variant={estadoToBadgeVariant(item.estado)}>
                {estadoLabel(item.estado)}
              </Badge>
            </div>
            <p className="text-xs text-[var(--color-on-surface-variant)] pt-1 font-mono">
              {item.folio}
            </p>
          </div>
          <span className={`material-symbols-outlined text-3xl ${estadoIconColor(item.estado)}`}>
            {estadoIcon(item.estado)}
          </span>
        </div>

        {/* Similarity Gauge Card */}
        <div className="bg-white border border-[var(--color-outline-variant)] rounded-xl p-6 flex items-center gap-6 shadow-sm">
          <SimilarityGauge value={similitud} />
          <div className="flex-1">
            <h4 className="text-base font-semibold text-[var(--color-on-surface)]">
              Puntaje de Similitud
            </h4>
            <p className="text-xs text-[var(--color-secondary)] mt-1">
              {similitud >= 90
                ? "Alta probabilidad de duplicación."
                : similitud >= 70
                ? "Similitud moderada detectada."
                : "Sin coincidencias significativas."}
            </p>
          </div>
        </div>

        {/* Quick Actions Card */}
        <div className="bg-white border border-[var(--color-outline-variant)] rounded-xl p-6 flex items-center gap-4 shadow-sm">
          <button className="flex-1 bg-[var(--color-primary)] text-white text-xs font-medium py-2 rounded-xl hover:opacity-90 transition-all active:scale-[0.98] shadow-sm">
            Aceptar como Válido
          </button>
          <Link
            href={`/revision/${item.id_comprobante}`}
            className="flex-1 border border-[var(--color-outline)] text-[var(--color-on-surface-variant)] text-xs font-medium py-2 rounded-xl hover:bg-[var(--color-surface-container)] transition-all active:scale-[0.98] text-center"
          >
            Revisión Manual
          </Link>
        </div>
      </div>

      {/* Main Split Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-start">

        {/* Left — Document Preview */}
        <div className="space-y-3">
          <div className="flex items-center justify-between px-1">
            <h3 className="text-base font-semibold text-[var(--color-on-surface)] flex items-center gap-2">
              <span className="material-symbols-outlined text-[var(--color-primary)]">image</span>
              Vista Previa del Documento Original
            </h3>
            <div className="flex gap-2">
              <button className="p-1 hover:bg-[var(--color-surface-container)] rounded-lg transition-colors">
                <span className="material-symbols-outlined text-[var(--color-secondary)] text-[20px]">zoom_in</span>
              </button>
              <button className="p-1 hover:bg-[var(--color-surface-container)] rounded-lg transition-colors">
                <span className="material-symbols-outlined text-[var(--color-secondary)] text-[20px]">download</span>
              </button>
            </div>
          </div>

          <div className="bg-[var(--color-surface-container-highest)] rounded-xl overflow-hidden border border-[var(--color-outline-variant)] aspect-[4/3] flex items-center justify-center relative group">
            {item.imagen_path ? (
              <>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={item.imagen_path}
                  alt={`Comprobante ${item.folio}`}
                  className="w-full h-full object-contain transition-transform group-hover:scale-105 duration-700"
                />
                <div className="absolute inset-0 bg-[var(--color-primary)]/10 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                  <div className="bg-white/90 backdrop-blur-md px-6 py-3 rounded-full shadow-lg flex items-center gap-2">
                    <span className="material-symbols-outlined text-[var(--color-primary)]">search</span>
                    <span className="text-xs font-medium text-[var(--color-on-background)]">
                      Clic para Inspeccionar Anclajes OCR
                    </span>
                  </div>
                </div>
              </>
            ) : (
              <div className="flex flex-col items-center gap-3 text-[var(--color-on-surface-variant)]">
                <span className="material-symbols-outlined text-5xl opacity-30">image_not_supported</span>
                <p className="text-sm">Sin imagen disponible</p>
              </div>
            )}
          </div>
        </div>

        {/* Right — Extracted Data */}
        <div className="space-y-3">
          <div className="flex items-center px-1">
            <h3 className="text-base font-semibold text-[var(--color-on-surface)] flex items-center gap-2">
              <span className="material-symbols-outlined text-[var(--color-primary)]">data_object</span>
              Información Extraída
            </h3>
          </div>

          <div className="bg-white border border-[var(--color-outline-variant)] rounded-xl overflow-hidden shadow-sm">
            {/* Table header */}
            <div className="bg-[#F9FAFB] border-b border-[var(--color-outline-variant)] px-6 py-3 grid grid-cols-2">
              <span className="text-xs font-bold text-[var(--color-secondary)] uppercase tracking-wider">
                NOMBRE DEL CAMPO
              </span>
              <span className="text-xs font-bold text-[var(--color-secondary)] uppercase tracking-wider">
                VALOR EXTRAÍDO
              </span>
            </div>

            {/* Field rows */}
            <div className="divide-y divide-slate-100">
              <div className="px-6 py-3 grid grid-cols-2 hover:bg-slate-50 transition-colors">
                <span className="text-sm text-[var(--color-secondary)] font-medium">Fecha de Transacción</span>
                <span className="text-sm font-bold text-[var(--color-on-surface)]">
                  {item.fecha_deposito ?? "—"}
                </span>
              </div>
              <div className="px-6 py-3 grid grid-cols-2 hover:bg-slate-50 transition-colors">
                <span className="text-sm text-[var(--color-secondary)] font-medium">Monto Total</span>
                <span className="text-sm font-bold text-[var(--color-primary)]">
                  {item.monto !== null ? `$${item.monto.toLocaleString()}` : "—"}
                </span>
              </div>
              <div className="px-6 py-3 grid grid-cols-2 hover:bg-slate-50 transition-colors">
                <span className="text-sm text-[var(--color-secondary)] font-medium">Número de Referencia</span>
                <span className="text-sm font-mono bg-[var(--color-surface-container)] px-2 py-0.5 rounded">
                  {item.referencia ?? "—"}
                </span>
              </div>
              <div className="px-6 py-3 grid grid-cols-2 hover:bg-slate-50 transition-colors">
                <span className="text-sm text-[var(--color-secondary)] font-medium">Banco Emisor</span>
                <span className="text-sm font-bold text-[var(--color-on-surface)]">
                  {item.banco ?? "—"}
                </span>
              </div>
              <div className="px-6 py-3 grid grid-cols-2 hover:bg-slate-50 transition-colors items-center">
                <span className="text-sm text-[var(--color-secondary)] font-medium">Folio / ID</span>
                <span className="text-xs font-mono text-blue-600">{item.folio}</span>
              </div>
            </div>

            {/* Footer note */}
            <div className="bg-[var(--color-surface-container-low)] p-6 border-t border-[var(--color-outline-variant)]">
              <div className="flex items-start gap-3">
                <span className="material-symbols-outlined text-[var(--color-secondary)] text-[18px]">info</span>
                <p className="text-xs text-[var(--color-on-surface-variant)] leading-relaxed">
                  OCR extraído con Motor Tesseract v4.0. Revise los datos antes de tomar una acción.
                </p>
              </div>
            </div>
          </div>

          {/* Fraud action */}
          <div className="flex flex-col gap-2">
            <button className="w-full bg-[var(--color-error-container)] text-[var(--color-on-error-container)] text-xs font-medium py-4 rounded-xl hover:opacity-80 transition-all border border-[var(--color-error)]/20 flex items-center justify-center gap-2">
              <span className="material-symbols-outlined text-[18px]">report</span>
              Marcar para Investigación de Fraude
            </button>
            <p className="text-[10px] text-center text-[var(--color-outline)] uppercase tracking-widest font-bold">
              El registro de auditoría grabará esta acción permanentemente
            </p>
          </div>
        </div>
      </div>

      {/* History Context Bento */}
      <div className="bg-white border border-[var(--color-outline-variant)] rounded-xl p-6 shadow-sm">
        <h3 className="text-base font-semibold text-[var(--color-on-surface)] mb-6 flex items-center gap-2">
          <span className="material-symbols-outlined text-[var(--color-primary)]">history</span>
          Contexto de Validación Reciente
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          {[
            { label: "Volumen de Hoy", value: "142", color: "text-[var(--color-primary)]" },
            { label: "Tasa de Éxito", value: "94.2%", color: "text-emerald-600" },
            { label: "Revisiones Pendientes", value: "8", color: "text-orange-500" },
            { label: "Tiempo Promedio IA", value: "1.2s", color: "text-[var(--color-on-surface)]" },
          ].map(({ label, value, color }) => (
            <div
              key={label}
              className="p-4 bg-[#F9FAFB] rounded-lg border border-slate-100 text-center"
            >
              <span className="text-xs text-[var(--color-secondary)] block mb-1">{label}</span>
              <span className={`text-xl font-bold ${color}`}>{value}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
