/**
 * KpiCard — RSC stat card for dashboard — R-37, S-23, S-24, 4.D.1
 */

interface KpiCardProps {
  label: string;
  value: number;
  icon?: React.ReactNode;
}

export function KpiCard({ label, value, icon }: KpiCardProps) {
  return (
    <div className="flex flex-col gap-2 rounded-[var(--radius-lg)] bg-[var(--color-surface-container-low)] p-5 shadow-sm">
      {icon && (
        <div className="text-[var(--color-primary)] text-2xl" aria-hidden="true">
          {icon}
        </div>
      )}
      <span className="text-sm font-medium text-[var(--color-on-surface-variant)]">
        {label}
      </span>
      <span className="text-3xl font-bold tracking-tight text-[var(--color-on-surface)]">
        {value}
      </span>
    </div>
  );
}
