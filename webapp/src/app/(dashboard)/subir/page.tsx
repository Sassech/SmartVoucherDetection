/**
 * Subir Comprobante page — RSC
 * Upload zone + guidelines + recent uploads table
 * R-SUB-1, design: subir_comprobante/code.html
 */

import Link from "next/link";

export default function SubirPage() {
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
          <label
            htmlFor="file-upload"
            className="bg-white border-2 border-dashed border-[var(--color-outline-variant)] rounded-xl p-8 flex flex-col items-center justify-center min-h-[400px] hover:border-[var(--color-primary-container)] hover:bg-[var(--color-surface-container-low)] transition-all group cursor-pointer"
          >
            <div className="w-20 h-20 rounded-full bg-[var(--color-primary-fixed)] flex items-center justify-center text-[var(--color-primary)] mb-4 group-hover:scale-110 transition-transform">
              <span className="material-symbols-outlined text-[40px]">cloud_upload</span>
            </div>
            <h2 className="text-xl font-semibold tracking-[-0.01em] leading-7 text-[var(--color-on-surface)] text-center">
              Arrastre archivos aquí o haga clic para buscar
            </h2>
            <p className="text-sm text-[var(--color-on-surface-variant)] text-center max-w-sm mt-2">
              Suba comprobantes individuales o múltiples. El motor OCR dividirá y procesará automáticamente cada página.
            </p>
            <div className="mt-8 flex flex-wrap justify-center gap-4">
              <div className="flex items-center gap-2 px-4 py-2 bg-[var(--color-surface-container)] rounded-lg border border-[var(--color-outline-variant)]">
                <span className="material-symbols-outlined text-sm text-[var(--color-on-surface-variant)]">picture_as_pdf</span>
                <span className="text-xs font-medium text-[var(--color-on-surface-variant)]">PDF (Vector/Escaneo)</span>
              </div>
              <div className="flex items-center gap-2 px-4 py-2 bg-[var(--color-surface-container)] rounded-lg border border-[var(--color-outline-variant)]">
                <span className="material-symbols-outlined text-sm text-[var(--color-on-surface-variant)]">image</span>
                <span className="text-xs font-medium text-[var(--color-on-surface-variant)]">JPG / PNG Alta Res</span>
              </div>
            </div>
            <input id="file-upload" type="file" className="hidden" accept=".pdf,.jpg,.jpeg,.png" />
          </label>

          {/* Action bar */}
          <div className="flex items-center justify-between p-4 bg-white border border-[var(--color-outline-variant)] rounded-xl shadow-sm">
            <span className="text-sm text-[var(--color-on-surface-variant)] italic">
              Ningún archivo seleccionado
            </span>
            <button
              disabled
              className="px-6 py-2 bg-[var(--color-outline-variant)] text-[var(--color-on-surface-variant)] rounded-lg text-base font-semibold opacity-50 cursor-not-allowed flex items-center gap-2"
            >
              <span className="material-symbols-outlined text-[18px]">play_arrow</span>
              Procesar
            </button>
          </div>
        </div>

        {/* Guidelines panel — col-span-4 */}
        <div className="col-span-12 lg:col-span-4 space-y-6">
          {/* Recognition tips */}
          <div className="bg-white border border-[var(--color-outline-variant)] rounded-xl overflow-hidden">
            <div className="p-4 border-b border-[var(--color-outline-variant)] bg-[var(--color-surface-container-low)]">
              <h3 className="text-base font-semibold flex items-center gap-2 text-[var(--color-on-surface)]">
                <span className="material-symbols-outlined text-[var(--color-primary)]">tips_and_updates</span>
                Pautas para el Reconocimiento
              </h3>
            </div>
            <div className="p-6 space-y-4">
              <div className="flex gap-4">
                <div className="shrink-0 w-8 h-8 rounded bg-emerald-50 text-emerald-600 flex items-center justify-center">
                  <span className="material-symbols-outlined text-lg">wb_sunny</span>
                </div>
                <div>
                  <p className="text-sm font-semibold text-[var(--color-on-surface)]">Iluminación Clara</p>
                  <p className="text-xs text-[var(--color-on-surface-variant)]">Evite sombras intensas y reflejos en papel brillante.</p>
                </div>
              </div>
              <div className="flex gap-4">
                <div className="shrink-0 w-8 h-8 rounded bg-blue-50 text-blue-600 flex items-center justify-center">
                  <span className="material-symbols-outlined text-lg">crop_free</span>
                </div>
                <div>
                  <p className="text-sm font-semibold text-[var(--color-on-surface)]">Superficie Plana</p>
                  <p className="text-xs text-[var(--color-on-surface-variant)]">Mantenga el documento plano para evitar distorsiones de perspectiva.</p>
                </div>
              </div>
              <div className="flex gap-4">
                <div className="shrink-0 w-8 h-8 rounded bg-amber-50 text-amber-600 flex items-center justify-center">
                  <span className="material-symbols-outlined text-lg">blur_off</span>
                </div>
                <div>
                  <p className="text-sm font-semibold text-[var(--color-on-surface)]">Alta Nitidez</p>
                  <p className="text-xs text-[var(--color-on-surface-variant)]">Asegúrese de que el texto sea legible y no esté borroso.</p>
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
                <span className="text-base font-semibold text-[var(--color-on-surface)]">842 / 1,000</span>
              </div>
              <div className="h-2 w-full bg-[var(--color-surface-container)] rounded-full overflow-hidden">
                <div className="h-full bg-[var(--color-primary)] rounded-full" style={{ width: "84%" }} />
              </div>
              <p className="text-[10px] text-[var(--color-on-surface-variant)]">Próximo reinicio: 1 de nov de 2023</p>
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
              <tr className="hover:bg-[var(--color-surface-container-low)] transition-colors">
                <td className="px-6 py-4 text-sm text-[var(--color-on-surface)]">comprobante_deposito_0921.pdf</td>
                <td className="px-6 py-4 text-sm text-[var(--color-on-surface-variant)]">hace 2 mins</td>
                <td className="px-6 py-4">
                  <span className="px-2 py-0.5 rounded bg-emerald-50 text-emerald-700 text-xs font-medium border border-emerald-100">
                    Válido
                  </span>
                </td>
                <td className="px-6 py-4">
                  <button className="text-[var(--color-primary)] hover:text-[var(--color-on-primary-fixed-variant)] transition-colors">
                    <span className="material-symbols-outlined text-[20px]">visibility</span>
                  </button>
                </td>
              </tr>
              <tr className="hover:bg-[var(--color-surface-container-low)] transition-colors">
                <td className="px-6 py-4 text-sm text-[var(--color-on-surface)]">escaneo_772.png</td>
                <td className="px-6 py-4 text-sm text-[var(--color-on-surface-variant)]">hace 14 mins</td>
                <td className="px-6 py-4">
                  <span className="px-2 py-0.5 rounded bg-amber-50 text-amber-700 text-xs font-medium border border-amber-100">
                    Sospechoso
                  </span>
                </td>
                <td className="px-6 py-4">
                  <button className="text-[var(--color-primary)] hover:text-[var(--color-on-primary-fixed-variant)] transition-colors">
                    <span className="material-symbols-outlined text-[20px]">edit</span>
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
