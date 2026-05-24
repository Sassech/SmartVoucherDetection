"use client";

/**
 * DuplicatePanel — decision panel for en_revision comprobantes — R-44, R-45, S-34, S-35, S-36, 4.D.10
 */

import { useState } from "react";
import { fetchApi } from "@/lib/api";
import type { WebComprobanteItem } from "@/lib/types";

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

function estadoLabel(estado: WebComprobanteItem["estado"]): string {
  switch (estado) {
    case "procesado": return "Válido";
    case "duplicado": return "Duplicado";
    case "sospechoso": return "Sospechoso";
    case "en_revision": return "En Revisión";
    case "error": return "Error";
    default: return "Pendiente";
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
  const [comment, setComment] = useState("");

  const candidates = parseCandidates(item.texto_extraido ?? null);

  async function handleDecision(decision: "valido" | "duplicado") {
    const prevEstado = estado;
    setEstado(decision === "valido" ? "procesado" : "duplicado");
    setError(null);
    setPending(true);

    try {
      await fetchApi(`/api/web/comprobantes/${item.id_comprobante}/decision`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ decision, comment }),
      });
      onDecision?.(decision);
    } catch (err) {
      setEstado(prevEstado);
      setError(err instanceof Error ? err.message : "Error al procesar la decisión");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="flex flex-col gap-0 rounded-xl border border-[var(--color-outline-variant)] bg-white overflow-hidden shadow-sm">
      {/* Card header */}
      <div className="px-5 py-4 border-b border-[var(--color-outline-variant)] bg-[var(--color-surface-container-low)] flex items-center justify-between">
        <h2 className="text-sm font-semibold text-[var(--color-on-surface)] flex items-center gap-2">
          <span className="material-symbols-outlined text-[20px] text-[var(--color-primary)]">
            gavel
          </span>
          Decisión Final
        </h2>
        <span className="text-[11px] font-bold px-2 py-0.5 rounded bg-[var(--color-surface-container-high)] text-[var(--color-on-surface-variant)]">
          {estadoLabel(estado)}
        </span>
      </div>

      <div className="p-5 flex flex-col gap-5">
        {/* Candidates table */}
        {candidates.length > 0 && (
          <div>
            <div className="border border-[var(--color-error-container)]/30 bg-[var(--color-error-container)]/5 rounded-lg overflow-hidden">
              {/* Warning header */}
              <div className="px-4 py-3 border-b border-[var(--color-error-container)]/30 bg-red-50/50 flex items-center gap-2">
                <span className="material-symbols-outlined text-[var(--color-error)] text-[18px]">
                  content_copy
                </span>
                <h3 className="text-xs font-semibold text-[var(--color-error)]">
                  Posibles Duplicados Encontrados
                </h3>
              </div>
              <table className="w-full text-left text-sm">
                <thead className="bg-[var(--color-surface-container-low)] border-b border-[var(--color-outline-variant)]">
                  <tr>
                    <th className="px-4 py-2 text-[10px] font-bold uppercase text-[var(--color-secondary)]">
                      ID Original
                    </th>
                    <th className="px-4 py-2 text-[10px] font-bold uppercase text-[var(--color-secondary)] text-right">
                      Similitud
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--color-outline-variant)]/50">
                  {candidates.map((c) => (
                    <tr key={c.id_comprobante_original} className="hover:bg-[var(--color-surface-container-low)] transition-colors">
                      <td className="px-4 py-3 font-mono text-xs text-[var(--color-primary)]">
                        {c.id_comprobante_original}
                      </td>
                      <td className="px-4 py-3 text-right text-xs font-semibold text-[var(--color-on-surface)]">
                        {Math.round(c.score_similitud * 100)}%
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="mt-3 flex items-start gap-2 bg-[var(--color-surface-container-high)]/50 p-3 rounded-lg">
              <span className="material-symbols-outlined text-[var(--color-secondary)] text-[18px] shrink-0">info</span>
              <p className="text-[11px] text-[var(--color-secondary)] italic leading-relaxed">
                Este registro comparte características similares con entradas previas. Verifique antes de confirmar.
              </p>
            </div>
          </div>
        )}

        {/* Reviewer comment */}
        <div>
          <label
            htmlFor="reviewer-comment"
            className="block text-[11px] font-medium text-[var(--color-secondary)] mb-2"
          >
            Comentarios del Revisor
          </label>
          <textarea
            id="reviewer-comment"
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="Explique su decisión aquí..."
            rows={3}
            className="w-full rounded-lg border border-[var(--color-outline-variant)] p-3 text-sm text-[var(--color-on-surface)] bg-white focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]/20 focus:border-[var(--color-primary)] resize-none placeholder:text-[var(--color-outline)]"
          />
        </div>

        {/* Error message */}
        {error && (
          <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 flex items-start gap-2">
            <span className="material-symbols-outlined text-red-600 text-[18px] shrink-0">error</span>
            <p className="text-xs text-red-700">{error}</p>
          </div>
        )}

        {/* Decision buttons */}
        <div className="flex flex-col gap-3 mt-auto">
          <button
            type="button"
            onClick={() => void handleDecision("duplicado")}
            disabled={pending}
            className="w-full flex items-center justify-center gap-2 bg-[var(--color-error)] text-white py-3 rounded-lg text-sm font-bold hover:bg-red-700 transition-colors disabled:opacity-50 shadow-sm"
          >
            <span className="material-symbols-outlined text-[18px]">block</span>
            Confirmar como Duplicado
          </button>
          <button
            type="button"
            onClick={() => void handleDecision("valido")}
            disabled={pending}
            className="w-full flex items-center justify-center gap-2 bg-emerald-500 text-white py-3 rounded-lg text-sm font-bold hover:bg-emerald-600 transition-colors disabled:opacity-50 shadow-sm"
          >
            <span className="material-symbols-outlined text-[18px]">verified</span>
            Anular — Marcar como Válido
          </button>
          <p className="text-center text-[10px] text-[var(--color-secondary)] px-4 uppercase tracking-wide">
            Las acciones se registran y no se pueden deshacer
          </p>
        </div>
      </div>
    </div>
  );
}
