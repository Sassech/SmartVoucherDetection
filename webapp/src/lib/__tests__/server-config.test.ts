import { afterEach, describe, expect, it, vi } from "vitest";
import { getServerApiBaseUrl, INTERNAL_API_BASE_URL } from "../server-config";

describe("getServerApiBaseUrl", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("returns API_BASE_URL when it is set", () => {
    vi.stubEnv("API_BASE_URL", "https://api.example.test");
    expect(getServerApiBaseUrl()).toBe("https://api.example.test");
  });

  it("falls back to the internal Docker service URL when API_BASE_URL is unset", () => {
    vi.stubEnv("API_BASE_URL", undefined);
    expect(getServerApiBaseUrl()).toBe(INTERNAL_API_BASE_URL);
    expect(INTERNAL_API_BASE_URL).toBe("http://api:8000");
  });
});
