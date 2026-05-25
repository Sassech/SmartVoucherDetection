/**
 * HistorialTable tests — R-39, R-42, S-29, S-30, S-31, 4.D.13
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { HistorialTable } from "../HistorialTable";
import type { WebComprobanteItem } from "@/lib/types";

const makeItem = (overrides: Partial<WebComprobanteItem>): WebComprobanteItem => ({
  id_comprobante: "id-001",
  monto: 500,
  banco: "BANAMEX",
  referencia: "REF-001",
  fecha_deposito: "2024-01-15",
  estado_actual: "recibido",
  imagen_path: "",
  fecha_registro: "2024-01-15T10:00:00Z",
  texto_extraido: null,
  ...overrides,
});

describe("HistorialTable", () => {
  it('renders "Sin resultados" when items is empty (S-30)', () => {
    render(
      <HistorialTable
        items={[]}
        hasMore={false}
        onNextPage={vi.fn()}
        onRowClick={vi.fn()}
      />,
    );
    expect(screen.getByText("Sin resultados")).toBeInTheDocument();
  });

  it("renders rows when items provided", () => {
    const items = [
      makeItem({ id_comprobante: "id-001", referencia: "aaaaaaaa12345678" }),
      makeItem({ id_comprobante: "id-002", referencia: "bbbbbbbb87654321" }),
    ];
    render(
      <HistorialTable
        items={items}
        hasMore={false}
        onNextPage={vi.fn()}
        onRowClick={vi.fn()}
      />,
    );
    expect(screen.getByText("aaaaaaaa12345")).toBeInTheDocument();
    expect(screen.getByText("bbbbbbbb87654")).toBeInTheDocument();
  });

  it("row click calls onRowClick with correct id (S-31)", async () => {
    const user = userEvent.setup();
    const onRowClick = vi.fn();
    const items = [makeItem({ id_comprobante: "abc-123", referencia: "REF-folio001" })];
    render(
      <HistorialTable
        items={items}
        hasMore={false}
        onNextPage={vi.fn()}
        onRowClick={onRowClick}
      />,
    );

    // Click the "Ver" link/button for the row
    await user.click(screen.getByRole("button", { name: /ver/i }));
    expect(onRowClick).toHaveBeenCalledWith("abc-123");
  });

  it("shows next-page button when hasMore=true (S-29)", () => {
    const items = [makeItem({})];
    render(
      <HistorialTable
        items={items}
        hasMore={true}
        onNextPage={vi.fn()}
        onRowClick={vi.fn()}
      />,
    );
    expect(screen.getByRole("button", { name: /siguiente/i })).toBeInTheDocument();
  });

  it("hides next-page button when hasMore=false", () => {
    const items = [makeItem({})];
    render(
      <HistorialTable
        items={items}
        hasMore={false}
        onNextPage={vi.fn()}
        onRowClick={vi.fn()}
      />,
    );
    expect(screen.queryByRole("button", { name: /siguiente/i })).not.toBeInTheDocument();
  });

  it("badge renders correct variant for duplicado status", () => {
    const items = [
      makeItem({ id_comprobante: "a", estado_actual: "duplicado" }),
    ];
    render(
      <HistorialTable
        items={items}
        hasMore={false}
        onNextPage={vi.fn()}
        onRowClick={vi.fn()}
      />,
    );
    expect(screen.getByText("Duplicado")).toBeInTheDocument();
  });

  it("referencia truncated to 14 chars", () => {
    const items = [makeItem({ referencia: "abcdef1234567890" })];
    render(
      <HistorialTable
        items={items}
        hasMore={false}
        onNextPage={vi.fn()}
        onRowClick={vi.fn()}
      />,
    );
    expect(screen.getByText("abcdef12345678")).toBeInTheDocument();
    expect(screen.queryByText("abcdef1234567890")).not.toBeInTheDocument();
  });

  it("onNextPage called when next-page button clicked", async () => {
    const user = userEvent.setup();
    const onNextPage = vi.fn();
    const items = [makeItem({})];
    render(
      <HistorialTable
        items={items}
        hasMore={true}
        onNextPage={onNextPage}
        onRowClick={vi.fn()}
      />,
    );

    await user.click(screen.getByRole("button", { name: /siguiente/i }));
    expect(onNextPage).toHaveBeenCalledOnce();
  });
});
