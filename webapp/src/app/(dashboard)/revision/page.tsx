"use client";

/**
 * Cola de Revisión page — client component
 * Lists comprobantes in review states (en_revision)
 */

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { fetchApi } from "@/lib/api";
import type { WebListResponse, WebComprobanteItem } from "@/lib/types";

function getStatusBadge(estado: string) {
  const colors: Record<string, { bg: string; text: string; border: string }> = {
    valido: { bg: "bg-emerald-50", text: "text-emerald-700", border: "border-emerald-100" },
    sospechoso: { bg: "bg-amber-50", text: "text-amber-700", border: "border-amber-100" },
    en_revision: { bg: "bg-amber-50", text: "text-amber-700", border: "border-amber-100" },
    duplicado: { bg: "bg-red-50", text: "text-red-700", border: "border-red-100" },
    error: { bg: "bg-red-50", text: "text-red-700", border: "border-red-100" },
    recibido: { bg: "bg-blue-50", text: "text-blue-700", border: "border-blue-100" },
    procesando: { bg: "bg-blue-50", text: "text-blue-700", border: "border-blue-100" },
    comparando: { bg: "bg-blue-50", text: "text-blue-700", border: "border-blue-100" },
  };
  const color = colors[estado.toLowerCase()] ?? colors.recibido;
  return (
    <span
      className={`px-2 py-0.5 rounded text-xs font-medium border ${color.bg} ${color.text} ${color.border}`}
    >
      {estado}
    </span>
  );
}

export default function RevisionPage() {
  const router = useRouter();
  const [data, setData] = useState<WebListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadData() {
      setLoading(true);
      setError(null);
      try {
        const result = await fetchApi<WebListResponse>(
          "/api/web/comprobantes/?estado=en_revision&page_size=20"
        );
        setData(result);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Error al cargar los datos");
      } finally {
        setLoading(false);
      }
    }
    void loadData();
  }, []);

  function handleRowClick(id: string) {
    router.push(`/revision/${id}`);
  }

  return (
    <div className="flex flex-col gap-5">
      <h1 className="text-2xl font-semibold tracking-tight text-[var(--color-on-surface)]">
        Cola de Revisión
      </h1>

      {loading ? (
        <div className="rounded-[var(--radius-lg)] border border-[var(--color-outline-variant)] bg-[var(--color-surface)] p-10 text-center">
          <div className="flex flex-col items-center gap-3">
            <div className="animate-spin rounded-full h-8 w-8 border-2 border-[var(--color-primary)] border-t-transparent" />
            <p className="text-sm text-[var(--color-on-surface-variant)]">Cargando…</p>
          </div>
        </div>
      ) : error ? (
        <div className="rounded-[var(--radius-lg)] border border-red-200 bg-red-50 p-6">
          <div className="flex items-start gap-3">
            <span className="material-symbols-outlined text-red-600">error</span>
            <div>
              <h3 className="text-sm font-semibold text-red-900">Error</h3>
              <p className="text-sm text-red-700 mt-1">{error}</p>
            </div>
          </div>
        </div>
      ) : !data || data.items.length === 0 ? (
        <div className="rounded-[var(--radius-lg)] border border-[var(--color-outline-variant)] bg-[var(--color-surface)] p-10 text-center">
          <div className="flex flex-col items-center gap-3">
            <span className="material-symbols-outlined text-5xl text-[var(--color-on-surface-variant)]">
              fact_check
            </span>
            <p className="text-sm text-[var(--color-on-surface-variant)]">
              No hay comprobantes en revisión
            </p>
          </div>
        </div>
      ) : (
        <div className="rounded-[var(--radius-lg)] border border-[var(--color-outline-variant)] bg-[var(--color-surface)] overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full border-collapse">
              <thead className="bg-[var(--color-surface-container-low)]">
                <tr>
                  <th className="px-6 py-4 text-left text-xs font-bold text-[var(--color-on-surface-variant)] uppercase tracking-wider">
                    Archivo
                  </th>
                  <th className="px-6 py-4 text-left text-xs font-bold text-[var(--color-on-surface-variant)] uppercase tracking-wider">
                    Referencia
                  </th>
                  <th className="px-6 py-4 text-left text-xs font-bold text-[var(--color-on-surface-variant)] uppercase tracking-wider">
                    Monto
                  </th>
                  <th className="px-6 py-4 text-left text-xs font-bold text-[var(--color-on-surface-variant)] uppercase tracking-wider">
                    Fecha
                  </th>
                  <th className="px-6 py-4 text-left text-xs font-bold text-[var(--color-on-surface-variant)] uppercase tracking-wider">
                    Estado
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--color-surface-container)]">
                {data.items.map((item: WebComprobanteItem) => {
                  const fileName = item.imagen_path.split("/").pop() ?? item.imagen_path;
                  const fecha = item.fecha_deposito
                    ? new Date(item.fecha_deposito).toLocaleDateString("es-AR", {
                        day: "2-digit",
                        month: "2-digit",
                        year: "numeric",
                      })
                    : "—";

                  return (
                    <tr
                      key={item.id_comprobante}
                      onClick={() => handleRowClick(item.id_comprobante)}
                      className="hover:bg-[var(--color-surface-container-low)] transition-colors cursor-pointer"
                    >
                      <td className="px-6 py-4 text-sm text-[var(--color-on-surface)]">
                        {fileName}
                      </td>
                      <td className="px-6 py-4 text-sm text-[var(--color-on-surface)]">
                        {item.referencia ?? "—"}
                      </td>
                      <td className="px-6 py-4 text-sm text-[var(--color-on-surface)]">
                        {item.monto ? `$${item.monto.toLocaleString("es-AR")}` : "—"}
                      </td>
                      <td className="px-6 py-4 text-sm text-[var(--color-on-surface-variant)]">
                        {fecha}
                      </td>
                      <td className="px-6 py-4">{getStatusBadge(item.estado_actual)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
