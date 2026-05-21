/**
 * RecentActivity tests — R-38, S-25, 4.D.12
 */

import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { RecentActivity } from "../RecentActivity";
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

describe("RecentActivity", () => {
  it("renders valido badge with correct text (S-25)", () => {
    const items = [makeItem({ estado: "procesado" })];
    render(<RecentActivity items={items} />);
    expect(screen.getByText("procesado")).toBeInTheDocument();
  });

  it("renders duplicado badge", () => {
    const items = [makeItem({ estado: "duplicado" })];
    render(<RecentActivity items={items} />);
    expect(screen.getByText("duplicado")).toBeInTheDocument();
  });

  it("renders sospechoso badge", () => {
    const items = [makeItem({ estado: "sospechoso" })];
    render(<RecentActivity items={items} />);
    expect(screen.getByText("sospechoso")).toBeInTheDocument();
  });

  it("renders en_revision badge", () => {
    const items = [makeItem({ estado: "en_revision" })];
    render(<RecentActivity items={items} />);
    expect(screen.getByText("en_revision")).toBeInTheDocument();
  });

  it("truncates folio to 8 chars", () => {
    const items = [makeItem({ folio: "abcdef1234567890" })];
    render(<RecentActivity items={items} />);
    expect(screen.getByText("abcdef12")).toBeInTheDocument();
    expect(screen.queryByText("abcdef1234567890")).not.toBeInTheDocument();
  });

  it("renders all items in the list", () => {
    const items = [
      makeItem({ id_comprobante: "id-001", folio: "aaaaaaaa12345678" }),
      makeItem({ id_comprobante: "id-002", folio: "bbbbbbbb87654321" }),
    ];
    render(<RecentActivity items={items} />);
    expect(screen.getByText("aaaaaaaa")).toBeInTheDocument();
    expect(screen.getByText("bbbbbbbb")).toBeInTheDocument();
  });
});
