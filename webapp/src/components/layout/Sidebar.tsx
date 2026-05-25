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
  { label: "Panel de Control", href: "/", icon: "dashboard" },
  { label: "Subir Comprobantes", href: "/subir", icon: "cloud_upload" },
  { label: "Historial", href: "/historial", icon: "history" },
  { label: "Cola de Revisión", href: "/revision", icon: "fact_check" },
  { label: "Mi Perfil", href: "/profile", icon: "manage_accounts" },
  { label: "Configuración", href: "/configuracion", icon: "settings" },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside
      className="flex h-full w-64 shrink-0 flex-col border-r border-slate-200 bg-[#F9FAFB] z-30"
      aria-label="Navegación principal"
    >
      {/* Brand */}
      <div className="px-6 py-8 border-b border-slate-200">
        <span className="text-xl font-black text-blue-700 tracking-tight">
          AutoDeposit
        </span>
        <p className="text-[10px] text-slate-500 uppercase tracking-widest mt-1">
          Terminal de Administración
        </p>
      </div>

      {/* Nav links */}
      <nav className="flex-1 px-4 space-y-1 py-4">
        {NAV_ITEMS.map(({ label, href, icon }) => {
          const isActive =
            href === "/" ? pathname === "/" : pathname.startsWith(href);

          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all text-sm font-medium",
                isActive
                  ? "bg-blue-50 text-blue-700 border-r-4 border-blue-700"
                  : "text-slate-500 hover:text-slate-900 hover:bg-slate-100",
              )}
              aria-current={isActive ? "page" : undefined}
            >
              <span
                className="material-symbols-outlined text-[20px]"
                aria-hidden="true"
                style={{
                  fontVariationSettings: isActive
                    ? "'FILL' 1, 'wght' 400, 'GRAD' 0, 'opsz' 24"
                    : "'FILL' 0, 'wght' 400, 'GRAD' 0, 'opsz' 24",
                }}
              >
                {icon}
              </span>
              {label}
            </Link>
          );
        })}
      </nav>

    </aside>
  );
}
