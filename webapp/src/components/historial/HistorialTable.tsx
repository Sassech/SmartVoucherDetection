"use client";

/**
 * HistorialTable — paginated comprobantes table — R-39, R-42, S-29, S-30, S-31, 4.D.5
 */

import { Badge } from "@/components/ui/badge";
import type { WebComprobanteItem } from "@/lib/types";
import type { BadgeProps } from "@/components/ui/badge";

function estadoToBadgeVariant(estado: WebComprobanteItem["estado"]): BadgeProps["variant"] {
  switch (estado) {
    case "procesado":
      return "valido";
    case "duplicado":
      return "duplicado";
    case "sospechoso":
      return "sospechoso";
    case "en_revision":
      return "en_revision";
    case "error":
      return "error";
    case "pendiente":
    default:
      return "default";
  }
}

interface HistorialTableProps {
  items: WebComprobanteItem[];
  hasMore: boolean;
  onNextPage: () => void;
  onRowClick: (id: string) => void;
}

export function HistorialTable({ items, hasMore, onNextPage, onRowClick }: HistorialTableProps) {
  if (items.length === 0) {
    return (
      <div className="rounded-[var(--radius-lg)] border border-[var(--color-outline-variant)] bg-[var(--color-surface)] p-10 text-center">
        <p className="text-sm text-[var(--color-on-surface-variant)]">Sin resultados</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="rounded-[var(--radius-lg)] border border-[var(--color-outline-variant)] bg-[var(--color-surface)] overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-[var(--color-surface-container-low)]">
            <tr>
              <th className="px-4 py-3 text-left text-xs font-medium text-[var(--color-on-surface-variant)] uppercase tracking-wide">
                Folio
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-[var(--color-on-surface-variant)] uppercase tracking-wide">
                Monto
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-[var(--color-on-surface-variant)] uppercase tracking-wide">
                Fecha
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-[var(--color-on-surface-variant)] uppercase tracking-wide">
                Estado
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-[var(--color-on-surface-variant)] uppercase tracking-wide">
                Acciones
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[var(--color-outline-variant)]">
            {items.map((item) => (
              <tr
                key={item.id_comprobante}
                className="hover:bg-[var(--color-surface-container-low)] transition-colors cursor-pointer"
                onClick={() => onRowClick(item.id_comprobante)}
              >
                <td className="px-4 py-3 font-mono text-xs text-[var(--color-on-surface)]">
                  {item.folio.slice(0, 8)}
                </td>
                <td className="px-4 py-3 text-[var(--color-on-surface)]">
                  {item.monto !== null ? `$${item.monto.toLocaleString()}` : "—"}
                </td>
                <td className="px-4 py-3 text-[var(--color-on-surface-variant)]">
                  {item.fecha_deposito ?? "—"}
                </td>
                <td className="px-4 py-3">
                  <Badge variant={estadoToBadgeVariant(item.estado)}>
                    {item.estado}
                  </Badge>
                </td>
                <td className="px-4 py-3">
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      onRowClick(item.id_comprobante);
                    }}
                    className="text-xs font-medium text-[var(--color-primary)] hover:underline"
                    aria-label={`Ver comprobante ${item.folio.slice(0, 8)}`}
                  >
                    Ver
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {hasMore && (
        <div className="flex justify-center">
          <button
            type="button"
            onClick={onNextPage}
            className="rounded-[var(--radius-md)] border border-[var(--color-outline-variant)] bg-[var(--color-surface)] px-4 py-2 text-sm font-medium text-[var(--color-primary)] hover:bg-[var(--color-surface-container-low)] transition-colors"
          >
            Siguiente página
          </button>
        </div>
      )}
    </div>
  );
}
