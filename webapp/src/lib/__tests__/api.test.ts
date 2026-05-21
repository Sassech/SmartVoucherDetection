/**
 * fetchApi tests — R-35, S-20.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { fetchApi, ApiError } from "../api";
import { setAccessToken } from "../auth-context";

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
    headers: new Headers(),
  } as unknown as Response;
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("fetchApi", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    setAccessToken(null);
  });

  it("happy path: returns parsed JSON on 200", async () => {
    global.fetch = vi.fn().mockResolvedValueOnce(makeResponse(200, { id: 1 }));

    const result = await fetchApi<{ id: number }>("/api/test");
    expect(result).toEqual({ id: 1 });
  });

  it("attaches Authorization header when token is set", async () => {
    setAccessToken("my-token");
    global.fetch = vi.fn().mockResolvedValueOnce(makeResponse(200, {}));

    await fetchApi("/api/test");

    const calledWith = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [string, RequestInit];
    const headers = new Headers(calledWith[1].headers);
    expect(headers.get("Authorization")).toBe("Bearer my-token");
  });

  it("S-20: single 401 triggers one refresh, then retries", async () => {
    setAccessToken("expired-token");

    const fetchMock = vi.fn()
      .mockResolvedValueOnce(makeResponse(401, { detail: "Unauthorized" })) // original request fails
      .mockResolvedValueOnce(makeResponse(200, { access_token: "new-token" })) // refresh
      .mockResolvedValueOnce(makeResponse(200, { data: "ok" })); // retry

    global.fetch = fetchMock;

    const result = await fetchApi<{ data: string }>("/api/protected");

    expect(result).toEqual({ data: "ok" });
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("S-20: concurrent 401s share one refresh call", async () => {
    setAccessToken("concurrent-expired");

    let refreshCallCount = 0;
    // Track call count per URL to differentiate original vs retry.
    const callCountByUrl: Record<string, number> = {};

    global.fetch = vi.fn().mockImplementation((url: string) => {
      callCountByUrl[url] = (callCountByUrl[url] ?? 0) + 1;

      if ((url as string).includes("/api/web/auth/refresh")) {
        refreshCallCount++;
        return Promise.resolve(makeResponse(200, { access_token: "shared-new-token" }));
      }

      // For the protected endpoint: first 3 calls return 401, subsequent retries return 200.
      const callNum = callCountByUrl[url];
      if (callNum <= 3) {
        return Promise.resolve(makeResponse(401, { detail: "Unauthorized" }));
      }
      return Promise.resolve(makeResponse(200, { data: "retried" }));
    });

    // Launch 3 concurrent requests that all hit 401.
    const results = await Promise.all([
      fetchApi<{ data: string }>("/api/protected"),
      fetchApi<{ data: string }>("/api/protected"),
      fetchApi<{ data: string }>("/api/protected"),
    ]);

    // All retries should succeed.
    expect(results).toHaveLength(3);
    results.forEach((r) => expect(r).toEqual({ data: "retried" }));

    // Refresh must have been called EXACTLY once.
    expect(refreshCallCount).toBe(1);
  });

  it("non-401 error propagates as ApiError", async () => {
    global.fetch = vi
      .fn()
      .mockResolvedValueOnce(makeResponse(500, { detail: "Server error" }));

    await expect(fetchApi("/api/test")).rejects.toBeInstanceOf(ApiError);
  });

  it("non-401 error has correct status code", async () => {
    global.fetch = vi
      .fn()
      .mockResolvedValueOnce(makeResponse(500, { detail: "Server error" }));

    try {
      await fetchApi("/api/test");
    } catch (err) {
      expect(err).toBeInstanceOf(ApiError);
      expect((err as ApiError).status).toBe(500);
    }
  });

  it("refresh failure redirects to /login (window.location mock)", async () => {
    setAccessToken("stale");
    const originalLocation = window.location;
    // jsdom doesn't allow direct location.href assignment easily — mock it.
    Object.defineProperty(window, "location", {
      writable: true,
      value: { href: "" },
    });

    global.fetch = vi.fn()
      .mockResolvedValueOnce(makeResponse(401, {})) // original
      .mockResolvedValueOnce(makeResponse(401, {})); // refresh fails

    await expect(fetchApi("/api/protected")).rejects.toBeInstanceOf(ApiError);
    expect(window.location.href).toBe("/login");

    Object.defineProperty(window, "location", { writable: true, value: originalLocation });
  });
});
