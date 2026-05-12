"use client";

/**
 * Topbar — R-36, 4.C.11.
 *
 * Displays the authenticated user's nombre and a logout button.
 * Client component because it uses useAuth().
 */

import { useAuth } from "@/lib/auth-context";
import { Button } from "@/components/ui/button";

export function Topbar() {
  const { user, logout } = useAuth();

  const handleLogout = () => {
    void logout();
  };

  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-[var(--color-outline-variant)] bg-white px-6">
      <div />
      <div className="flex items-center gap-4">
        {user && (
          <span className="text-sm font-medium text-[var(--color-on-surface-variant)]">
            {user.nombre}
          </span>
        )}
        <Button
          variant="secondary"
          size="sm"
          onClick={handleLogout}
          aria-label="Cerrar sesión"
        >
          Salir
        </Button>
      </div>
    </header>
  );
}
