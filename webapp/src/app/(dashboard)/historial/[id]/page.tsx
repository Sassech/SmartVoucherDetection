/**
 * Historial detail page — RSC.
 * Fetches comprobante by ID server-side, renders all fields.
 * R-42, R-46, S-39, S-40, 4.D.7
 */

import { cookies } from "next/headers";
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
        <div className="rounded-[var(--radius-lg)] bg-red-50 border border-red-200 p-5">
          <p className="text-sm font-medium text-red-700">Acceso denegado</p>
          <p className="mt-1 text-xs text-red-500">
            No tienes permisos para ver este comprobante.
          </p>
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
        <div className="rounded-[var(--radius-lg)] bg-red-50 border border-red-200 p-5">
          <p className="text-sm font-medium text-red-700">
            No se pudo cargar el comprobante
          </p>
          {error && <p className="mt-1 text-xs text-red-500">{error}</p>}
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center gap-3">
        <h1 className="text-2xl font-semibold tracking-tight text-[var(--color-on-surface)]">
          Comprobante
        </h1>
        <span className="font-mono text-sm text-[var(--color-on-surface-variant)]">
          {item.folio.slice(0, 8)}
        </span>
        <Badge variant={estadoToBadgeVariant(item.estado)}>{item.estado}</Badge>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="rounded-[var(--radius-lg)] border border-[var(--color-outline-variant)] bg-[var(--color-surface)] p-5">
          <h2 className="mb-4 text-sm font-semibold text-[var(--color-on-surface)]">
            Datos del Depósito
          </h2>
          <dl className="flex flex-col gap-3">
            {[
              { label: "Monto", value: item.monto !== null ? `$${item.monto.toLocaleString()}` : "—" },
              { label: "Banco", value: item.banco ?? "—" },
              { label: "Referencia", value: item.referencia ?? "—" },
              { label: "Fecha de depósito", value: item.fecha_deposito ?? "—" },
            ].map(({ label, value }) => (
              <div key={label} className="flex justify-between text-sm">
                <dt className="text-[var(--color-on-surface-variant)]">{label}</dt>
                <dd className="font-medium text-[var(--color-on-surface)]">{value}</dd>
              </div>
            ))}
          </dl>
        </div>

        {item.imagen_path && (
          <div className="rounded-[var(--radius-lg)] border border-[var(--color-outline-variant)] bg-[var(--color-surface)] p-5">
            <h2 className="mb-4 text-sm font-semibold text-[var(--color-on-surface)]">
              Imagen
            </h2>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={item.imagen_path}
              alt={`Comprobante ${item.folio.slice(0, 8)}`}
              className="w-full rounded-[var(--radius-md)] object-contain"
            />
          </div>
        )}
      </div>

      {item.texto_extraido && (
        <div className="rounded-[var(--radius-lg)] border border-[var(--color-outline-variant)] bg-[var(--color-surface)] p-5">
          <h2 className="mb-3 text-sm font-semibold text-[var(--color-on-surface)]">
            Texto Extraído (OCR)
          </h2>
          <pre className="overflow-auto rounded-[var(--radius-sm)] bg-[var(--color-surface-container-low)] p-3 text-xs text-[var(--color-on-surface)]">
            {item.texto_extraido}
          </pre>
        </div>
      )}
    </div>
  );
}
