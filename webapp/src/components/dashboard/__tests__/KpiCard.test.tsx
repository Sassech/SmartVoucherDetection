/**
 * KpiCard tests — R-37, S-23, S-24, 4.D.12
 */

import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { KpiCard } from "../KpiCard";

describe("KpiCard", () => {
  it("renders the label correctly", () => {
    render(<KpiCard label="Total Comprobantes" value={42} icon="analytics" />);
    expect(screen.getByText("Total Comprobantes")).toBeInTheDocument();
  });

  it("renders the numeric value", () => {
    render(<KpiCard label="Pendientes" value={7} icon="pending" />);
    expect(screen.getByText("7")).toBeInTheDocument();
  });

  it("renders 0 without crash (S-24)", () => {
    render(<KpiCard label="Duplicados" value={0} icon="content_copy" />);
    expect(screen.getByText("0")).toBeInTheDocument();
    expect(screen.getByText("Duplicados")).toBeInTheDocument();
  });
});
