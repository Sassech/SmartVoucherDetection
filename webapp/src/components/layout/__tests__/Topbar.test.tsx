/**
 * Topbar tests — R-36, 4.C.17.
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { Topbar } from "../Topbar";

// ── Mock useAuth ──────────────────────────────────────────────────────────────

const mockLogout = vi.fn();
const mockUseAuth = vi.fn();

vi.mock("@/lib/auth-context", () => ({
  useAuth: () => mockUseAuth(),
}));

describe("Topbar", () => {
  it("renders user nombre when authenticated", () => {
    mockUseAuth.mockReturnValue({
      user: { nombre: "María García", rol: "admin", correo: "m@g.com", id_usuario: "u1", id_organizacion: "org1" },
      logout: mockLogout,
    });

    render(<Topbar />);
    expect(screen.getByText("María García")).toBeInTheDocument();
  });

  it("renders logout button", () => {
    mockUseAuth.mockReturnValue({ user: null, logout: mockLogout });
    render(<Topbar />);
    expect(screen.getByRole("button", { name: /salir|logout|cerrar sesión/i })).toBeInTheDocument();
  });

  it("clicking logout calls logout()", async () => {
    mockUseAuth.mockReturnValue({ user: null, logout: mockLogout });
    render(<Topbar />);

    await userEvent.click(screen.getByRole("button", { name: /salir|logout|cerrar sesión/i }));
    expect(mockLogout).toHaveBeenCalledTimes(1);
  });

  it("renders nothing for nombre when user is null", () => {
    mockUseAuth.mockReturnValue({ user: null, logout: mockLogout });
    render(<Topbar />);
    // No nombre text — just the button.
    expect(screen.queryByText(/García/i)).not.toBeInTheDocument();
  });
});
