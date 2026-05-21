/**
 * RecentActivity — recent comprobantes table for dashboard — R-38, S-25, 4.D.2
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

interface RecentActivityProps {
  items: WebComprobanteItem[];
}

export function RecentActivity({ items }: RecentActivityProps) {
  return (
    <div className="rounded-[var(--radius-lg)] border border-[var(--color-outline-variant)] bg-[var(--color-surface)] overflow-hidden">
      <div className="px-5 py-4 border-b border-[var(--color-outline-variant)]">
        <h2 className="text-sm font-semibold text-[var(--color-on-surface)]">
          Actividad Reciente
        </h2>
      </div>
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
          </tr>
        </thead>
        <tbody className="divide-y divide-[var(--color-outline-variant)]">
          {items.map((item) => (
            <tr key={item.id_comprobante} className="hover:bg-[var(--color-surface-container-low)] transition-colors">
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
            </tr>
          ))}
        </tbody>
      </table>
      {items.length === 0 && (
        <p className="px-4 py-6 text-center text-sm text-[var(--color-on-surface-variant)]">
          Sin actividad reciente
        </p>
      )}
    </div>
  );
}
