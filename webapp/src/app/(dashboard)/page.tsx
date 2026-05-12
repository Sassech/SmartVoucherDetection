/**
 * Dashboard root page — placeholder for PR-D.
 * PR-D will replace this with KpiCard + RecentActivity components.
 */

export default function DashboardPage() {
  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-semibold tracking-tight text-[var(--color-on-surface)]">
        Dashboard
      </h1>
      <p className="text-sm text-[var(--color-on-surface-variant)]">
        Cargando datos del panel…
      </p>
    </div>
  );
}
