"use client";

/**
 * FilterBar — status pill + date range filter for historial — R-40, R-41, S-27, S-28, S-32, 4.D.4
 */

import { cn } from "@/lib/utils";
import type { FilterState } from "@/lib/types";

const STATUS_OPTIONS = ["pendiente", "procesado", "duplicado", "error"] as const;

interface FilterBarProps {
  value: FilterState;
  onChange: (v: FilterState) => void;
}

export function FilterBar({ value, onChange }: FilterBarProps) {
  function toggleStatus(status: string) {
    const isSelected = value.status.includes(status);
    const nextStatus = isSelected
      ? value.status.filter((s) => s !== status)
      : [...value.status, status];
    onChange({ ...value, status: nextStatus });
  }

  function handleDateChange(field: "date_from" | "date_to", raw: string) {
    onChange({ ...value, [field]: raw });
  }

  return (
    <div className="flex flex-wrap items-center gap-3 rounded-[var(--radius-lg)] border border-[var(--color-outline-variant)] bg-[var(--color-surface-container-low)] px-4 py-3">
      {/* Status pills */}
      <div className="flex flex-wrap gap-2" role="group" aria-label="Filtrar por estado">
        {STATUS_OPTIONS.map((status) => {
          const isSelected = value.status.includes(status);
          return (
            <button
              key={status}
              type="button"
              onClick={() => toggleStatus(status)}
              className={cn(
                "rounded-full px-3 py-1 text-xs font-medium transition-colors",
                isSelected
                  ? "bg-[var(--color-primary)] text-white"
                  : "bg-[var(--color-surface-container)] text-[var(--color-on-surface-variant)] hover:bg-[var(--color-surface-container-high)]",
              )}
              aria-pressed={isSelected}
            >
              {status}
            </button>
          );
        })}
      </div>

      {/* Date range */}
      <div className="flex flex-wrap items-center gap-2 ml-auto">
        <div className="flex items-center gap-1.5">
          <label
            htmlFor="filter-date-from"
            className="text-xs font-medium text-[var(--color-on-surface-variant)] whitespace-nowrap"
          >
            Fecha desde
          </label>
          <input
            id="filter-date-from"
            type="date"
            value={value.date_from}
            onChange={(e) => handleDateChange("date_from", e.target.value)}
            className="rounded-[var(--radius-sm)] border border-[var(--color-outline-variant)] bg-[var(--color-surface)] px-2 py-1 text-xs text-[var(--color-on-surface)] focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]"
          />
        </div>
        <div className="flex items-center gap-1.5">
          <label
            htmlFor="filter-date-to"
            className="text-xs font-medium text-[var(--color-on-surface-variant)] whitespace-nowrap"
          >
            Fecha hasta
          </label>
          <input
            id="filter-date-to"
            type="date"
            value={value.date_to}
            onChange={(e) => handleDateChange("date_to", e.target.value)}
            className="rounded-[var(--radius-sm)] border border-[var(--color-outline-variant)] bg-[var(--color-surface)] px-2 py-1 text-xs text-[var(--color-on-surface)] focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]"
          />
        </div>
      </div>
    </div>
  );
}
