/**
 * QuotaCard — R-81 "Plan & Usage" section.
 *
 * Displays the user's plan name, a progress bar (used/limit),
 * and the quota reset date.
 *
 * Props:
 *   plan      — "basic" | "pro" | "enterprise"
 *   used      — uploads consumed this month (null = loading)
 *   limit     — plan cap (-1 = unlimited)
 *   resetDate — ISO date string for quota reset (null if unlimited)
 */

import type { ReactNode } from "react";

interface QuotaCardProps {
  plan: string;
  used: number | null;
  limit: number;
  resetDate: string | null;
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

export function QuotaCard({ plan, used, limit, resetDate }: Readonly<QuotaCardProps>) {
  const unlimited = limit === -1;
  const loading = used === null;
  const usedVal = used ?? 0;
  const pct = unlimited || loading ? 0 : Math.min(100, Math.round((usedVal / limit) * 100));
  const labelKey = plan.toLowerCase();
  const planLabel = PLAN_LABELS[labelKey] ?? plan;
  const badgeStyle = PLAN_BADGE_STYLES[labelKey] ?? PLAN_BADGE_STYLES.basic;

  // Color the bar red when near limit (>= 90%) — only for capped plans
  let barColor: string;
  if (!unlimited && pct >= 90) {
    barColor = "var(--color-error, #ba1a1a)";
  } else {
    barColor = "var(--color-primary, #003d9b)";
  }

  let usageDisplay: ReactNode;
  if (loading) {
    usageDisplay = (
      <span className="text-sm font-normal text-[var(--color-on-surface-variant)]">Loading…</span>
    );
  } else if (unlimited) {
    usageDisplay = (
      <>
        {usedVal}
        <span className="text-sm font-normal text-[var(--color-on-surface-variant)]"> / Unlimited</span>
      </>
    );
  } else {
    usageDisplay = (
      <>
        {usedVal}
        <span className="text-sm font-normal text-[var(--color-on-surface-variant)]"> / {limit}</span>
      </>
    );
  }

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
            {usageDisplay}
          </span>
        </div>

        {/* Progress bar — hidden for unlimited plans and while loading */}
        {!unlimited && !loading && (
          <div>
            <progress
              value={pct}
              max={100}
              aria-label={`${pct}% of monthly quota used`}
              className="h-2 w-full rounded-full overflow-hidden"
              style={{ accentColor: barColor }}
            />
            <p className="mt-1 text-[11px] text-[var(--color-on-surface-variant)]">
              {pct}% used
            </p>
          </div>
        )}

        {/* Reset date */}
        {resetDate && (
          <p className="text-xs text-[var(--color-on-surface-variant)]">
            Quota resets on{" "}
            <span className="font-medium text-[var(--color-on-surface)]">
              {formatResetDate(resetDate)}
            </span>
          </p>
        )}
        {unlimited && (
          <p className="text-xs text-[var(--color-on-surface-variant)]">
            No monthly limit on this plan.
          </p>
        )}
      </div>
    </div>
  );
}
