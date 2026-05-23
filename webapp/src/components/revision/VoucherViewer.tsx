"use client";

/**
 * VoucherViewer — renders comprobante image with Skeleton loading state — R-43, S-33, 4.D.9
 */

import { useState } from "react";
import { Skeleton } from "@/components/ui/skeleton";

interface VoucherViewerProps {
  src: string | null;
  alt?: string;
}

export function VoucherViewer({ src, alt = "comprobante" }: VoucherViewerProps) {
  const [loaded, setLoaded] = useState(false);

  if (!src) {
    return (
      <div className="bg-white border border-[var(--color-outline-variant)] rounded-xl overflow-hidden flex flex-col">
        <div className="px-6 py-4 border-b border-[var(--color-outline-variant)] bg-[var(--color-surface-container-low)]">
          <h3 className="text-base font-semibold flex items-center gap-2 text-[var(--color-on-surface)]">
            <span className="material-symbols-outlined text-[var(--color-primary)]">image</span>
            Carga Original
          </h3>
        </div>
        <div className="flex-1 bg-slate-100 p-10 flex items-center justify-center min-h-[400px]">
          <p className="text-sm text-[var(--color-on-surface-variant)]">Sin imagen disponible</p>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white border border-[var(--color-outline-variant)] rounded-xl overflow-hidden flex flex-col">
      {/* Card header */}
      <div className="px-6 py-4 border-b border-[var(--color-outline-variant)] bg-[var(--color-surface-container-low)] flex justify-between items-center">
        <h3 className="text-base font-semibold flex items-center gap-2 text-[var(--color-on-surface)]">
          <span className="material-symbols-outlined text-[var(--color-primary)]">image</span>
          Carga Original
        </h3>
        <div className="flex gap-2">
          <button
            type="button"
            className="p-1 hover:bg-[var(--color-surface-container-highest)] rounded transition-colors"
            aria-label="Ampliar imagen"
          >
            <span className="material-symbols-outlined text-[var(--color-secondary)] text-[20px]">zoom_in</span>
          </button>
          <button
            type="button"
            className="p-1 hover:bg-[var(--color-surface-container-highest)] rounded transition-colors"
            aria-label="Rotar imagen"
          >
            <span className="material-symbols-outlined text-[var(--color-secondary)] text-[20px]">rotate_right</span>
          </button>
        </div>
      </div>

      {/* Image area */}
      <div className="flex-1 bg-slate-100 p-6 flex items-center justify-center min-h-[400px] relative">
        {!loaded && (
          <Skeleton
            data-testid="voucher-skeleton"
            className="absolute inset-0 h-full w-full rounded-none"
          />
        )}
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={src}
          alt={alt}
          onLoad={() => setLoaded(true)}
          className="max-w-full shadow-2xl border-4 border-white rounded-sm"
          style={{ display: loaded ? "block" : "block" }}
        />
      </div>
    </div>
  );
}
