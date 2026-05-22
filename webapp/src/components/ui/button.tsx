import * as React from "react";
import { cn } from "@/lib/utils";

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "ghost" | "destructive";
  size?: "sm" | "md" | "lg";
}

// Estilos inline para variantes — evita dependencia de Tailwind para colores con var()
// que no se generan correctamente en builds standalone de Next.js
const variantStyles: Record<NonNullable<ButtonProps["variant"]>, React.CSSProperties> = {
  primary:  { backgroundColor: "var(--color-primary, #003d9b)", color: "var(--color-on-primary, #ffffff)" },
  secondary: { backgroundColor: "white", border: "1px solid var(--color-outline-variant, #c3c6d6)", color: "var(--color-on-surface, #141b2b)" },
  ghost:    { backgroundColor: "transparent", color: "var(--color-primary, #003d9b)" },
  destructive: { backgroundColor: "var(--color-error, #ba1a1a)", color: "var(--color-on-error, #ffffff)" },
};

const variantClasses: Record<NonNullable<ButtonProps["variant"]>, string> = {
  primary:     "hover:brightness-95 active:brightness-90",
  secondary:   "hover:brightness-95",
  ghost:       "",
  destructive: "hover:brightness-95",
};

const sizeClasses: Record<NonNullable<ButtonProps["size"]>, string> = {
  sm: "px-3 py-1.5 text-sm",
  md: "px-4 py-2 text-sm",
  lg: "px-6 py-3 text-base",
};

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  (
    { className, variant = "primary", size = "md", disabled, style, children, ...props },
    ref,
  ) => {
    return (
      <button
        ref={ref}
        disabled={disabled}
        style={{
          borderRadius: "var(--radius-DEFAULT, 0.25rem)",
          ...variantStyles[variant],
          ...style,  // caller overrides last — pero backgroundColor/color ya están en variantStyles
        }}
        className={cn(
          "inline-flex items-center justify-center gap-2 font-medium transition-all focus-visible:outline-none disabled:pointer-events-none disabled:opacity-50",
          variantClasses[variant],
          sizeClasses[size],
          className,
        )}
        {...props}
      >
        {children}
      </button>
    );
  },
);
Button.displayName = "Button";

export { Button };
