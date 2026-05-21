/**
 * Auth context tests — R-34, S-21.
 */

import { render, screen, act, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { AuthProvider, useAuth, getAccessToken, setAccessToken } from "../auth-context";

// ── Mock global fetch ─────────────────────────────────────────────────────────

function mockFetch(responses: Array<{ ok: boolean; json?: unknown; status?: number }>) {
  let callIndex = 0;
  return vi.fn().mockImplementation(() => {
    const resp = responses[callIndex % responses.length];
    callIndex++;
    return Promise.resolve({
      ok: resp.ok,
      status: resp.status ?? (resp.ok ? 200 : 401),
      json: () => Promise.resolve(resp.json ?? {}),
    });
  });
}

// ── Test component that consumes auth context ─────────────────────────────────

function TestConsumer() {
  const { user, token, login, logout } = useAuth();
  return (
    <div>
      <span data-testid="user">{user ? user.nombre : "none"}</span>
      <span data-testid="token">{token ?? "null"}</span>
      <button onClick={() => void login("a@b.com", "pass")}>Login</button>
      <button onClick={() => void logout()}>Logout</button>
    </div>
  );
}

function renderWithProvider() {
  return render(
    <AuthProvider>
      <TestConsumer />
    </AuthProvider>,
  );
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("AuthProvider", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    // Reset module-level token between tests.
    setAccessToken(null);
  });

  it("initial state is unauthenticated (no user, no token)", async () => {
    // Refresh attempt fails on mount.
    global.fetch = mockFetch([{ ok: false, status: 401 }]);

    renderWithProvider();

    await waitFor(() => {
      expect(screen.getByTestId("user").textContent).toBe("none");
      expect(screen.getByTestId("token").textContent).toBe("null");
    });
  });

  it("login() stores token in context", async () => {
    global.fetch = mockFetch([
      { ok: false, status: 401 }, // mount refresh fails
      { ok: true, json: { access_token: "tok-123" } }, // login
      { ok: true, json: { id_usuario: "u1", correo: "a@b.com", nome: "Ana", nombre: "Ana", rol: "admin", id_organizacion: "org1" } }, // /me
    ]);

    renderWithProvider();

    await waitFor(() => expect(screen.getByTestId("token").textContent).toBe("null"));

    await act(async () => {
      await userEvent.click(screen.getByText("Login"));
    });

    await waitFor(() => {
      expect(screen.getByTestId("token").textContent).toBe("tok-123");
    });
  });

  it("logout() clears token and user from context", async () => {
    global.fetch = mockFetch([
      { ok: false, status: 401 }, // mount refresh fails
      { ok: true, json: { access_token: "tok-xyz" } }, // login
      { ok: true, json: { id_usuario: "u1", correo: "a@b.com", nombre: "Ana", rol: "admin", id_organizacion: "org1" } }, // /me
      { ok: true }, // logout
    ]);

    renderWithProvider();
    await waitFor(() => expect(screen.getByTestId("token").textContent).toBe("null"));

    await act(async () => {
      await userEvent.click(screen.getByText("Login"));
    });
    await waitFor(() => expect(screen.getByTestId("token").textContent).toBe("tok-xyz"));

    await act(async () => {
      await userEvent.click(screen.getByText("Logout"));
    });

    await waitFor(() => {
      expect(screen.getByTestId("token").textContent).toBe("null");
      expect(screen.getByTestId("user").textContent).toBe("none");
    });
  });

  it("S-21: localStorage is never written after login", async () => {
    global.fetch = mockFetch([
      { ok: false, status: 401 }, // mount refresh
      { ok: true, json: { access_token: "tok-safe" } }, // login
      { ok: true, json: { id_usuario: "u1", correo: "a@b.com", nombre: "Ana", rol: "admin", id_organizacion: "org1" } }, // /me
    ]);

    const setItemSpy = vi.spyOn(Storage.prototype, "setItem");

    renderWithProvider();
    await waitFor(() => expect(screen.getByTestId("token").textContent).toBe("null"));

    await act(async () => {
      await userEvent.click(screen.getByText("Login"));
    });

    await waitFor(() => expect(screen.getByTestId("token").textContent).toBe("tok-safe"));

    expect(setItemSpy).not.toHaveBeenCalledWith("access_token", expect.anything());
    expect(localStorage.getItem("access_token")).toBeNull();
  });

  it("context updates trigger re-render with new user", async () => {
    global.fetch = mockFetch([
      { ok: false, status: 401 }, // mount refresh
      { ok: true, json: { access_token: "tok-user" } }, // login
      { ok: true, json: { id_usuario: "u1", correo: "a@b.com", nombre: "Carlos", rol: "operador", id_organizacion: "org2" } }, // /me
    ]);

    renderWithProvider();
    await waitFor(() => expect(screen.getByTestId("user").textContent).toBe("none"));

    await act(async () => {
      await userEvent.click(screen.getByText("Login"));
    });

    await waitFor(() => {
      expect(screen.getByTestId("user").textContent).toBe("Carlos");
    });
  });
});
