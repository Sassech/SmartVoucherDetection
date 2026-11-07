/**
 * Server-side configuration shared by Server Components.
 *
 * The default points to the FastAPI service on the internal Docker network.
 * That hop never leaves the compose network and TLS terminates at nginx, so
 * plain HTTP is intentional here. Override it with API_BASE_URL.
 */
export const INTERNAL_API_BASE_URL = "http://api:8000";

export function getServerApiBaseUrl(): string {
  return process.env.API_BASE_URL ?? INTERNAL_API_BASE_URL;
}
