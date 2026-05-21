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
  folio: "folio001xxxxxxxx",
  monto: 1000,
  banco: "BANAMEX",
  referencia: "REF-001",
  fecha_deposito: "2024-01-15",
  estado: "en_revision",
  imagen_path: null,
  texto_extraido: null,
};

const itemWithCandidates: WebComprobanteItem = {
  ...baseItem,
  texto_extraido: JSON.stringify([
    { id_comprobante_original: "orig-001", score_similitud: 0.95 },
    { id_comprobante_original: "orig-002", score_similitud: 0.78 },
  ]),
};

describe("DuplicatePanel", () => {
  beforeEach(() => {
    vi.mocked(fetchApi).mockResolvedValue({});
  });

  it("renders Aceptar and Rechazar buttons", () => {
    render(<DuplicatePanel item={baseItem} />);
    expect(screen.getByRole("button", { name: /aceptar/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /rechazar/i })).toBeInTheDocument();
  });

  it('click Aceptar calls POST with decision:"valido"', async () => {
    const user = userEvent.setup();
    render(<DuplicatePanel item={baseItem} />);

    await user.click(screen.getByRole("button", { name: /aceptar/i }));

    await waitFor(() => {
      expect(fetchApi).toHaveBeenCalledWith(
        `/api/web/comprobantes/comp-001/decision`,
        expect.objectContaining({
          method: "POST",
          body: expect.stringContaining('"valido"'),
        }),
      );
    });
  });

  it('click Rechazar calls POST with decision:"duplicado"', async () => {
    const user = userEvent.setup();
    render(<DuplicatePanel item={baseItem} />);

    await user.click(screen.getByRole("button", { name: /rechazar/i }));

    await waitFor(() => {
      expect(fetchApi).toHaveBeenCalledWith(
        `/api/web/comprobantes/comp-001/decision`,
        expect.objectContaining({
          method: "POST",
          body: expect.stringContaining('"duplicado"'),
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
    expect(screen.getByText("en_revision")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /aceptar/i }));

    // Should immediately show the optimistic estado
    expect(screen.getByText("procesado")).toBeInTheDocument();
  });

  it("reverts state on API failure (S-36)", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchApi).mockRejectedValue(new Error("Server error"));

    render(<DuplicatePanel item={baseItem} />);
    await user.click(screen.getByRole("button", { name: /aceptar/i }));

    // After failure, the estado should revert
    await waitFor(() => {
      expect(screen.getByText("en_revision")).toBeInTheDocument();
    });
  });

  it("shows error message on failure", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchApi).mockRejectedValue(new Error("Server error"));

    render(<DuplicatePanel item={baseItem} />);
    await user.click(screen.getByRole("button", { name: /aceptar/i }));

    await waitFor(() => {
      expect(screen.getByText(/error/i)).toBeInTheDocument();
    });
  });

  it("renders candidates table when texto_extraido has candidates (S-34)", () => {
    render(<DuplicatePanel item={itemWithCandidates} />);
    expect(screen.getByText("orig-001")).toBeInTheDocument();
  });

  it("renders 2 candidate rows in S-34 scenario", () => {
    render(<DuplicatePanel item={itemWithCandidates} />);
    expect(screen.getByText("orig-001")).toBeInTheDocument();
    expect(screen.getByText("orig-002")).toBeInTheDocument();
  });

  it("shows score_similitud as percentage", () => {
    render(<DuplicatePanel item={itemWithCandidates} />);
    expect(screen.getByText("95%")).toBeInTheDocument();
    expect(screen.getByText("78%")).toBeInTheDocument();
  });

  it("renders empty candidates gracefully when texto_extraido is null", () => {
    render(<DuplicatePanel item={baseItem} />);
    // No crash, no candidates table shown — buttons still present
    expect(screen.getByRole("button", { name: /aceptar/i })).toBeInTheDocument();
    expect(screen.queryByText(/similitud/i)).not.toBeInTheDocument();
  });
});
