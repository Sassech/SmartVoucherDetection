/**
 * DuplicatePanel tests — R-44, R-45, S-34, S-35, S-36, 4.D.14
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";

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
import { DuplicatePanel } from "../DuplicatePanel";
import type { WebComprobanteItem } from "@/lib/types";

const baseItem: WebComprobanteItem = {
  id_comprobante: "comp-001",
  monto: 1000,
  banco: "BANAMEX",
  referencia: "REF-001",
  fecha_deposito: "2024-01-15",
  estado_actual: "en_revision",
  imagen_path: "",
  fecha_registro: "2024-01-15T10:00:00Z",
  texto_extraido: null,
};

describe("DuplicatePanel", () => {
  beforeEach(() => {
    vi.mocked(fetchApi).mockResolvedValue({});
  });

  it("renders Aceptar and Rechazar buttons", () => {
    render(<DuplicatePanel item={baseItem} />);
    expect(screen.getByRole("button", { name: /válido/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /duplicado/i })).toBeInTheDocument();
  });

  it('click Aceptar calls POST with accion:"aceptar"', async () => {
    const user = userEvent.setup();
    render(<DuplicatePanel item={baseItem} />);

    await user.click(screen.getByRole("button", { name: /válido/i }));

    await waitFor(() => {
      expect(fetchApi).toHaveBeenCalledWith(
        `/api/web/comprobantes/comp-001/decision`,
        expect.objectContaining({
          method: "POST",
          body: expect.stringContaining('"aceptar"'),
        }),
      );
    });
  });

  it('click Rechazar calls POST with accion:"rechazar"', async () => {
    const user = userEvent.setup();
    render(<DuplicatePanel item={baseItem} />);

    await user.click(screen.getByRole("button", { name: /duplicado/i }));

    await waitFor(() => {
      expect(fetchApi).toHaveBeenCalledWith(
        `/api/web/comprobantes/comp-001/decision`,
        expect.objectContaining({
          method: "POST",
          body: expect.stringContaining('"rechazar"'),
        }),
      );
    });
  });

  it("optimistic update: badge changes immediately on Aceptar click (S-35)", async () => {
    const user = userEvent.setup();
    // Make fetch slow so we can observe the optimistic state
    vi.mocked(fetchApi).mockImplementation(
      () => new Promise((resolve) => setTimeout(resolve, 100)),
    );

    render(<DuplicatePanel item={baseItem} />);
    expect(screen.getByText("En Revisión")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /válido/i }));

    // Should immediately show the optimistic estado
    expect(screen.getByText("Válido")).toBeInTheDocument();
  });

  it("reverts state on API failure (S-36)", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchApi).mockRejectedValue(new Error("Server error"));

    render(<DuplicatePanel item={baseItem} />);
    await user.click(screen.getByRole("button", { name: /válido/i }));

    // After failure, the estado should revert
    await waitFor(() => {
      expect(screen.getByText("En Revisión")).toBeInTheDocument();
    });
  });

  it("shows error message on failure", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchApi).mockRejectedValue(new Error("Server error"));

    render(<DuplicatePanel item={baseItem} />);
    await user.click(screen.getByRole("button", { name: /válido/i }));

    await waitFor(() => {
      expect(screen.getByText(/error/i)).toBeInTheDocument();
    });
  });

  it("always shows no-candidates message (texto_extraido is plain OCR text, not JSON)", () => {
    render(<DuplicatePanel item={baseItem} />);
    expect(screen.getByText(/no hay candidatos duplicados disponibles/i)).toBeInTheDocument();
  });

  it("no-candidates message shown even when texto_extraido contains text", () => {
    const itemWithText: WebComprobanteItem = {
      ...baseItem,
      texto_extraido: "BANCO BANAMEX REF 12345 MONTO $1000.00",
    };
    render(<DuplicatePanel item={itemWithText} />);
    expect(screen.getByText(/no hay candidatos duplicados disponibles/i)).toBeInTheDocument();
  });

  it("renders empty candidates gracefully when texto_extraido is null", () => {
    render(<DuplicatePanel item={baseItem} />);
    // No crash, buttons still present
    expect(screen.getByRole("button", { name: /válido/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /duplicado/i })).toBeInTheDocument();
  });
});
