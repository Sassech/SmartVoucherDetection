"use client";

/**
 * Topbar — R-36, 4.C.11.
 *
 * Displays the authenticated user's nombre and a logout button.
 * Client component because it uses useAuth().
 */

import { useAuth } from "@/lib/auth-context";

export function Topbar() {
  const { user, logout } = useAuth();

  const handleLogout = () => {
    void logout();
  };

  const initials = user?.nombre
    ? user.nombre.slice(0, 2).toUpperCase()
    : "AD";

  return (
    <header className="flex h-16 shrink-0 items-center justify-between border-b border-slate-200 bg-white px-6 sticky top-0 z-40">
      {/* Left: branding */}
      <div className="flex items-center gap-4">
        <span className="text-lg font-bold text-slate-900 tracking-tight">
          Reconocimiento de Depósitos
        </span>
      </div>

      {/* Right: actions + user */}
      <div className="flex items-center gap-2">
        <button
          type="button"
          className="p-2 hover:bg-slate-50 rounded-full transition-colors"
          aria-label="Notificaciones"
        >
          <span className="material-symbols-outlined text-slate-600 text-[22px]">
            notifications
          </span>
        </button>
        <button
          type="button"
          className="p-2 hover:bg-slate-50 rounded-full transition-colors"
          aria-label="Ayuda"
        >
          <span className="material-symbols-outlined text-slate-600 text-[22px]">
            help_outline
          </span>
        </button>

        {/* Divider */}
        <div className="h-6 w-px bg-slate-200 mx-2" />

        {/* User */}
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-full bg-[var(--color-primary-fixed)] flex items-center justify-center">
            <span className="text-xs font-bold text-[var(--color-on-primary-fixed)]">{initials}</span>
          </div>
          {user && (
            <span className="text-sm font-medium text-slate-900 hidden sm:block">
              {user.nombre}
            </span>
          )}
        </div>

        {/* Logout */}
        <button
          type="button"
          onClick={handleLogout}
          className="ml-2 flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50 transition-colors"
          aria-label="Cerrar sesión"
        >
          <span className="material-symbols-outlined text-[16px]">logout</span>
          Salir
        </button>
      </div>
    </header>
  );
}
