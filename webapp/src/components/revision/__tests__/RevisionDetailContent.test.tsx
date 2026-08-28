/**
 * RevisionDetailContent tests — TDD for P1-webapp 3.4
 * Covers: loading skeleton, error, empty, success with data, texto_extraido branch,
 * VoucherViewer/OcrFields/DuplicatePanel integration, a11y, heading.
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { RevisionDetailContent } from "../RevisionDetailContent";
import type { WebComprobanteItem } from "@/lib/types";

// Mock fetchApi used indirectly by DuplicatePanel's decision handler.
// DuplicatePanel only calls fetchApi on button click; render doesn't trigger it,
// but we mock to prevent accidental network calls if tests click.
vi.mock("@/lib/api", () => ({
  fetchApi: vi.fn().mockResolvedValue({}),
}));

function makeItem(overrides: Partial<WebComprobanteItem> = {}): WebComprobanteItem {
  return {
    id_comprobante: "rev-123-abc",
    imagen_path: "/uploads/rev.jpg",
    referencia: "REF-REV-001",
    monto: 9999,
    fecha_deposito: "2024-02-01",
    banco: "BBVA",
    estado_actual: "en_revision",
    fecha_registro: "2024-02-01T10:00:00Z",
    texto_extraido: null,
    ...overrides,
  };
}

describe("RevisionDetailContent — loading", () => {
  it("should render loading skeleton when loading", () => {
    render(<RevisionDetailContent loading />);
    expect(screen.getByTestId("revision-detail-loading")).toBeInTheDocument();
  });

  it("should not render error or success content while loading", () => {
    render(<RevisionDetailContent loading />);
    expect(screen.queryByText("No se pudo cargar el comprobante")).not.toBeInTheDocument();
    expect(screen.queryByText("Revisión de Comprobante")).not.toBeInTheDocument();
  });

  it("prioritizes loading over error", () => {
    render(<RevisionDetailContent loading error="oops" />);
    expect(screen.getByTestId("revision-detail-loading")).toBeInTheDocument();
    expect(screen.queryByText("oops")).not.toBeInTheDocument();
  });
});

describe("RevisionDetailContent — error and empty", () => {
  it("should render error when error present", () => {
    render(<RevisionDetailContent error="HTTP 500: Internal Server Error" />);
    expect(screen.getByText("No se pudo cargar el comprobante")).toBeInTheDocument();
    expect(screen.getByText("HTTP 500: Internal Server Error")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });

  it("should render error when item is null without explicit error", () => {
    render(<RevisionDetailContent item={null} />);
    expect(screen.getByText("No se pudo cargar el comprobante")).toBeInTheDocument();
  });

  it("should render error when both item null and error", () => {
    render(<RevisionDetailContent item={null} error="Network error" />);
    expect(screen.getByText("Network error")).toBeInTheDocument();
  });

  it("should render heading on error state", () => {
    render(<RevisionDetailContent error="fail" />);
    expect(screen.getByRole("heading", { name: /Revisión de Comprobante/i })).toBeInTheDocument();
  });

  it("prioritizes error over item when error present", () => {
    // If error is set but item also provided, current impl shows error first
    render(<RevisionDetailContent item={makeItem()} error="some error" />);
    expect(screen.getByText("some error")).toBeInTheDocument();
  });
});

describe("RevisionDetailContent — success with data", () => {
  it("should render heading and layout when item present", () => {
    render(<RevisionDetailContent item={makeItem()} />);
    expect(screen.getByRole("heading", { name: /Revisión de Comprobante/i })).toBeInTheDocument();
  });

  it("should render VoucherViewer with imagen_path", () => {
    render(<RevisionDetailContent item={makeItem({ imagen_path: "/uploads/rev.jpg" })} />);
    // VoucherViewer renders Carga Original header
    expect(screen.getByText("Carga Original")).toBeInTheDocument();
  });

  it("should render VoucherViewer fallback when imagen_path null", () => {
    render(<RevisionDetailContent item={makeItem({ imagen_path: "" })} />);
    expect(screen.getByText("Sin imagen disponible")).toBeInTheDocument();
  });

  it("should render OcrFields data", () => {
    render(<RevisionDetailContent item={makeItem()} />);
    expect(screen.getByText("Datos OCR Extraídos")).toBeInTheDocument();
    // OcrFields renders monto and banco; check monto present
    expect(screen.getByText("$9,999")).toBeInTheDocument();
    expect(screen.getByText("BBVA")).toBeInTheDocument();
  });

  it("should render DuplicatePanel decision buttons", () => {
    render(<RevisionDetailContent item={makeItem()} />);
    expect(screen.getByText("Decisión Final")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Confirmar como Duplicado/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Marcar como Válido/i })).toBeInTheDocument();
  });

  it("should not render Texto Extraído when texto_extraido null", () => {
    render(<RevisionDetailContent item={makeItem({ texto_extraido: null })} />);
    expect(screen.queryByText("Texto Extraído")).not.toBeInTheDocument();
  });

  it("should render Texto Extraído when texto_extraido present", () => {
    const { container } = render(
      <RevisionDetailContent item={makeItem({ texto_extraido: "OCR raw text line 1\nline 2" })} />,
    );
    expect(screen.getByText("Texto Extraído")).toBeInTheDocument();
    const pre = container.querySelector("pre");
    expect(pre?.textContent).toContain("OCR raw text line 1");
    expect(pre?.textContent).toContain("line 2");
  });

  it("should render texto_extraido inside pre element", () => {
    const { container } = render(<RevisionDetailContent item={makeItem({ texto_extraido: "hello" })} />);
    const pre = container.querySelector("pre");
    expect(pre).toBeInTheDocument();
    expect(pre?.textContent).toBe("hello");
  });

  it("handles different estado_actual values without crashing", () => {
    for (const estado of ["valido", "duplicado", "sospechoso", "en_revision", "error"] as const) {
      const { unmount } = render(<RevisionDetailContent item={makeItem({ estado_actual: estado })} />);
      expect(screen.getByRole("heading", { name: /Revisión de Comprobante/i })).toBeInTheDocument();
      unmount();
    }
  });
});

describe("RevisionDetailContent — a11y", () => {
  it("has alert role on error", () => {
    render(<RevisionDetailContent error="e" />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });

  it("heading is accessible", () => {
    render(<RevisionDetailContent item={makeItem()} />);
    expect(screen.getByRole("heading", { name: /Revisión de Comprobante/i })).toBeInTheDocument();
  });

  it("buttons have type button via DuplicatePanel", () => {
    render(<RevisionDetailContent item={makeItem()} />);
    const buttons = screen.getAllByRole("button");
    for (const btn of buttons) {
      expect(btn).toHaveAttribute("type", "button");
    }
  });
});
