"use client";

/**
 * FilterBar — status pill + date range filter for historial — R-40, R-41, S-27, S-28, S-32, 4.D.4
 */

import { cn } from "@/lib/utils";
import type { FilterState } from "@/lib/types";

const STATUS_OPTIONS = [
  { value: "todos", label: "Todos los Registros" },
  { value: "procesado", label: "Válido" },
  { value: "duplicado", label: "Duplicado" },
  { value: "sospechoso", label: "Sospechoso" },
] as const;

interface FilterBarProps {
  value: FilterState;
  onChange: (v: FilterState) => void;
}

export function FilterBar({ value, onChange }: FilterBarProps) {
  const isAll = value.status.length === 0;

  function handleStatusClick(status: string) {
    if (status === "todos") {
      onChange({ ...value, status: [] });
      return;
    }
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
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
      {/* Status filter */}
      <div className="md:col-span-2 bg-white border border-slate-200 rounded-xl p-4 shadow-sm">
        <label className="block text-[10px] font-bold text-[var(--color-secondary)] uppercase tracking-wider mb-3">
          Filtrar por Estado
        </label>
        <div className="flex flex-wrap gap-2" role="group" aria-label="Filtrar por estado">
          {STATUS_OPTIONS.map(({ value: optVal, label }) => {
            const isSelected =
              optVal === "todos"
                ? isAll
                : value.status.includes(optVal);

            return (
              <button
                key={optVal}
                type="button"
                onClick={() => handleStatusClick(optVal)}
                className={cn(
                  "px-4 py-1.5 rounded-full text-xs font-semibold transition-colors",
                  isSelected
                    ? "bg-[var(--color-primary-container)] text-white"
                    : "bg-[var(--color-surface-container)] text-[var(--color-on-surface-variant)] hover:bg-[var(--color-surface-container-high)]",
                )}
                aria-pressed={isSelected}
              >
                {label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Date range */}
      <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm">
        <label className="block text-[10px] font-bold text-[var(--color-secondary)] uppercase tracking-wider mb-3">
          Rango de Fechas
        </label>
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <span className="material-symbols-outlined text-[var(--color-outline)] text-[18px]">
              calendar_today
            </span>
            <input
              id="filter-date-from"
              type="date"
              value={value.date_from}
              onChange={(e) => handleDateChange("date_from", e.target.value)}
              className="flex-1 rounded-lg border border-[var(--color-outline-variant)] bg-[var(--color-surface)] px-2 py-1.5 text-xs text-[var(--color-on-surface)] focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]/20 focus:border-[var(--color-primary)]"
              aria-label="Fecha desde"
            />
          </div>
          <div className="flex items-center gap-2">
            <span className="material-symbols-outlined text-[var(--color-outline)] text-[18px]">
              event
            </span>
            <input
              id="filter-date-to"
              type="date"
              value={value.date_to}
              onChange={(e) => handleDateChange("date_to", e.target.value)}
              className="flex-1 rounded-lg border border-[var(--color-outline-variant)] bg-[var(--color-surface)] px-2 py-1.5 text-xs text-[var(--color-on-surface)] focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]/20 focus:border-[var(--color-primary)]"
              aria-label="Fecha hasta"
            />
          </div>
        </div>
      </div>
    </div>
  );
}
