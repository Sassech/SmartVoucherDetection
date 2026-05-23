/**
 * OcrFields — labeled rows for OCR-extracted comprobante data — R-43, S-33, 4.D.8
 */

import type { WebComprobanteItem } from "@/lib/types";

interface OcrFieldsProps {
  item: WebComprobanteItem;
}

export function OcrFields({ item }: OcrFieldsProps) {
  const fields = [
    {
      label: "Monto de Transacción",
      value: item.monto !== null ? `$${item.monto.toLocaleString()}` : "—",
      highlight: true,
    },
    {
      label: "Banco Emisor",
      value: item.banco ?? "—",
      highlight: false,
    },
    {
      label: "Número de Referencia",
      value: item.referencia ?? "—",
      highlight: false,
      mono: true,
    },
    {
      label: "Fecha de Depósito",
      value: item.fecha_deposito ?? "—",
      highlight: false,
    },
  ];

  return (
    <div className="rounded-xl border border-[var(--color-outline-variant)] bg-white overflow-hidden shadow-sm">
      {/* Card header */}
      <div className="px-5 py-4 border-b border-[var(--color-outline-variant)] bg-[var(--color-surface-container-low)] flex items-center gap-2">
        <span className="material-symbols-outlined text-[var(--color-primary)] text-[20px]">
          data_object
        </span>
        <h2 className="text-sm font-semibold text-[var(--color-on-surface)]">
          Datos OCR Extraídos
        </h2>
      </div>

      {/* Header row */}
      <div className="bg-[#F9FAFB] border-b border-[var(--color-outline-variant)] px-5 py-3 grid grid-cols-2">
        <span className="text-[11px] font-bold uppercase tracking-wider text-[var(--color-secondary)]">
          Campo
        </span>
        <span className="text-[11px] font-bold uppercase tracking-wider text-[var(--color-secondary)]">
          Valor Extraído
        </span>
      </div>

      {/* Field rows */}
      <div className="divide-y divide-slate-100">
        {fields.map(({ label, value, highlight, mono }) => (
          <div
            key={label}
            className="px-5 py-3 grid grid-cols-2 hover:bg-slate-50 transition-colors"
          >
            <span className="text-sm text-[var(--color-secondary)]">{label}</span>
            <span
              className={
                highlight
                  ? "text-lg font-bold text-[var(--color-primary)]"
                  : mono
                    ? "text-sm font-mono bg-[var(--color-surface-container)] px-2 py-0.5 rounded text-[var(--color-on-surface)] w-fit"
                    : "text-sm font-semibold text-[var(--color-on-surface)]"
              }
            >
              {value}
            </span>
          </div>
        ))}
      </div>

      {/* Footer info */}
      <div className="bg-[var(--color-surface-container-low)] px-5 py-3 border-t border-[var(--color-outline-variant)] flex items-start gap-2">
        <span className="material-symbols-outlined text-[var(--color-secondary)] text-[18px] shrink-0 mt-0.5">
          info
        </span>
        <p className="text-[11px] text-[var(--color-secondary)] leading-relaxed">
          Datos extraídos automáticamente por el motor OCR. Verifique la información antes de tomar una decisión.
        </p>
      </div>
    </div>
  );
}
