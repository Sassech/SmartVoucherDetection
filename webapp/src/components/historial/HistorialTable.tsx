"use client";

/**
 * HistorialTable — paginated comprobantes table — R-39, R-42, S-29, S-30, S-31, 4.D.5
 */

import Link from "next/link";
import type { WebComprobanteItem } from "@/lib/types";

type ItemWithSimilitud = WebComprobanteItem & { similitud?: number };

function StatusBadge({ estado }: { estado: WebComprobanteItem["estado"] }) {
  switch (estado) {
    case "procesado":
      return (
        <span className="px-3 py-1 rounded-[4px] bg-green-100 text-green-800 text-[11px] font-bold uppercase">
          Válido
        </span>
      );
    case "duplicado":
      return (
        <span className="px-3 py-1 rounded-[4px] bg-red-100 text-red-800 text-[11px] font-bold uppercase">
          Duplicado
        </span>
      );
    case "sospechoso":
      return (
        <span className="px-3 py-1 rounded-[4px] bg-orange-100 text-orange-800 text-[11px] font-bold uppercase">
          Sospechoso
        </span>
      );
    case "en_revision":
      return (
        <span className="px-3 py-1 rounded-[4px] bg-blue-100 text-blue-800 text-[11px] font-bold uppercase">
          En Revisión
        </span>
      );
    case "error":
      return (
        <span className="px-3 py-1 rounded-[4px] bg-red-50 text-red-500 text-[11px] font-bold uppercase">
          Error
        </span>
      );
    default:
      return (
        <span className="px-3 py-1 rounded-[4px] bg-slate-100 text-slate-500 text-[11px] font-bold uppercase">
          Pendiente
        </span>
      );
  }
}

function similitudColor(similitud: number | undefined): string {
  if (similitud === undefined) return "#3b82f6";
  if (similitud >= 95) return "#ef4444";
  if (similitud >= 80) return "#fb923c";
  return "#3b82f6";
}

interface HistorialTableProps {
  items: ItemWithSimilitud[];
  hasMore: boolean;
  onNextPage: () => void;
  onRowClick: (id: string) => void;
  currentPage?: number;
  total?: number;
  pageSize?: number;
}

export function HistorialTable({
  items,
  hasMore,
  onNextPage,
  onRowClick,
  currentPage = 1,
  total,
  pageSize = 20,
}: HistorialTableProps) {
  if (items.length === 0) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white p-10 text-center shadow-sm">
        <p className="text-sm text-[var(--color-secondary)]">Sin resultados</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-[#F9FAFB] border-b border-slate-100">
                <th className="px-6 py-4 text-[11px] font-bold uppercase tracking-wider text-[var(--color-secondary)]">
                  Fecha
                </th>
                <th className="px-6 py-4 text-[11px] font-bold uppercase tracking-wider text-[var(--color-secondary)]">
                  Folio / REF
                </th>
                <th className="px-6 py-4 text-[11px] font-bold uppercase tracking-wider text-[var(--color-secondary)]">
                  Monto
                </th>
                <th className="px-6 py-4 text-[11px] font-bold uppercase tracking-wider text-[var(--color-secondary)]">
                  Estado
                </th>
                <th className="px-6 py-4 text-[11px] font-bold uppercase tracking-wider text-[var(--color-secondary)]">
                  Puntaje de Similitud
                </th>
                <th className="px-6 py-4 text-[11px] font-bold uppercase tracking-wider text-[var(--color-secondary)] text-right">
                  Acciones
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {items.map((item) => (
                <tr
                  key={item.id_comprobante}
                  className="hover:bg-[#F3F4F6] transition-colors cursor-pointer"
                  onClick={() => onRowClick(item.id_comprobante)}
                >
                  <td className="px-6 py-4 text-sm text-[var(--color-on-surface)]">
                    {item.fecha_deposito ?? "—"}
                  </td>
                  <td className="px-6 py-4 font-mono text-sm text-blue-600 font-medium">
                    {item.folio.slice(0, 14)}
                  </td>
                  <td className="px-6 py-4 text-sm font-semibold text-[var(--color-on-surface)]">
                    {item.monto !== null ? `$${item.monto.toLocaleString()}` : "—"}
                  </td>
                  <td className="px-6 py-4">
                    <StatusBadge estado={item.estado} />
                  </td>
                  <td className="px-6 py-4">
                    <div className="flex flex-col gap-1">
                      <div className="w-16 h-1.5 bg-slate-100 rounded-full overflow-hidden">
                        <div
                          className="h-full rounded-full"
                          style={{
                            width: `${item.similitud ?? 0}%`,
                            backgroundColor: similitudColor(item.similitud),
                          }}
                        />
                      </div>
                      <span className="text-xs font-medium text-[var(--color-secondary)]">
                        {item.similitud !== undefined ? `${item.similitud}%` : "—"}
                      </span>
                    </div>
                  </td>
                  <td className="px-6 py-4 text-right space-x-1">
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        onRowClick(item.id_comprobante);
                      }}
                      className="p-2 text-slate-400 hover:text-[var(--color-primary)] transition-colors"
                      aria-label={`Ver comprobante ${item.folio.slice(0, 8)}`}
                      title="Ver Detalles"
                    >
                      <span className="material-symbols-outlined text-[20px]">visibility</span>
                    </button>
                    <button
                      type="button"
                      onClick={(e) => e.stopPropagation()}
                      className="p-2 text-slate-400 hover:text-[var(--color-primary)] transition-colors"
                      aria-label={`Descargar comprobante ${item.folio.slice(0, 8)}`}
                      title="Descargar"
                    >
                      <span className="material-symbols-outlined text-[20px]">download</span>
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {hasMore && (
          <div className="flex items-center justify-between px-6 py-4 bg-white border-t border-slate-100">
            <span className="text-sm text-[var(--color-secondary)]">
              Mostrando resultados parciales
            </span>
            <button
              type="button"
              onClick={onNextPage}
              className="flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-2 text-sm font-medium text-[var(--color-primary)] hover:bg-slate-50 transition-colors"
            >
              Siguiente página
              <span className="material-symbols-outlined text-[18px]">chevron_right</span>
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
