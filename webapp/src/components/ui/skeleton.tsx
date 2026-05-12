import { cn } from "@/lib/utils";

interface SkeletonProps extends React.HTMLAttributes<HTMLDivElement> {}

function Skeleton({ className, ...props }: SkeletonProps) {
  return (
    <div
      className={cn(
        "animate-pulse rounded-[var(--radius-DEFAULT)] bg-[var(--color-surface-container-high)]",
        className,
      )}
      {...props}
    />
  );
}

export { Skeleton };
