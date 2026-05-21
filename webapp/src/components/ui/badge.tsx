import * as React from "react";
import { cn } from "@/lib/utils";

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: "default" | "valido" | "duplicado" | "sospechoso" | "en_revision" | "procesando" | "recibido" | "error";
}

const variantClasses: Record<NonNullable<BadgeProps["variant"]>, string> = {
  default: "bg-[var(--color-surface-container)] text-[var(--color-on-surface-variant)]",
  valido: "bg-green-100 text-green-700",
  duplicado: "bg-red-100 text-red-700",
  sospechoso: "bg-orange-100 text-orange-700",
  en_revision: "bg-yellow-100 text-yellow-700",
  procesando: "bg-blue-100 text-blue-700",
  recibido: "bg-[var(--color-surface-container)] text-[var(--color-on-surface-variant)]",
  error: "bg-red-50 text-red-600",
};

const Badge = React.forwardRef<HTMLSpanElement, BadgeProps>(
  ({ className, variant = "default", children, ...props }, ref) => {
    return (
      <span
        ref={ref}
        className={cn(
          "inline-flex items-center rounded-[var(--radius-DEFAULT)] px-2 py-0.5 text-xs font-medium tracking-wide",
          variantClasses[variant],
          className,
        )}
        {...props}
      >
        {children}
      </span>
    );
  },
);
Badge.displayName = "Badge";

export { Badge };
