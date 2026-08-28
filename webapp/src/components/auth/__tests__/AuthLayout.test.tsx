/**
 * AuthLayout tests — dedup extraction (sonarqube-final-hardening AD-01).
 * Focus: title/subtitle render, children/beforeForm/afterForm slots, a11y.
 */

import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { AuthLayout, ShieldIcon, Spinner } from "../AuthLayout";

describe("AuthLayout", () => {
  it("renders title and subtitle", () => {
    render(
      <AuthLayout title="Iniciar sesión" subtitle="Portal de Validación">
        <form>form content</form>
      </AuthLayout>,
    );

    expect(screen.getByRole("heading", { level: 2, name: "Iniciar sesión" })).toBeInTheDocument();
    expect(screen.getByText("Portal de Validación")).toBeInTheDocument();
  });

  it("renders children (form slot)", () => {
    render(
      <AuthLayout title="t" subtitle="s">
        <form data-testid="the-form">form content</form>
      </AuthLayout>,
    );

    expect(screen.getByTestId("the-form")).toBeInTheDocument();
  });

  it("renders beforeForm and afterForm slots around children", () => {
    render(
      <AuthLayout
        title="t"
        subtitle="s"
        beforeForm={<div data-testid="before">banner</div>}
        afterForm={<div data-testid="after">footer link</div>}
      >
        <form data-testid="the-form" />
      </AuthLayout>,
    );

    expect(screen.getByTestId("before")).toBeInTheDocument();
    expect(screen.getByTestId("the-form")).toBeInTheDocument();
    expect(screen.getByTestId("after")).toBeInTheDocument();
  });

  it("does not render beforeForm/afterForm when omitted", () => {
    render(
      <AuthLayout title="t" subtitle="s">
        <form />
      </AuthLayout>,
    );

    expect(screen.queryByTestId("before")).not.toBeInTheDocument();
    expect(screen.queryByTestId("after")).not.toBeInTheDocument();
  });

  it("SmartVoucher brand appears twice (desktop branding + mobile header)", () => {
    render(
      <AuthLayout title="t" subtitle="s">
        <form />
      </AuthLayout>,
    );

    expect(screen.getAllByText("SmartVoucher")).toHaveLength(2);
  });

  it("branding panel is hidden from assistive tech (aria-hidden)", () => {
    const { container } = render(
      <AuthLayout title="t" subtitle="s">
        <form />
      </AuthLayout>,
    );

    const leftPanel = container.querySelector(".sv-left");
    expect(leftPanel).toHaveAttribute("aria-hidden", "true");
  });
});

describe("ShieldIcon", () => {
  it("renders an svg with default size", () => {
    const { container } = render(<ShieldIcon />);
    const svg = container.querySelector("svg");
    expect(svg).toHaveAttribute("width", "36");
    expect(svg).toHaveAttribute("height", "36");
  });

  it("respects custom size and dark props", () => {
    const { container } = render(<ShieldIcon size={32} dark />);
    const svg = container.querySelector("svg");
    expect(svg).toHaveAttribute("width", "32");
  });
});

describe("Spinner", () => {
  it("renders an svg marked aria-hidden", () => {
    const { container } = render(<Spinner />);
    const svg = container.querySelector("svg");
    expect(svg).toHaveAttribute("aria-hidden", "true");
  });
});
