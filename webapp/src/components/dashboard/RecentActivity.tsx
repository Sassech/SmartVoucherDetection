/**
 * RecentActivity — recent comprobantes table for dashboard — R-38, S-25, 4.D.2
 */

import Link from "next/link";
import type { WebComprobanteItem } from "@/lib/types";

function estadoBadge(estado: WebComprobanteItem["estado_actual"]) {
  switch (estado) {
    case "valido":
      return (
        <span className="bg-green-100 text-green-700 text-[10px] px-2 py-0.5 rounded-full font-bold uppercase tracking-wider">
          Válido
        </span>
      );
    case "duplicado":
      return (
        <span className="bg-red-100 text-red-700 text-[10px] px-2 py-0.5 rounded-full font-bold uppercase tracking-wider">
          Duplicado
        </span>
      );
    case "sospechoso":
      return (
        <span className="bg-orange-100 text-orange-700 text-[10px] px-2 py-0.5 rounded-full font-bold uppercase tracking-wider">
          Sospechoso
        </span>
      );
    case "en_revision":
      return (
        <span className="bg-blue-100 text-blue-700 text-[10px] px-2 py-0.5 rounded-full font-bold uppercase tracking-wider">
          En revisión
        </span>
      );
    case "error":
      return (
        <span className="bg-red-50 text-red-500 text-[10px] px-2 py-0.5 rounded-full font-bold uppercase tracking-wider">
          Error
        </span>
      );
    default:
      return (
        <span className="bg-slate-100 text-slate-500 text-[10px] px-2 py-0.5 rounded-full font-bold uppercase tracking-wider">
          Pendiente
        </span>
      );
  }
}

interface RecentActivityProps {
  items: WebComprobanteItem[];
}

export function RecentActivity({ items }: RecentActivityProps) {
  return (
    <div className="rounded-xl border border-[var(--color-outline-variant)] bg-white overflow-hidden">
      {/* Card header */}
      <div className="px-5 py-4 border-b border-[var(--color-outline-variant)] flex items-center justify-between">
        <h2 className="text-sm font-semibold text-[var(--color-on-surface)]">
          Actividad Reciente
        </h2>
        <Link
          href="/historial"
          className="text-[11px] font-bold text-[var(--color-primary)] hover:underline"
        >
          Ver Todo
        </Link>
      </div>

      {/* Table */}
      <table className="w-full text-left">
        <thead className="bg-[var(--color-surface-container-low)]">
          <tr>
            <th className="px-5 py-3 text-[10px] font-bold uppercase tracking-wider text-[var(--color-secondary)]">
              Referencia
            </th>
            <th className="px-5 py-3 text-[10px] font-bold uppercase tracking-wider text-[var(--color-secondary)]">
              Estado
            </th>
            <th className="px-5 py-3 text-right text-[10px] font-bold uppercase tracking-wider text-[var(--color-secondary)]">
              Monto
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-[var(--color-outline-variant)]/30">
          {items.map((item) => (
            <tr
              key={item.id_comprobante}
              className="hover:bg-[var(--color-surface-container-low)] transition-colors"
            >
              <td className="px-5 py-3">
                <div className="flex flex-col">
                  <span className="font-bold text-[var(--color-on-surface)] text-sm">
                    {(item.referencia ?? item.id_comprobante).slice(0, 12)}
                  </span>
                  <span className="text-[10px] text-[var(--color-secondary)]">
                    {item.fecha_deposito ?? "—"}
                  </span>
                </div>
              </td>
              <td className="px-5 py-3">{estadoBadge(item.estado_actual)}</td>
              <td className="px-5 py-3 text-right font-mono text-sm text-[var(--color-on-surface)]">
                {item.monto !== null ? `$${Number(item.monto).toLocaleString()}` : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {items.length === 0 && (
        <p className="px-5 py-8 text-center text-sm text-[var(--color-secondary)]">
          Sin actividad reciente
        </p>
      )}
    </div>
  );
}
