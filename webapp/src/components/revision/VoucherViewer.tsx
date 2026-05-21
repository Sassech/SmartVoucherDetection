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
      <div className="flex items-center justify-center rounded-[var(--radius-lg)] border border-[var(--color-outline-variant)] bg-[var(--color-surface-container-low)] p-10">
        <p className="text-sm text-[var(--color-on-surface-variant)]">Sin imagen disponible</p>
      </div>
    );
  }

  return (
    <div className="relative rounded-[var(--radius-lg)] border border-[var(--color-outline-variant)] bg-[var(--color-surface)] overflow-hidden">
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
        className="w-full object-contain"
        style={{ display: loaded ? "block" : "block" }}
      />
    </div>
  );
}
