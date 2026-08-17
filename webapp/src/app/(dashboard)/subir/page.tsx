"use client";

/**
 * Subir Comprobante page — functional client component
 * Upload zone + guidelines + recent uploads table
 * R-SUB-1, design: subir_comprobante/code.html
 */

import { useEffect, useState, useRef } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { fetchApi } from "@/lib/api";
import { getAccessToken } from "@/lib/auth-context";
import type { WebListResponse, WebComprobanteItem } from "@/lib/types";

interface QuotaResponse {
  used: number;
  limit: number;
  plan: string;
  reset_date: string | null;
}

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

export default function SubirPage() {
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [files, setFiles] = useState<File[]>([]);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const [quota, setQuota] = useState<QuotaResponse | null>(null);
  const [recentUploads, setRecentUploads] = useState<WebListResponse | null>(null);

  useEffect(() => {
    async function loadQuota() {
      try {
        const result = await fetchApi<QuotaResponse>("/api/web/auth/quota");
        setQuota(result);
      } catch {
        // Ignore quota errors — not critical
      }
    }
    async function loadRecentUploads() {
      try {
        const result = await fetchApi<WebListResponse>("/api/web/comprobantes/?page_size=5");
        setRecentUploads(result);
      } catch {
        // Ignore errors — not critical
      }
    }
    void loadQuota();
    void loadRecentUploads();
  }, []);

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    if (e.target.files) {
      setFiles(Array.from(e.target.files));
      setUploadError(null);
    }
  }

  function handleDragOver(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragging(true);
  }

  function handleDragLeave() {
    setDragging(false);
  }

  function handleDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragging(false);
    setFiles(Array.from(e.dataTransfer.files));
    setUploadError(null);
  }

  function handleDropZoneClick() {
    fileInputRef.current?.click();
  }

  async function handleProcesar() {
    if (files.length === 0 || uploading) return;

    setUploading(true);
    setUploadError(null);

    try {
      // The endpoint accepts one file at a time — upload sequentially
      for (const file of files) {
        const formData = new FormData();
        formData.append("file", file);

        const token = getAccessToken();
        const headers: HeadersInit = {};
        if (token) headers["Authorization"] = `Bearer ${token}`;

        const response = await fetch("/api/upload-slip/async", {
          method: "POST",
          headers,
          body: formData,
          credentials: "include",
        });

        if (!response.ok) {
          const errorData = await response.json().catch(() => null) as { detail?: string } | null;
          throw new Error(errorData?.detail ?? `Error al procesar ${file.name}`);
        }
      }

      // All files uploaded — clear state and redirect
      setFiles([]);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }

      setTimeout(() => {
        router.push("/historial");
      }, 1500);
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : "Error al procesar el archivo");
    } finally {
      setUploading(false);
    }
  }

  const usagePercentage = quota ? Math.round((quota.used / quota.limit) * 100) : 84;
  const resetDate = quota?.reset_date
    ? new Date(quota.reset_date).toLocaleDateString("es-AR", {
        day: "numeric",
        month: "long",
        year: "numeric",
      })
    : "Sin fecha de reinicio";

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-[-0.02em] leading-8 text-[var(--color-on-surface)]">
            Subir Nuevo Comprobante de Depósito
          </h1>
          <p className="text-sm text-[var(--color-on-surface-variant)] mt-1">
            Envíe documentos escaneados o fotos para el reconocimiento automático por OCR.
          </p>
        </div>
        <span className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-[var(--color-surface-container-high)] border border-[var(--color-outline-variant)] text-xs font-medium text-[var(--color-on-surface)]">
          <span className="w-2 h-2 rounded-full bg-emerald-500" />
          Sistema Listo
        </span>
      </div>

      {/* Bento Grid */}
      <div className="grid grid-cols-12 gap-6">
        {/* Upload Zone — col-span-8 */}
        <div className="col-span-12 lg:col-span-8 space-y-4">
          {/* Drop zone */}
          <div
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            onClick={handleDropZoneClick}
            className={`bg-white border-2 border-dashed rounded-xl p-8 flex flex-col items-center justify-center min-h-[400px] transition-all group cursor-pointer ${
              dragging
                ? "border-blue-400 bg-blue-50"
                : "border-[var(--color-outline-variant)] hover:border-[var(--color-primary-container)] hover:bg-[var(--color-surface-container-low)]"
            }`}
          >
            <div className="w-20 h-20 rounded-full bg-[var(--color-primary-fixed)] flex items-center justify-center text-[var(--color-primary)] mb-4 group-hover:scale-110 transition-transform">
              <span className="material-symbols-outlined text-[40px]">cloud_upload</span>
            </div>
            <h2 className="text-xl font-semibold tracking-[-0.01em] leading-7 text-[var(--color-on-surface)] text-center">
              Arrastre archivos aquí o haga clic para buscar
            </h2>
            <p className="text-sm text-[var(--color-on-surface-variant)] text-center max-w-sm mt-2">
              Suba comprobantes individuales o múltiples. El motor OCR dividirá y procesará
              automáticamente cada página.
            </p>
            <div className="mt-8 flex flex-wrap justify-center gap-4">
              <div className="flex items-center gap-2 px-4 py-2 bg-[var(--color-surface-container)] rounded-lg border border-[var(--color-outline-variant)]">
                <span className="material-symbols-outlined text-sm text-[var(--color-on-surface-variant)]">
                  picture_as_pdf
                </span>
                <span className="text-xs font-medium text-[var(--color-on-surface-variant)]">
                  PDF (Vector/Escaneo)
                </span>
              </div>
              <div className="flex items-center gap-2 px-4 py-2 bg-[var(--color-surface-container)] rounded-lg border border-[var(--color-outline-variant)]">
                <span className="material-symbols-outlined text-sm text-[var(--color-on-surface-variant)]">
                  image
                </span>
                <span className="text-xs font-medium text-[var(--color-on-surface-variant)]">
                  JPG / PNG Alta Res
                </span>
              </div>
            </div>
            <input
              ref={fileInputRef}
              id="file-upload"
              type="file"
              className="hidden"
              accept=".pdf,.jpg,.jpeg,.png"
              multiple
              onChange={handleFileChange}
            />
          </div>

          {/* Action bar */}
          <div className="flex items-center justify-between p-4 bg-white border border-[var(--color-outline-variant)] rounded-xl shadow-sm">
            <span className="text-sm text-[var(--color-on-surface-variant)] italic">
              {files.length === 0
                ? "Ningún archivo seleccionado"
                : files.length === 1
                  ? files[0].name
                  : `${files.length} archivos seleccionados`}
            </span>
            <button
              disabled={files.length === 0 || uploading}
              onClick={handleProcesar}
              className={`px-6 py-2 rounded-lg text-base font-semibold flex items-center gap-2 ${
                files.length > 0 && !uploading
                  ? "bg-[var(--color-primary)] text-[var(--color-on-primary)] hover:bg-[var(--color-primary-container)] cursor-pointer"
                  : "bg-[var(--color-outline-variant)] text-[var(--color-on-surface-variant)] opacity-50 cursor-not-allowed"
              }`}
            >
              {uploading ? (
                <>
                  <div className="animate-spin rounded-full h-4 w-4 border-2 border-white border-t-transparent" />
                  Procesando...
                </>
              ) : (
                <>
                  <span className="material-symbols-outlined text-[18px]">play_arrow</span>
                  Procesar
                </>
              )}
            </button>
          </div>

          {/* Upload error */}
          {uploadError && (
            <div className="rounded-lg border border-red-200 bg-red-50 p-4">
              <div className="flex items-start gap-3">
                <span className="material-symbols-outlined text-red-600">error</span>
                <p className="text-sm text-red-700">{uploadError}</p>
              </div>
            </div>
          )}

          {/* Success message */}
          {uploading === false && files.length === 0 && !uploadError && (
            <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-4">
              <div className="flex items-start gap-3">
                <span className="material-symbols-outlined text-emerald-600">check_circle</span>
                <p className="text-sm text-emerald-700">Comprobante enviado correctamente</p>
              </div>
            </div>
          )}
        </div>

        {/* Guidelines panel — col-span-4 */}
        <div className="col-span-12 lg:col-span-4 space-y-6">
          {/* Recognition tips */}
          <div className="bg-white border border-[var(--color-outline-variant)] rounded-xl overflow-hidden">
            <div className="p-4 border-b border-[var(--color-outline-variant)] bg-[var(--color-surface-container-low)]">
              <h3 className="text-base font-semibold flex items-center gap-2 text-[var(--color-on-surface)]">
                <span className="material-symbols-outlined text-[var(--color-primary)]">
                  tips_and_updates
                </span>
                Pautas para el Reconocimiento
              </h3>
            </div>
            <div className="p-6 space-y-4">
              <div className="flex gap-4">
                <div className="shrink-0 w-8 h-8 rounded bg-emerald-50 text-emerald-600 flex items-center justify-center">
                  <span className="material-symbols-outlined text-lg">wb_sunny</span>
                </div>
                <div>
                  <p className="text-sm font-semibold text-[var(--color-on-surface)]">
                    Iluminación Clara
                  </p>
                  <p className="text-xs text-[var(--color-on-surface-variant)]">
                    Evite sombras intensas y reflejos en papel brillante.
                  </p>
                </div>
              </div>
              <div className="flex gap-4">
                <div className="shrink-0 w-8 h-8 rounded bg-blue-50 text-blue-600 flex items-center justify-center">
                  <span className="material-symbols-outlined text-lg">crop_free</span>
                </div>
                <div>
                  <p className="text-sm font-semibold text-[var(--color-on-surface)]">
                    Superficie Plana
                  </p>
                  <p className="text-xs text-[var(--color-on-surface-variant)]">
                    Mantenga el documento plano para evitar distorsiones de perspectiva.
                  </p>
                </div>
              </div>
              <div className="flex gap-4">
                <div className="shrink-0 w-8 h-8 rounded bg-amber-50 text-amber-600 flex items-center justify-center">
                  <span className="material-symbols-outlined text-lg">blur_off</span>
                </div>
                <div>
                  <p className="text-sm font-semibold text-[var(--color-on-surface)]">
                    Alta Nitidez
                  </p>
                  <p className="text-xs text-[var(--color-on-surface-variant)]">
                    Asegúrese de que el texto sea legible y no esté borroso.
                  </p>
                </div>
              </div>
            </div>
          </div>

          {/* Usage card */}
          <div className="bg-white border border-[var(--color-outline-variant)] rounded-xl p-6">
            <h3 className="text-xs font-medium text-[var(--color-on-surface-variant)] uppercase tracking-wider mb-4">
              USO ESTE MES
            </h3>
            <div className="space-y-2">
              <div className="flex justify-between items-center">
                <span className="text-sm text-[var(--color-on-surface)]">Tokens Restantes</span>
                <span className="text-base font-semibold text-[var(--color-on-surface)]">
                  {quota ? `${quota.used} / ${quota.limit.toLocaleString("es-AR")}` : "842 / 1,000"}
                </span>
              </div>
              <div className="h-2 w-full bg-[var(--color-surface-container)] rounded-full overflow-hidden">
                <div
                  className="h-full bg-[var(--color-primary)] rounded-full"
                  style={{ width: `${usagePercentage}%` }}
                />
              </div>
              <p className="text-[10px] text-[var(--color-on-surface-variant)]">
                Próximo reinicio: {resetDate}
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Recent Uploads Table */}
      <div className="bg-white border border-[var(--color-outline-variant)] rounded-xl shadow-sm">
        <div className="p-4 flex items-center justify-between border-b border-[var(--color-outline-variant)]">
          <h3 className="text-base font-semibold text-[var(--color-on-surface)]">
            Últimos Archivos Subidos
          </h3>
          <Link
            href="/historial"
            className="text-xs font-bold text-[var(--color-primary)] hover:underline"
          >
            Ver Historial
          </Link>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full border-collapse">
            <thead className="bg-[var(--color-surface-container-low)]">
              <tr>
                <th className="px-6 py-4 text-left text-xs font-bold text-[var(--color-on-surface-variant)] uppercase tracking-wider">
                  NOMBRE DE ARCHIVO
                </th>
                <th className="px-6 py-4 text-left text-xs font-bold text-[var(--color-on-surface-variant)] uppercase tracking-wider">
                  FECHA
                </th>
                <th className="px-6 py-4 text-left text-xs font-bold text-[var(--color-on-surface-variant)] uppercase tracking-wider">
                  ESTADO
                </th>
                <th className="px-6 py-4 text-left text-xs font-bold text-[var(--color-on-surface-variant)] uppercase tracking-wider">
                  ACCIONES
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--color-surface-container)]">
              {recentUploads && recentUploads.items.length > 0 ? (
                recentUploads.items.map((item: WebComprobanteItem) => {
                  const fileName = item.imagen_path.split("/").pop() ?? item.imagen_path;
                  const fecha = new Date(item.fecha_registro).toLocaleString("es-AR", {
                    dateStyle: "short",
                    timeStyle: "short",
                  });

                  return (
                    <tr
                      key={item.id_comprobante}
                      className="hover:bg-[var(--color-surface-container-low)] transition-colors"
                    >
                      <td className="px-6 py-4 text-sm text-[var(--color-on-surface)]">
                        {fileName}
                      </td>
                      <td className="px-6 py-4 text-sm text-[var(--color-on-surface-variant)]">
                        {fecha}
                      </td>
                      <td className="px-6 py-4">{getStatusBadge(item.estado_actual)}</td>
                      <td className="px-6 py-4">
                        <Link
                          href={`/historial/${item.id_comprobante}`}
                          className="text-[var(--color-primary)] hover:text-[var(--color-on-primary-fixed-variant)] transition-colors"
                        >
                          <span className="material-symbols-outlined text-[20px]">visibility</span>
                        </Link>
                      </td>
                    </tr>
                  );
                })
              ) : (
                <tr>
                  <td colSpan={4} className="px-6 py-8 text-center text-sm text-[var(--color-on-surface-variant)]">
                    No hay archivos recientes
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
