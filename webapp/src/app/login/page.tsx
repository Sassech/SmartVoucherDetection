"use client";

/**
 * Login page — 4.C.13, S-19, S-01.
 *
 * Public page (middleware skips /login).
 * Form: correo + contrasena → calls useAuth().login() → redirects to / on success.
 */

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function LoginPage() {
  const { login } = useAuth();
  const router = useRouter();

  const [correo, setCorreo] = useState("");
  const [contrasena, setContrasena] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      await login(correo, contrasena);
      router.push("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al iniciar sesión");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-[var(--color-background)] p-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>Iniciar sesión</CardTitle>
          <p className="text-sm text-[var(--color-on-surface-variant)]">
            SmartVoucher — Portal de Validación
          </p>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="flex flex-col gap-4" noValidate>
            <div className="flex flex-col gap-1.5">
              <label
                htmlFor="correo"
                className="text-sm font-medium text-[var(--color-on-surface)]"
              >
                Correo electrónico
              </label>
              <Input
                id="correo"
                type="email"
                autoComplete="email"
                required
                value={correo}
                onChange={(e) => setCorreo(e.target.value)}
                placeholder="usuario@empresa.com"
                aria-describedby={error ? "login-error" : undefined}
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label
                htmlFor="contrasena"
                className="text-sm font-medium text-[var(--color-on-surface)]"
              >
                Contraseña
              </label>
              <Input
                id="contrasena"
                type="password"
                autoComplete="current-password"
                required
                value={contrasena}
                onChange={(e) => setContrasena(e.target.value)}
                placeholder="••••••••"
                aria-describedby={error ? "login-error" : undefined}
              />
            </div>

            {error && (
              <p
                id="login-error"
                role="alert"
                className="text-sm text-[var(--color-error)]"
              >
                {error}
              </p>
            )}

            <Button
              type="submit"
              variant="primary"
              className="w-full"
              disabled={loading}
              aria-busy={loading}
            >
              {loading ? "Ingresando…" : "Ingresar"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
