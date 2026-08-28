/**
 * Historial detail page — thin RSC wrapper.
 * Fetches comprobante by ID server-side, delegates rendering to HistorialDetailContent.
 */

import { cookies } from "next/headers";
import { HistorialDetailContent } from "@/components/historial/HistorialDetailContent";
import type { WebComprobanteItem } from "@/lib/types";

interface Props {
  params: Readonly<Promise<{ id: string }>>;
}

async function fetchComprobante(id: string): Promise<{
  item: WebComprobanteItem | null;
  error: string | null;
  status403: boolean;
}> {
  try {
    const cookieStore = await cookies();
    const token = cookieStore.get("access_token")?.value;
    const baseUrl = process.env.API_BASE_URL ?? "http://api:8000";

    const headers: Record<string, string> = {};
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }

    const res = await fetch(`${baseUrl}/web/comprobantes/${id}`, {
      headers,
      cache: "no-store",
    });

    if (res.status === 403) {
      return { item: null, error: null, status403: true };
    }
    if (!res.ok) {
      return { item: null, error: `HTTP ${res.status}: ${res.statusText}`, status403: false };
    }
    const item = (await res.json()) as WebComprobanteItem;
    return { item, error: null, status403: false };
  } catch (err) {
    return { item: null, error: err instanceof Error ? err.message : "Error desconocido", status403: false };
  }
}

export default async function HistorialDetailPage({ params }: Readonly<Props>) {
  const { id } = await params;
  const { item, error, status403 } = await fetchComprobante(id);
  return <HistorialDetailContent item={item} error={error} status403={status403} />;
}
