/**
 * Login page tests — S-19, S-01, 4.C.18.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import LoginPage from "../page";

// ── Mocks ─────────────────────────────────────────────────────────────────────

const mockLogin = vi.fn();
const mockPush = vi.fn();

vi.mock("@/lib/auth-context", () => ({
  useAuth: () => ({ login: mockLogin }),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
}));

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("LoginPage", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("renders form without authentication required (S-19)", () => {
    render(<LoginPage />);

    expect(screen.getByLabelText(/correo/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/contraseña/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /ingresar/i })).toBeInTheDocument();
  });

  it("form fields are present with correct types", () => {
    render(<LoginPage />);

    const emailInput = screen.getByLabelText(/correo/i);
    const passwordInput = screen.getByLabelText(/contraseña/i);

    expect(emailInput).toHaveAttribute("type", "email");
    expect(passwordInput).toHaveAttribute("type", "password");
  });

  it("submit calls login() with form values", async () => {
    mockLogin.mockResolvedValueOnce(undefined);
    render(<LoginPage />);

    await userEvent.type(screen.getByLabelText(/correo/i), "user@test.com");
    await userEvent.type(screen.getByLabelText(/contraseña/i), "secret123");
    await userEvent.click(screen.getByRole("button", { name: /ingresar/i }));

    await waitFor(() => {
      expect(mockLogin).toHaveBeenCalledWith("user@test.com", "secret123");
    });
  });

  it("redirects to / on successful login", async () => {
    mockLogin.mockResolvedValueOnce(undefined);
    render(<LoginPage />);

    await userEvent.type(screen.getByLabelText(/correo/i), "user@test.com");
    await userEvent.type(screen.getByLabelText(/contraseña/i), "pass");
    await userEvent.click(screen.getByRole("button", { name: /ingresar/i }));

    await waitFor(() => {
      expect(mockPush).toHaveBeenCalledWith("/");
    });
  });

  it("shows error message on 401 rejection", async () => {
    mockLogin.mockRejectedValueOnce(new Error("Invalid credentials"));
    render(<LoginPage />);

    await userEvent.type(screen.getByLabelText(/correo/i), "bad@test.com");
    await userEvent.type(screen.getByLabelText(/contraseña/i), "wrong");
    await userEvent.click(screen.getByRole("button", { name: /ingresar/i }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(/invalid credentials/i);
    });
  });

  it("does not redirect on error", async () => {
    mockLogin.mockRejectedValueOnce(new Error("Invalid credentials"));
    render(<LoginPage />);

    await userEvent.type(screen.getByLabelText(/correo/i), "bad@test.com");
    await userEvent.type(screen.getByLabelText(/contraseña/i), "wrong");
    await userEvent.click(screen.getByRole("button", { name: /ingresar/i }));

    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
    expect(mockPush).not.toHaveBeenCalled();
  });

  it("S-21: localStorage is never written during login", async () => {
    mockLogin.mockResolvedValueOnce(undefined);
    const setItemSpy = vi.spyOn(Storage.prototype, "setItem");

    render(<LoginPage />);
    await userEvent.type(screen.getByLabelText(/correo/i), "u@t.com");
    await userEvent.type(screen.getByLabelText(/contraseña/i), "pass");
    await userEvent.click(screen.getByRole("button", { name: /ingresar/i }));

    await waitFor(() => expect(mockLogin).toHaveBeenCalled());
    expect(setItemSpy).not.toHaveBeenCalledWith("access_token", expect.anything());
  });

  it("shows loading state while submitting", async () => {
    let resolve!: () => void;
    mockLogin.mockReturnValueOnce(new Promise<void>((r) => { resolve = r; }));

    render(<LoginPage />);
    await userEvent.type(screen.getByLabelText(/correo/i), "u@t.com");
    await userEvent.type(screen.getByLabelText(/contraseña/i), "pass");
    await userEvent.click(screen.getByRole("button", { name: /ingresar/i }));

    expect(screen.getByRole("button", { name: /ingresando/i })).toBeDisabled();
    resolve();
  });
});
