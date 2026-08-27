"use client";

/**
 * Login page — 4.C.13, S-19, S-01.
 * Split layout via shared AuthLayout (left branding panel + right form card).
 * R-80: shows success banner when ?registered=1 is present.
 */

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { AuthLayout, Spinner } from "@/components/auth/AuthLayout";

function LoginForm() {
  const { login } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const registered = searchParams.get("registered") === "1";

  const [correo, setCorreo] = useState("");
  const [contrasena, setContrasena] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.SyntheticEvent<HTMLFormElement>) => {
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
    <AuthLayout
      title="Iniciar sesión"
      subtitle="Portal de Validación · Acceso autorizado"
      cardMaxWidth={400}
      beforeForm={
        registered && (
          <output
            style={{
              display: "flex", alignItems: "flex-start", gap: 10,
              padding: "12px 16px", borderRadius: 12, marginBottom: "1.25rem",
              background: "#f0fdf4", border: "1px solid #bbf7d0",
            }}
          >
            <span aria-hidden="true" style={{ fontSize: "1rem", lineHeight: 1, marginTop: 1 }}>✅</span>
            <p style={{ margin: 0, fontSize: "0.875rem", fontWeight: 500, color: "#166534" }}>
              Account created successfully. Please log in.
            </p>
          </output>
        )
      }
      afterForm={
        <p className="sv-a sv-a5" style={{ marginTop: "2rem", textAlign: "center", fontSize: "0.75rem", color: "#737685" }}>
          Acceso restringido a usuarios autorizados.{" "}
          <span style={{ color: "#003d9b", fontWeight: 500 }}>Uso corporativo exclusivo.</span>
        </p>
      }
    >
      <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }} noValidate>
        {/* Email */}
        <div className="sv-a sv-a2" style={{ display: "flex", flexDirection: "column", gap: "0.375rem" }}>
          <label htmlFor="correo" style={{ fontSize: "0.875rem", fontWeight: 500, color: "#141b2b" }}>
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
            className="sv-input"
          />
        </div>

        {/* Contraseña */}
        <div className="sv-a sv-a3" style={{ display: "flex", flexDirection: "column", gap: "0.375rem" }}>
          <label htmlFor="contrasena" style={{ fontSize: "0.875rem", fontWeight: 500, color: "#141b2b" }}>
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
            className="sv-input"
          />
        </div>

        {/* Error */}
        {error && (
          <div
            id="login-error"
            role="alert"
            style={{
              display: "flex", alignItems: "flex-start", gap: 10,
              padding: "12px 16px", borderRadius: 12,
              background: "#fff4f4", border: "1px solid #ffdad6",
            }}
          >
            <span aria-hidden="true" style={{ fontSize: "1rem", lineHeight: 1, marginTop: 1 }}>⚠️</span>
            <p style={{ margin: 0, fontSize: "0.875rem", fontWeight: 500, color: "#93000a" }}>
              {error}
            </p>
          </div>
        )}

        {/* Submit */}
        <div className={cn("sv-a sv-a4", error ? "" : "mt-1")}>
          <Button
            type="submit"
            variant="primary"
            size="lg"
            style={{ height: "3rem", borderRadius: 12, fontSize: "1rem", fontWeight: 600, width: "100%", display: "flex" }}
            disabled={loading}
            aria-busy={loading}
          >
            {loading ? (
              <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <Spinner />
                Ingresando…
              </span>
            ) : "Ingresar"}
          </Button>
        </div>
      </form>
    </AuthLayout>
  );
}

// Suspense boundary required because LoginForm uses useSearchParams()
export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <LoginForm />
    </Suspense>
  );
}
