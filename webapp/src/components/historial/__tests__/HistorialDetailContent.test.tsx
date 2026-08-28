/**
 * HistorialDetailContent tests — TDD for P1-webapp 3.2
 * Covers: loading skeleton, 403, error, empty, success, similarity gauge branches,
 * estados valido/duplicado/sospechoso/en_revision/error, image/no-image, monto null,
 * a11y roles, duplicate badge via estado.
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import {
  HistorialDetailContent,
  estadoToBadgeVariant,
  estadoLabel,
  estadoIcon,
  estadoIconColor,
  SimilarityGauge,
} from "../HistorialDetailContent";
import type { WebComprobanteItem } from "@/lib/types";

// Mock next/link to avoid Next router context issues in jsdom
vi.mock("next/link", () => ({
  default: ({ children, href, ...props }: { children: React.ReactNode; href: string }) => (
    // eslint-disable-next-line @next/next/no-html-link-for-pages
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

function makeItem(overrides: Partial<WebComprobanteItem> = {}): WebComprobanteItem {
  return {
    id_comprobante: "abc-123-def-456",
    imagen_path: "/uploads/img.jpg",
    referencia: "REF-001",
    monto: 12500,
    fecha_deposito: "2024-01-15",
    banco: "BANAMEX",
    estado_actual: "valido",
    fecha_registro: "2024-01-15T10:00:00Z",
    texto_extraido: "texto ocr",
    ...overrides,
  };
}

describe("HistorialDetailContent — loading", () => {
  it("should render loading skeleton when loading", () => {
    render(<HistorialDetailContent loading />);
    expect(screen.getByTestId("historial-detail-loading")).toBeInTheDocument();
  });

  it("should not render error or success content while loading", () => {
    render(<HistorialDetailContent loading />);
    expect(screen.queryByText("Acceso denegado")).not.toBeInTheDocument();
    expect(screen.queryByText("No se pudo cargar el comprobante")).not.toBeInTheDocument();
  });
});

describe("HistorialDetailContent — 403", () => {
  it("should render acceso denegado when status403", () => {
    render(<HistorialDetailContent status403 />);
    expect(screen.getByText("Acceso denegado")).toBeInTheDocument();
    expect(screen.getByText("No tienes permisos para ver este comprobante.")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });

  it("should render heading Detalle de Comprobante on 403", () => {
    render(<HistorialDetailContent status403 />);
    expect(screen.getByRole("heading", { name: /Detalle de Comprobante/i })).toBeInTheDocument();
  });

  it("prioritizes 403 over error", () => {
    render(<HistorialDetailContent status403 error="some error" item={makeItem()} />);
    expect(screen.getByText("Acceso denegado")).toBeInTheDocument();
    expect(screen.queryByText("No se pudo cargar el comprobante")).not.toBeInTheDocument();
  });

  it("prioritizes loading over 403", () => {
    render(<HistorialDetailContent loading status403 />);
    expect(screen.getByTestId("historial-detail-loading")).toBeInTheDocument();
    expect(screen.queryByText("Acceso denegado")).not.toBeInTheDocument();
  });
});

describe("HistorialDetailContent — error and empty", () => {
  it("should render error when error present and no item", () => {
    render(<HistorialDetailContent error="HTTP 500: Internal Server Error" />);
    expect(screen.getByText("No se pudo cargar el comprobante")).toBeInTheDocument();
    expect(screen.getByText("HTTP 500: Internal Server Error")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });

  it("should render error when item is null without explicit error", () => {
    render(<HistorialDetailContent item={null} />);
    expect(screen.getByText("No se pudo cargar el comprobante")).toBeInTheDocument();
  });

  it("should render error when error string and item null", () => {
    render(<HistorialDetailContent error="Network error" item={null} />);
    expect(screen.getByText("Network error")).toBeInTheDocument();
  });

  it("should render heading on error state", () => {
    render(<HistorialDetailContent error="fail" />);
    expect(screen.getByRole("heading", { name: /Detalle de Comprobante/i })).toBeInTheDocument();
  });
});

describe("HistorialDetailContent — success with data", () => {
  it("should render success with referencia and monto", () => {
    render(<HistorialDetailContent item={makeItem()} />);
    expect(screen.getAllByText("REF-001").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("$12,500")).toBeInTheDocument();
  });

  it("should render referencia fallback to truncated id when referencia null", () => {
    const item = makeItem({ referencia: null });
    render(<HistorialDetailContent item={item} />);
    // truncated id is first 12 chars
    expect(screen.getByText(item.id_comprobante.slice(0, 12))).toBeInTheDocument();
  });

  it("should render monto fallback — when null", () => {
    render(<HistorialDetailContent item={makeItem({ monto: null })} />);
    // multiple — appear; check that monto row shows —
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });

  it("should render banco and fecha", () => {
    render(<HistorialDetailContent item={makeItem()} />);
    expect(screen.getByText("BANAMEX")).toBeInTheDocument();
    expect(screen.getByText("2024-01-15")).toBeInTheDocument();
  });

  it("should render Sin imagen disponible when imagen_path falsy", () => {
    render(<HistorialDetailContent item={makeItem({ imagen_path: "" })} />);
    expect(screen.getByText("Sin imagen disponible")).toBeInTheDocument();
  });

  it("should render img when imagen_path present", () => {
    render(<HistorialDetailContent item={makeItem()} />);
    const img = screen.getByAltText("Comprobante REF-001");
    expect(img).toBeInTheDocument();
    expect(img).toHaveAttribute("src", "/api/web/comprobantes/abc-123-def-456/image");
  });

  it("should fallback alt to id when referencia null", () => {
    const item = makeItem({ referencia: null });
    render(<HistorialDetailContent item={item} />);
    expect(screen.getByAltText(`Comprobante ${item.id_comprobante}`)).toBeInTheDocument();
  });

  it("should render Revisión Manual link with correct href", () => {
    render(<HistorialDetailContent item={makeItem()} />);
    const link = screen.getByRole("link", { name: /Revisión Manual/i });
    expect(link).toHaveAttribute("href", "/revision/abc-123-def-456");
  });

  it("should render action buttons", () => {
    render(<HistorialDetailContent item={makeItem()} />);
    expect(screen.getByRole("button", { name: /Aceptar como Válido/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Marcar para Investigación de Fraude/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Ampliar imagen/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Descargar imagen/i })).toBeInTheDocument();
  });

  it("should render section headings", () => {
    render(<HistorialDetailContent item={makeItem()} />);
    expect(screen.getByText("Vista Previa del Documento Original")).toBeInTheDocument();
    expect(screen.getByText("Información Extraída")).toBeInTheDocument();
  });
});

describe("HistorialDetailContent — similarity gauge branches", () => {
  it("shows pending when similitud 0", () => {
    render(<HistorialDetailContent item={makeItem()} similitud={0} />);
    expect(screen.getByTestId("similitud-pending")).toBeInTheDocument();
    expect(screen.getByText("Sin datos de similitud aún")).toBeInTheDocument();
  });

  it("shows gauge with moderate message when similitud 75", () => {
    render(<HistorialDetailContent item={makeItem()} similitud={75} />);
    expect(screen.getByText("Similitud moderada detectada.")).toBeInTheDocument();
    expect(screen.getByText("75%")).toBeInTheDocument();
  });

  it("shows gauge with alta when similitud 95", () => {
    render(<HistorialDetailContent item={makeItem()} similitud={95} />);
    expect(screen.getByText("Alta probabilidad de duplicación.")).toBeInTheDocument();
    expect(screen.getByText("95%")).toBeInTheDocument();
  });

  it("shows gauge with sin coincidencias when similitud 10", () => {
    render(<HistorialDetailContent item={makeItem()} similitud={10} />);
    expect(screen.getByText("Sin coincidencias significativas.")).toBeInTheDocument();
  });

  it("boundary 70 -> moderada", () => {
    render(<HistorialDetailContent item={makeItem()} similitud={70} />);
    expect(screen.getByText("Similitud moderada detectada.")).toBeInTheDocument();
  });

  it("boundary 90 -> alta", () => {
    render(<HistorialDetailContent item={makeItem()} similitud={90} />);
    expect(screen.getByText("Alta probabilidad de duplicación.")).toBeInTheDocument();
  });
});

describe("HistorialDetailContent — estados", () => {
  it.each([
    ["valido" as const, "Válido"],
    ["duplicado" as const, "Duplicado"],
    ["sospechoso" as const, "Sospechoso"],
    ["en_revision" as const, "En Revisión"],
    ["error" as const, "Error"],
    ["recibido" as const, "Recibido"],
    ["procesando" as const, "Procesando"],
    ["comparando" as const, "Comparando"],
  ])("renders estado %s with label %s", (estado, label) => {
    render(<HistorialDetailContent item={makeItem({ estado_actual: estado })} />);
    expect(screen.getByText(label)).toBeInTheDocument();
  });

  it("estadoToBadgeVariant branches", () => {
    expect(estadoToBadgeVariant("valido")).toBe("valido");
    expect(estadoToBadgeVariant("duplicado")).toBe("duplicado");
    expect(estadoToBadgeVariant("sospechoso")).toBe("sospechoso");
    expect(estadoToBadgeVariant("en_revision")).toBe("en_revision");
    expect(estadoToBadgeVariant("error")).toBe("error");
    expect(estadoToBadgeVariant("recibido")).toBe("default");
    expect(estadoToBadgeVariant("procesando")).toBe("default");
  });

  it("estadoLabel fallback to Desconocido when undefined", () => {
    // @ts-expect-error testing fallback
    expect(estadoLabel(undefined)).toBe("Desconocido");
  });

  it("estadoIcon branches", () => {
    expect(estadoIcon("valido")).toBe("check_circle");
    expect(estadoIcon("duplicado")).toBe("content_copy");
    expect(estadoIcon("sospechoso")).toBe("warning");
    expect(estadoIcon("error")).toBe("error");
    expect(estadoIcon("en_revision")).toBe("info");
  });

  it("estadoIconColor branches", () => {
    expect(estadoIconColor("valido")).toContain("green");
    expect(estadoIconColor("duplicado")).toContain("red");
    expect(estadoIconColor("sospechoso")).toContain("orange");
    expect(estadoIconColor("error")).toContain("red-600");
    expect(estadoIconColor("recibido")).toContain("secondary");
  });
});

describe("SimilarityGauge", () => {
  it("renders value%", () => {
    render(<SimilarityGauge value={42} />);
    expect(screen.getByText("42%")).toBeInTheDocument();
  });

  it("hides svg from a11y", () => {
    const { container } = render(<SimilarityGauge value={80} />);
    const svg = container.querySelector("svg");
    expect(svg).toHaveAttribute("aria-hidden", "true");
  });
});

describe("HistorialDetailContent — a11y", () => {
  it("has alert role on error and 403", () => {
    const { rerender } = render(<HistorialDetailContent error="e" />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
    rerender(<HistorialDetailContent status403 />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });

  it("buttons have type button", () => {
    render(<HistorialDetailContent item={makeItem()} />);
    const buttons = screen.getAllByRole("button");
    for (const btn of buttons) {
      expect(btn).toHaveAttribute("type", "button");
    }
  });

  it("image has alt text", () => {
    render(<HistorialDetailContent item={makeItem()} />);
    expect(screen.getByAltText(/Comprobante/)).toBeInTheDocument();
  });
});
