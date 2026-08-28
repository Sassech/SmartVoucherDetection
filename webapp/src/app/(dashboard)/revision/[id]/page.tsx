"use client";

/**
 * Revision detail page — thin client wrapper.
 * Handles fetch state, delegates rendering to RevisionDetailContent.
 */

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { fetchApi } from "@/lib/api";
import { RevisionDetailContent } from "@/components/revision/RevisionDetailContent";
import type { WebComprobanteItem } from "@/lib/types";

export default function RevisionPage() {
  const params = useParams<{ id: string }>();
  const id = params?.id ?? "";

  const [item, setItem] = useState<WebComprobanteItem | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;

    const load = async () => {
      setLoading(true);
      try {
        const data = await fetchApi<WebComprobanteItem>(`/api/web/comprobantes/${id}`);
        setItem(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Error al cargar el comprobante");
      } finally {
        setLoading(false);
      }
    };

    void load();
  }, [id]);

  return <RevisionDetailContent item={item} loading={loading} error={error} />;
}
