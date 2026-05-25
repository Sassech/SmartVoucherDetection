"use client";

/**
 * DuplicatePanel — decision panel for en_revision comprobantes — R-44, R-45, S-34, S-35, S-36, 4.D.10
 */

import { useState } from "react";
import { fetchApi } from "@/lib/api";
import type { WebComprobanteItem } from "@/lib/types";

function estadoLabel(estado: WebComprobanteItem["estado_actual"]): string {
  switch (estado) {
    case "valido": return "Válido";
    case "duplicado": return "Duplicado";
    case "sospechoso": return "Sospechoso";
    case "en_revision": return "En Revisión";
    case "error": return "Error";
    default: return "Procesando";
  }
}

interface DuplicatePanelProps {
  item: WebComprobanteItem;
  onDecision?: (decision: "aceptar" | "rechazar") => void;
}

export function DuplicatePanel({ item, onDecision }: DuplicatePanelProps) {
  const [estado, setEstado] = useState<WebComprobanteItem["estado_actual"]>(item.estado_actual);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [motivo, setMotivo] = useState("");

  async function handleDecision(accion: "aceptar" | "rechazar") {
    const prevEstado = estado;
    setEstado(accion === "aceptar" ? "valido" : "duplicado");
    setError(null);
    setPending(true);

    try {
      await fetchApi(`/api/web/comprobantes/${item.id_comprobante}/decision`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ accion, motivo: motivo || undefined }),
      });
      onDecision?.(accion);
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
        {/* No duplicate candidates available — texto_extraido is plain OCR text, not JSON */}
        <div className="rounded-lg bg-[var(--color-surface-container-low)] border border-[var(--color-outline-variant)] px-4 py-3 flex items-center gap-2">
          <span className="material-symbols-outlined text-[var(--color-secondary)] text-[18px]">info</span>
          <p className="text-xs text-[var(--color-secondary)]">
            No hay candidatos duplicados disponibles
          </p>
        </div>

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
            value={motivo}
            onChange={(e) => setMotivo(e.target.value)}
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
            onClick={() => void handleDecision("rechazar")}
            disabled={pending}
            className="w-full flex items-center justify-center gap-2 bg-[var(--color-error)] text-white py-3 rounded-lg text-sm font-bold hover:bg-red-700 transition-colors disabled:opacity-50 shadow-sm"
          >
            <span className="material-symbols-outlined text-[18px]">block</span>
            Confirmar como Duplicado
          </button>
          <button
            type="button"
            onClick={() => void handleDecision("aceptar")}
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
