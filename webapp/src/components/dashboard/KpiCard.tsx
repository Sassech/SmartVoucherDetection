/**
 * KpiCard — RSC stat card for dashboard — R-37, S-23, S-24, 4.D.1
 */

interface KpiCardProps {
  label: string;
  value: number;
  icon: string;
  iconBgClass?: string;
  iconColorClass?: string;
  valueColorClass?: string;
  badge?: string;
  badgeColorClass?: string;
}

export function KpiCard({
  label,
  value,
  icon,
  iconBgClass = "bg-[var(--color-surface-container)]",
  iconColorClass = "text-[var(--color-primary)]",
  valueColorClass = "text-[var(--color-on-surface)]",
  badge,
  badgeColorClass = "text-[var(--color-secondary)]",
}: KpiCardProps) {
  return (
    <div className="flex flex-col justify-between gap-4 rounded-xl border border-[var(--color-outline-variant)] bg-white p-4">
      <div className="flex items-start justify-between">
        <div className={`w-10 h-10 rounded-lg ${iconBgClass} flex items-center justify-center ${iconColorClass}`}>
          <span className="material-symbols-outlined text-[20px]">{icon}</span>
        </div>
        {badge && (
          <span className={`text-xs font-medium ${badgeColorClass}`}>
            {badge}
          </span>
        )}
      </div>
      <div>
        <p className="text-[11px] font-bold uppercase tracking-wider text-[var(--color-secondary)]">
          {label}
        </p>
        <p className={`text-2xl font-semibold tracking-[-0.02em] leading-8 mt-1 ${valueColorClass}`}>
          {value.toLocaleString()}
        </p>
      </div>
    </div>
  );
}
