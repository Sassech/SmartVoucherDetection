/**
 * Historial page tests — R-39, R-40, R-41, S-27, S-28, S-29, S-30, S-31, S-32, 4.D.13
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";

// Mock next/navigation
const mockPush = vi.fn();
const mockSearchParams = new URLSearchParams();

vi.mock("next/navigation", () => ({
  useRouter: vi.fn(() => ({ push: mockPush })),
  useSearchParams: vi.fn(() => mockSearchParams),
}));

// Mock fetchApi
vi.mock("@/lib/api", () => ({
  fetchApi: vi.fn(),
  ApiError: class ApiError extends Error {
    constructor(public status: number, message: string) {
      super(message);
    }
  },
}));

import { fetchApi } from "@/lib/api";
import HistorialPage from "../page";

const mockListData = {
  items: [
    {
      id_comprobante: "abc-123",
      folio: "folio00112345678",
      monto: 1000,
      banco: "BANAMEX",
      referencia: "REF-001",
      fecha_deposito: "2024-01-15",
      estado: "procesado",
      imagen_path: null,
      texto_extraido: null,
    },
  ],
  total: 1,
  page: 1,
  has_more: false,
};

describe("Historial page", () => {
  beforeEach(() => {
    vi.mocked(fetchApi).mockResolvedValue(mockListData);
    mockPush.mockClear();
  });

  it("renders FilterBar and HistorialTable", async () => {
    render(<HistorialPage />);

    // Wait for data to load
    expect(await screen.findByText("folio001")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /pendiente/i })).toBeInTheDocument();
  });

  it("changing filter calls router.push with updated params", async () => {
    const user = userEvent.setup();
    render(<HistorialPage />);

    // Wait for initial render
    await screen.findByText("folio001");

    await user.click(screen.getByRole("button", { name: /pendiente/i }));

    expect(mockPush).toHaveBeenCalledWith(expect.stringContaining("status=pendiente"));
  });

  it("page resets to 1 on filter change", async () => {
    const user = userEvent.setup();
    render(<HistorialPage />);
    await screen.findByText("folio001");

    await user.click(screen.getByRole("button", { name: /duplicado/i }));

    const pushArg = mockPush.mock.calls[0][0] as string;
    expect(pushArg).toContain("page=1");
  });
});
