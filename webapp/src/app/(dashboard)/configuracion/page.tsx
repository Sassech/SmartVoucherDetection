/**
 * Configuración page — server component placeholder
 * Future: system settings and user preferences
 */

export default function ConfiguracionPage() {
  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-[var(--color-on-surface)]">
          Configuración
        </h1>
        <p className="text-sm text-[var(--color-on-surface-variant)] mt-1">
          Ajustes del sistema y preferencias.
        </p>
      </div>

      <div className="rounded-[var(--radius-lg)] border border-[var(--color-outline-variant)] bg-[var(--color-surface)] p-10">
        <div className="flex flex-col items-center gap-4 text-center">
          <div className="w-16 h-16 rounded-full bg-[var(--color-surface-container-high)] flex items-center justify-center">
            <span className="material-symbols-outlined text-4xl text-[var(--color-on-surface-variant)]">
              construction
            </span>
          </div>
          <div>
            <h3 className="text-base font-semibold text-[var(--color-on-surface)]">
              En construcción
            </h3>
            <p className="text-sm text-[var(--color-on-surface-variant)] mt-1">
              Esta sección estará disponible próximamente.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
