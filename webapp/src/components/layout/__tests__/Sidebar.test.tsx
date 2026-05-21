/**
 * Sidebar tests — R-36, 4.C.17.
 */

import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { Sidebar } from "../Sidebar";

// Mock usePathname from next/navigation.
vi.mock("next/navigation", () => ({
  usePathname: vi.fn(() => "/"),
}));
vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: React.ReactNode; [key: string]: unknown }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

import { usePathname } from "next/navigation";

describe("Sidebar", () => {
  it("renders all three navigation links", () => {
    render(<Sidebar />);

    expect(screen.getByRole("link", { name: /dashboard/i })).toHaveAttribute("href", "/");
    expect(screen.getByRole("link", { name: /historial/i })).toHaveAttribute("href", "/historial");
    expect(screen.getByRole("link", { name: /revisión/i })).toHaveAttribute("href", "/revision");
  });

  it("marks Dashboard as active when pathname is /", () => {
    vi.mocked(usePathname).mockReturnValue("/");
    render(<Sidebar />);

    const dashLink = screen.getByRole("link", { name: /dashboard/i });
    expect(dashLink).toHaveAttribute("aria-current", "page");
  });

  it("marks Historial as active when pathname is /historial", () => {
    vi.mocked(usePathname).mockReturnValue("/historial");
    render(<Sidebar />);

    const histLink = screen.getByRole("link", { name: /historial/i });
    expect(histLink).toHaveAttribute("aria-current", "page");

    const dashLink = screen.getByRole("link", { name: /dashboard/i });
    expect(dashLink).not.toHaveAttribute("aria-current");
  });

  it("marks Revisión as active when pathname starts with /revision", () => {
    vi.mocked(usePathname).mockReturnValue("/revision/abc-123");
    render(<Sidebar />);

    const revLink = screen.getByRole("link", { name: /revisión/i });
    expect(revLink).toHaveAttribute("aria-current", "page");
  });

  it("renders brand name", () => {
    render(<Sidebar />);
    expect(screen.getByText("SmartVoucher")).toBeInTheDocument();
  });
});
