/**
 * OcrFields tests — R-43, S-33, 4.D.14
 */

import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { OcrFields } from "../OcrFields";
import type { WebComprobanteItem } from "@/lib/types";

const baseItem: WebComprobanteItem = {
  id_comprobante: "id-001",
  monto: 1500,
  banco: "BBVA",
  referencia: "REF-XYZ",
  fecha_deposito: "2024-06-15",
  estado_actual: "en_revision",
  imagen_path: "",
  fecha_registro: "2024-06-15T10:00:00Z",
  texto_extraido: null,
};

describe("OcrFields", () => {
  it("renders monto field", () => {
    render(<OcrFields item={baseItem} />);
    expect(screen.getByText("Monto")).toBeInTheDocument();
    expect(screen.getByText("$1,500")).toBeInTheDocument();
  });

  it("renders banco field", () => {
    render(<OcrFields item={baseItem} />);
    expect(screen.getByText("Banco")).toBeInTheDocument();
    expect(screen.getByText("BBVA")).toBeInTheDocument();
  });

  it("renders referencia field", () => {
    render(<OcrFields item={baseItem} />);
    expect(screen.getByText("Referencia")).toBeInTheDocument();
    expect(screen.getByText("REF-XYZ")).toBeInTheDocument();
  });

  it("renders fecha_deposito field", () => {
    render(<OcrFields item={baseItem} />);
    expect(screen.getByText("Fecha de depósito")).toBeInTheDocument();
    expect(screen.getByText("2024-06-15")).toBeInTheDocument();
  });

  it('renders "—" for null monto', () => {
    render(<OcrFields item={{ ...baseItem, monto: null }} />);
    // Only the monto row should show "—"
    const dashElements = screen.getAllByText("—");
    expect(dashElements.length).toBeGreaterThanOrEqual(1);
  });

  it('renders "—" for null banco', () => {
    render(<OcrFields item={{ ...baseItem, banco: null }} />);
    const dashElements = screen.getAllByText("—");
    expect(dashElements.length).toBeGreaterThanOrEqual(1);
  });
});
