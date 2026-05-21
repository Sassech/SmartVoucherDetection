"use client";

/**
 * Historial list page — client component with URL-driven filters.
 * R-39, R-40, R-41, S-27, S-28, S-29, S-30, S-31, S-32, 4.D.6
 */

import { useEffect, useState, useCallback } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { fetchApi } from "@/lib/api";
import { FilterBar } from "@/components/historial/FilterBar";
import { HistorialTable } from "@/components/historial/HistorialTable";
import type { WebListResponse, FilterState } from "@/lib/types";

function buildUrl(filter: FilterState, page: number): string {
  const params = new URLSearchParams();
  if (filter.status.length > 0) {
    params.set("status", filter.status.join(","));
  }
  if (filter.date_from) {
    params.set("date_from", filter.date_from);
  }
  if (filter.date_to) {
    params.set("date_to", filter.date_to);
  }
  params.set("page", String(page));
  return `/historial?${params.toString()}`;
}

function buildApiUrl(filter: FilterState, page: number): string {
  const params = new URLSearchParams();
  params.set("limit", "20");
  params.set("page", String(page));
  if (filter.status.length > 0) {
    params.set("status", filter.status.join(","));
  }
  if (filter.date_from) {
    params.set("date_from", filter.date_from);
  }
  if (filter.date_to) {
    params.set("date_to", filter.date_to);
  }
  return `/api/web/comprobantes/?${params.toString()}`;
}

function searchParamsToFilter(sp: URLSearchParams): FilterState {
  const statusRaw = sp.get("status") ?? "";
  return {
    status: statusRaw ? statusRaw.split(",") : [],
    date_from: sp.get("date_from") ?? "",
    date_to: sp.get("date_to") ?? "",
  };
}

export default function HistorialPage() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const [filter, setFilter] = useState<FilterState>(() =>
    searchParamsToFilter(searchParams),
  );
  const [page, setPage] = useState<number>(() => {
    const p = searchParams.get("page");
    return p ? parseInt(p, 10) : 1;
  });
  const [data, setData] = useState<WebListResponse | null>(null);
  const [loading, setLoading] = useState(true);

  const loadData = useCallback(
    async (currentFilter: FilterState, currentPage: number) => {
      setLoading(true);
      try {
        const result = await fetchApi<WebListResponse>(buildApiUrl(currentFilter, currentPage));
        setData(result);
      } catch {
        setData(null);
      } finally {
        setLoading(false);
      }
    },
    [],
  );

  useEffect(() => {
    void loadData(filter, page);
  }, [filter, page, loadData]);

  function handleFilterChange(newFilter: FilterState) {
    const newPage = 1;
    setFilter(newFilter);
    setPage(newPage);
    router.push(buildUrl(newFilter, newPage));
  }

  function handleNextPage() {
    const newPage = page + 1;
    setPage(newPage);
    router.push(buildUrl(filter, newPage));
  }

  function handleRowClick(id: string) {
    router.push(`/historial/${id}`);
  }

  return (
    <div className="flex flex-col gap-5">
      <h1 className="text-2xl font-semibold tracking-tight text-[var(--color-on-surface)]">
        Historial
      </h1>

      <FilterBar value={filter} onChange={handleFilterChange} />

      {loading ? (
        <div className="rounded-[var(--radius-lg)] border border-[var(--color-outline-variant)] bg-[var(--color-surface)] p-10 text-center">
          <p className="text-sm text-[var(--color-on-surface-variant)]">Cargando…</p>
        </div>
      ) : (
        <HistorialTable
          items={data?.items ?? []}
          hasMore={data?.has_more ?? false}
          onNextPage={handleNextPage}
          onRowClick={handleRowClick}
        />
      )}
    </div>
  );
}
