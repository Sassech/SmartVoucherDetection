import * as React from "react";
import { cn } from "@/lib/utils";

export type InputProps = React.InputHTMLAttributes<HTMLInputElement>;

const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, type, ...props }, ref) => {
    return (
      <input
        type={type}
        ref={ref}
        style={{
          display: "flex",
          height: "2.5rem",
          width: "100%",
          borderRadius: "var(--radius-DEFAULT, 0.25rem)",
          border: "1px solid #c3c6d6",
          backgroundColor: "white",
          padding: "0.5rem 0.75rem",
          fontSize: "0.875rem",
          color: "var(--color-on-surface, #141b2b)",
          transition: "box-shadow 0.15s, border-color 0.15s",
          outline: "none",
        }}
        onFocus={e => {
          e.currentTarget.style.borderColor = "#003d9b";
          e.currentTarget.style.boxShadow = "0 0 0 3px rgba(0,61,155,0.15)";
        }}
        onBlur={e => {
          e.currentTarget.style.borderColor = "#c3c6d6";
          e.currentTarget.style.boxShadow = "none";
        }}
        className={cn(
          "disabled:cursor-not-allowed disabled:opacity-50",
          className,
        )}
        {...props}
      />
    );
  },
);
Input.displayName = "Input";

export { Input };
