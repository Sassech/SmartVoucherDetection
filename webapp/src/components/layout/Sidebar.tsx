"use client";

/**
 * Sidebar navigation — R-36, 4.C.10.
 *
 * Client component so it can read the current pathname for active state.
 * Links: Dashboard (/), Historial (/historial), Revisión (/revision).
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

interface NavItem {
  label: string;
  href: string;
  icon: string;
}

const NAV_ITEMS: NavItem[] = [
  { label: "Dashboard", href: "/", icon: "▤" },
  { label: "Historial", href: "/historial", icon: "☰" },
  { label: "Revisión", href: "/revision", icon: "✦" },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside
      className="flex h-full w-56 shrink-0 flex-col border-r border-[var(--color-outline-variant)] bg-[var(--color-surface-container-low)] py-6"
      aria-label="Navegación principal"
    >
      {/* Brand */}
      <div className="mb-8 px-5">
        <span className="text-base font-semibold tracking-tight text-[var(--color-primary)]">
          SmartVoucher
        </span>
      </div>

      {/* Nav links */}
      <nav className="flex flex-col gap-1 px-3">
        {NAV_ITEMS.map(({ label, href, icon }) => {
          const isActive =
            href === "/" ? pathname === "/" : pathname.startsWith(href);

          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-3 rounded-[var(--radius-md)] px-3 py-2 text-sm font-medium transition-colors",
                isActive
                  ? "bg-[var(--color-primary-fixed)] text-[var(--color-on-primary-fixed-variant)]"
                  : "text-[var(--color-on-surface-variant)] hover:bg-[var(--color-surface-container)] hover:text-[var(--color-on-surface)]",
              )}
              aria-current={isActive ? "page" : undefined}
            >
              <span aria-hidden="true">{icon}</span>
              {label}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
