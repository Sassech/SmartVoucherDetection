"use client";

/**
 * DuplicatePanel — decision panel for en_revision comprobantes — R-44, R-45, S-34, S-35, S-36, 4.D.10
 */

import { useState } from "react";
import { fetchApi } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import type { WebComprobanteItem } from "@/lib/types";
import type { BadgeProps } from "@/components/ui/badge";

interface DuplicateCandidate {
  id_comprobante_original: string;
  score_similitud: number;
}

function parseCandidates(texto: string | null): DuplicateCandidate[] {
  if (!texto) return [];
  try {
    const parsed = JSON.parse(texto) as unknown;
    if (Array.isArray(parsed)) {
      return parsed as DuplicateCandidate[];
    }
    return [];
  } catch {
    return [];
  }
}

function estadoToBadgeVariant(estado: WebComprobanteItem["estado"]): BadgeProps["variant"] {
  switch (estado) {
    case "procesado": return "valido";
    case "duplicado": return "duplicado";
    case "sospechoso": return "sospechoso";
    case "en_revision": return "en_revision";
    case "error": return "error";
    default: return "default";
  }
}

interface DuplicatePanelProps {
  item: WebComprobanteItem;
  onDecision?: (decision: "valido" | "duplicado") => void;
}

export function DuplicatePanel({ item, onDecision }: DuplicatePanelProps) {
  const [estado, setEstado] = useState<WebComprobanteItem["estado"]>(item.estado);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const candidates = parseCandidates(item.texto_extraido);

  async function handleDecision(decision: "valido" | "duplicado") {
    const prevEstado = estado;
    // Optimistic update
    setEstado(decision === "valido" ? "procesado" : "duplicado");
    setError(null);
    setPending(true);

    try {
      await fetchApi(`/api/web/comprobantes/${item.id_comprobante}/decision`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ decision }),
      });
      onDecision?.(decision);
    } catch (err) {
      // Revert optimistic update
      setEstado(prevEstado);
      setError(err instanceof Error ? err.message : "Error al procesar la decisión");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="flex flex-col gap-5 rounded-[var(--radius-lg)] border border-[var(--color-outline-variant)] bg-[var(--color-surface)] p-5">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-[var(--color-on-surface)]">
          Revisión de Comprobante
        </h2>
        <Badge variant={estadoToBadgeVariant(estado)}>{estado}</Badge>
      </div>

      {/* Candidates table */}
      {candidates.length > 0 && (
        <div>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--color-on-surface-variant)]">
            Posibles duplicados
          </h3>
          <table className="w-full text-sm">
            <thead>
              <tr>
                <th className="pb-1 text-left text-xs font-medium text-[var(--color-on-surface-variant)]">
                  ID Original
                </th>
                <th className="pb-1 text-right text-xs font-medium text-[var(--color-on-surface-variant)]">
                  Similitud
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--color-outline-variant)]">
              {candidates.map((c) => (
                <tr key={c.id_comprobante_original}>
                  <td className="py-1.5 font-mono text-xs text-[var(--color-primary)]">
                    {c.id_comprobante_original}
                  </td>
                  <td className="py-1.5 text-right text-xs text-[var(--color-on-surface)]">
                    {Math.round(c.score_similitud * 100)}%
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Error message */}
      {error && (
        <div className="rounded-[var(--radius-sm)] bg-red-50 border border-red-200 px-3 py-2">
          <p className="text-xs text-red-700">Error: {error}</p>
        </div>
      )}

      {/* Decision buttons */}
      <div className="flex gap-3">
        <button
          type="button"
          onClick={() => void handleDecision("valido")}
          disabled={pending}
          className="flex-1 rounded-[var(--radius-md)] bg-[var(--color-primary)] px-4 py-2 text-sm font-medium text-white hover:opacity-90 transition-opacity disabled:opacity-50"
        >
          Aceptar
        </button>
        <button
          type="button"
          onClick={() => void handleDecision("duplicado")}
          disabled={pending}
          className="flex-1 rounded-[var(--radius-md)] border border-red-300 bg-red-50 px-4 py-2 text-sm font-medium text-red-700 hover:bg-red-100 transition-colors disabled:opacity-50"
        >
          Rechazar
        </button>
      </div>
    </div>
  );
}
