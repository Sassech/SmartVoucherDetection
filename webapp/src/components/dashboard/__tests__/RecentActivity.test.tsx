/**
 * RecentActivity tests — R-38, S-25, 4.D.12
 */

import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { RecentActivity } from "../RecentActivity";
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

describe("RecentActivity", () => {
  it("renders valido badge with correct text (S-25)", () => {
    const items = [makeItem({ estado_actual: "valido" })];
    render(<RecentActivity items={items} />);
    expect(screen.getByText("Válido")).toBeInTheDocument();
  });

  it("renders duplicado badge", () => {
    const items = [makeItem({ estado_actual: "duplicado" })];
    render(<RecentActivity items={items} />);
    expect(screen.getByText("Duplicado")).toBeInTheDocument();
  });

  it("renders sospechoso badge", () => {
    const items = [makeItem({ estado_actual: "sospechoso" })];
    render(<RecentActivity items={items} />);
    expect(screen.getByText("Sospechoso")).toBeInTheDocument();
  });

  it("renders en_revision badge", () => {
    const items = [makeItem({ estado_actual: "en_revision" })];
    render(<RecentActivity items={items} />);
    expect(screen.getByText("En revisión")).toBeInTheDocument();
  });

  it("truncates referencia to 12 chars", () => {
    const items = [makeItem({ referencia: "abcdef1234567890" })];
    render(<RecentActivity items={items} />);
    expect(screen.getByText("abcdef123456")).toBeInTheDocument();
    expect(screen.queryByText("abcdef1234567890")).not.toBeInTheDocument();
  });

  it("renders all items in the list", () => {
    const items = [
      makeItem({ id_comprobante: "id-001", referencia: "aaaaaaaa12345678" }),
      makeItem({ id_comprobante: "id-002", referencia: "bbbbbbbb87654321" }),
    ];
    render(<RecentActivity items={items} />);
    expect(screen.getByText("aaaaaaaa1234")).toBeInTheDocument();
    expect(screen.getByText("bbbbbbbb8765")).toBeInTheDocument();
  });
});
