"use client";

/**
 * Revision detail page — client component with 7/5 grid layout.
 * R-43, R-44, R-45, R-46, S-33, S-34, S-35, S-36, S-37, 4.D.11
 */

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { fetchApi } from "@/lib/api";
import { VoucherViewer } from "@/components/revision/VoucherViewer";
import { OcrFields } from "@/components/revision/OcrFields";
import { DuplicatePanel } from "@/components/revision/DuplicatePanel";
import { Skeleton } from "@/components/ui/skeleton";
import type { WebComprobanteItem } from "@/lib/types";

export default function RevisionPage() {
  const params = useParams<{ id: string }>();
  const id = params?.id ?? "";

  const [item, setItem] = useState<WebComprobanteItem | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;

    const load = async () => {
      setLoading(true);
      try {
        const data = await fetchApi<WebComprobanteItem>(`/api/web/comprobantes/${id}`);
        setItem(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Error al cargar el comprobante");
      } finally {
        setLoading(false);
      }
    };

    void load();
  }, [id]);

  if (loading) {
    return (
      <div className="grid grid-cols-12 gap-6">
        <div className="col-span-7 flex flex-col gap-4">
          <Skeleton className="h-64 w-full" />
          <Skeleton className="h-40 w-full" />
        </div>
        <div className="col-span-5">
          <Skeleton className="h-80 w-full" />
        </div>
      </div>
    );
  }

  if (error || !item) {
    return (
      <div className="flex flex-col gap-4">
        <h1 className="text-2xl font-semibold tracking-tight text-[var(--color-on-surface)]">
          Revisión de Comprobante
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
    <div className="flex flex-col gap-5">
      <h1 className="text-2xl font-semibold tracking-tight text-[var(--color-on-surface)]">
        Revisión de Comprobante
      </h1>

      <div className="grid grid-cols-12 gap-6">
        {/* Left column — 7/12 */}
        <div className="col-span-12 lg:col-span-7 flex flex-col gap-4">
          <VoucherViewer src={item.imagen_path} />
          <OcrFields item={item} />

          {/* OCR raw text if available */}
          {item.texto_extraido && (
            <div className="rounded-[var(--radius-lg)] border border-[var(--color-outline-variant)] bg-[var(--color-surface)] p-5">
              <h2 className="mb-3 text-sm font-semibold text-[var(--color-on-surface)]">
                Texto Extraído
              </h2>
              <pre className="overflow-auto rounded-[var(--radius-sm)] bg-[var(--color-surface-container-low)] p-3 text-xs text-[var(--color-on-surface)]">
                {item.texto_extraido}
              </pre>
            </div>
          )}
        </div>

        {/* Right column — 5/12 */}
        <div className="col-span-12 lg:col-span-5">
          <DuplicatePanel item={item} />
        </div>
      </div>
    </div>
  );
}
