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
      label: "Monto",
      value: item.monto !== null ? `$${item.monto.toLocaleString()}` : "—",
    },
    {
      label: "Banco",
      value: item.banco ?? "—",
    },
    {
      label: "Referencia",
      value: item.referencia ?? "—",
    },
    {
      label: "Fecha de depósito",
      value: item.fecha_deposito ?? "—",
    },
  ];

  return (
    <div className="rounded-[var(--radius-lg)] border border-[var(--color-outline-variant)] bg-[var(--color-surface)] p-5">
      <h2 className="mb-4 text-sm font-semibold text-[var(--color-on-surface)]">
        Datos OCR Extraídos
      </h2>
      <dl className="flex flex-col gap-3">
        {fields.map(({ label, value }) => (
          <div key={label} className="flex justify-between text-sm">
            <dt className="text-[var(--color-on-surface-variant)]">{label}</dt>
            <dd className="font-medium text-[var(--color-on-surface)]">{value}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
