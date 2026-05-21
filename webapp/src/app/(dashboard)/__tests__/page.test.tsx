/**
 * Dashboard page tests — R-37, R-38, S-23, S-24, S-25, S-26, 4.D.12
 *
 * The dashboard page is a RSC (async server component).
 * We test it by calling it as an async function and rendering the result.
 */

import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

// Mock next/headers (only available in RSC server runtime)
vi.mock("next/headers", () => ({
  cookies: vi.fn().mockResolvedValue({
    get: vi.fn().mockReturnValue({ value: "mock-token" }),
  }),
}));

const mockStatsData = {
  total_comprobantes: 10,
  pendientes: 2,
  procesados_hoy: 5,
  duplicados_detectados: 1,
};

const mockListData = {
  items: [],
  total: 0,
  page: 1,
  has_more: false,
};

// We import the page module once — the fetch mock controls what happens
import DashboardPage from "../page";

describe("Dashboard page", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        if (String(url).includes("/stats/")) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve(mockStatsData),
          });
        }
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(mockListData),
        });
      }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders 4 KpiCards with fetched stats", async () => {
    const jsx = await DashboardPage();
    render(jsx);

    expect(screen.getByText("Total Comprobantes")).toBeInTheDocument();
    expect(screen.getByText("10")).toBeInTheDocument();
    expect(screen.getByText("Pendientes")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByText("Procesados Hoy")).toBeInTheDocument();
    expect(screen.getByText("5")).toBeInTheDocument();
    expect(screen.getByText("Duplicados Detectados")).toBeInTheDocument();
    expect(screen.getByText("1")).toBeInTheDocument();
  });

  it("renders RecentActivity section", async () => {
    const jsx = await DashboardPage();
    render(jsx);

    expect(screen.getByText("Actividad Reciente")).toBeInTheDocument();
  });

  it("shows friendly error message on fetch failure (S-26)", async () => {
    // Override fetch to simulate failure
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.reject(new Error("Network error"))),
    );

    const jsx = await DashboardPage();
    render(jsx);

    expect(
      screen.getByText("No se pudieron cargar los datos del dashboard"),
    ).toBeInTheDocument();
  });
});
