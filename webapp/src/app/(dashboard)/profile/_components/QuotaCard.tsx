/**
 * QuotaCard — R-81 "Plan & Usage" section.
 *
 * Displays the user's plan name, a progress bar (used/limit),
 * and the quota reset date.
 *
 * Props:
 *   plan      — "basic" | "pro" | "enterprise"
 *   used      — uploads consumed this month
 *   limit     — plan cap (-1 = unlimited)
 *   resetDate — ISO date string for quota reset (first day of next month)
 */

interface QuotaCardProps {
  plan: string;
  used: number;
  limit: number;
  resetDate: string;
}

const PLAN_LABELS: Record<string, string> = {
  basic: "Basic",
  pro: "Pro",
  enterprise: "Enterprise",
};

const PLAN_BADGE_STYLES: Record<string, React.CSSProperties> = {
  basic: { background: "#eff6ff", color: "#1d4ed8", border: "1px solid #bfdbfe" },
  pro: { background: "#faf5ff", color: "#7c3aed", border: "1px solid #ddd6fe" },
  enterprise: { background: "#f0fdf4", color: "#166534", border: "1px solid #bbf7d0" },
};

function formatResetDate(isoDate: string): string {
  try {
    return new Date(isoDate).toLocaleDateString("es-MX", {
      day: "numeric",
      month: "long",
      year: "numeric",
    });
  } catch {
    return isoDate;
  }
}

export function QuotaCard({ plan, used, limit, resetDate }: QuotaCardProps) {
  const unlimited = limit === -1;
  const pct = unlimited ? 0 : Math.min(100, Math.round((used / limit) * 100));
  const labelKey = plan.toLowerCase();
  const planLabel = PLAN_LABELS[labelKey] ?? plan;
  const badgeStyle = PLAN_BADGE_STYLES[labelKey] ?? PLAN_BADGE_STYLES.basic;

  // Color the bar red when near limit (>= 90%) — only for capped plans
  const barColor = !unlimited && pct >= 90
    ? "var(--color-error, #ba1a1a)"
    : "var(--color-primary, #003d9b)";

  return (
    <div
      className="bg-white border border-[var(--color-outline-variant)] rounded-xl overflow-hidden"
      aria-label="Plan and usage"
    >
      {/* Card header */}
      <div className="px-5 py-4 border-b border-[var(--color-outline-variant)] flex items-center justify-between">
        <h2 className="text-sm font-semibold text-[var(--color-on-surface)]">
          Plan &amp; Usage
        </h2>
        {/* Plan badge */}
        <span
          style={{
            ...badgeStyle,
            padding: "2px 10px",
            borderRadius: 99,
            fontSize: "0.72rem",
            fontWeight: 700,
            letterSpacing: "0.04em",
          }}
        >
          {planLabel}
        </span>
      </div>

      {/* Card body */}
      <div className="px-5 py-5 space-y-4">
        {/* Used / limit counts */}
        <div className="flex items-baseline justify-between">
          <span className="text-sm text-[var(--color-on-surface-variant)]">
            Uploads this month
          </span>
          <span className="text-base font-semibold text-[var(--color-on-surface)]">
            {unlimited ? (
              <>
                {used}
                <span className="text-sm font-normal text-[var(--color-on-surface-variant)]"> / Unlimited</span>
              </>
            ) : (
              <>
                {used}
                <span className="text-sm font-normal text-[var(--color-on-surface-variant)]"> / {limit}</span>
              </>
            )}
          </span>
        </div>

        {/* Progress bar — hidden for unlimited plans */}
        {!unlimited && (
          <div role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label={`${pct}% of monthly quota used`}>
            <div className="h-2 w-full bg-[var(--color-surface-container)] rounded-full overflow-hidden">
              <div
                className="h-full rounded-full transition-all duration-500"
                style={{ width: `${pct}%`, backgroundColor: barColor }}
              />
            </div>
            <p className="mt-1 text-[11px] text-[var(--color-on-surface-variant)]">
              {pct}% used
            </p>
          </div>
        )}

        {/* Reset date */}
        <p className="text-xs text-[var(--color-on-surface-variant)]">
          Quota resets on{" "}
          <span className="font-medium text-[var(--color-on-surface)]">
            {formatResetDate(resetDate)}
          </span>
        </p>

        {/*
         * TODO (deuda técnica): el conteo mensual requiere un endpoint
         * dedicado en el backend que devuelva el uso del mes en curso.
         * Actualmente se muestra el plan y la fecha de reset, pero `used`
         * proviene de una estimación (historial total, no mensual).
         * Ver: sdd/fase-7-multiuser — open item quota usage endpoint.
         */}
      </div>
    </div>
  );
}
