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
  folio: "abcdef1234567890",
  monto: 500,
  banco: "BANAMEX",
  referencia: "REF-001",
  fecha_deposito: "2024-01-15",
  estado: "pendiente",
  imagen_path: null,
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
      makeItem({ id_comprobante: "id-001", folio: "aaaaaaaa12345678" }),
      makeItem({ id_comprobante: "id-002", folio: "bbbbbbbb87654321" }),
    ];
    render(
      <HistorialTable
        items={items}
        hasMore={false}
        onNextPage={vi.fn()}
        onRowClick={vi.fn()}
      />,
    );
    expect(screen.getByText("aaaaaaaa")).toBeInTheDocument();
    expect(screen.getByText("bbbbbbbb")).toBeInTheDocument();
  });

  it("row click calls onRowClick with correct id (S-31)", async () => {
    const user = userEvent.setup();
    const onRowClick = vi.fn();
    const items = [makeItem({ id_comprobante: "abc-123", folio: "folio001xxxxxxxx" })];
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

  it("badge renders correct variant for each status", () => {
    const items = [
      makeItem({ id_comprobante: "a", folio: "folioa00xxxxxxxx", estado: "duplicado" }),
    ];
    render(
      <HistorialTable
        items={items}
        hasMore={false}
        onNextPage={vi.fn()}
        onRowClick={vi.fn()}
      />,
    );
    expect(screen.getByText("duplicado")).toBeInTheDocument();
  });

  it("folio truncated to 8 chars", () => {
    const items = [makeItem({ folio: "abcdef1234567890" })];
    render(
      <HistorialTable
        items={items}
        hasMore={false}
        onNextPage={vi.fn()}
        onRowClick={vi.fn()}
      />,
    );
    expect(screen.getByText("abcdef12")).toBeInTheDocument();
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
