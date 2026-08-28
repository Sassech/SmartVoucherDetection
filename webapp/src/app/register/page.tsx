"use client";

/**
 * Register page — R-80.
 * Split-panel layout via shared AuthLayout (mirrors login/page.tsx).
 * POST /web/auth/register → 201 redirects to /login?registered=1
 *                         → 409 shows "Email already registered"
 *                         → 422 shows validation error
 */

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { AuthLayout, Spinner } from "@/components/auth/AuthLayout";

interface ApiValidationError {
  loc: (string | number)[];
  msg: string;
  type: string;
}

export default function RegisterPage() {
  const router = useRouter();

  const [nombre, setNombre] = useState("");
  const [correo, setCorreo] = useState("");
  const [nombreOrg, setNombreOrg] = useState("");
  const [contrasena, setContrasena] = useState("");
  const [confirmar, setConfirmar] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // Client-side validation
  function validate(): string | null {
    if (!nombre.trim()) return "El nombre es requerido";
    if (!nombreOrg.trim()) return "El nombre de la organización es requerido";
    if (contrasena.length < 8) return "La contraseña debe tener al menos 8 caracteres";
    if (contrasena !== confirmar) return "Las contraseñas no coinciden";
    return null;
  }

  const handleSubmit = async (e: React.SyntheticEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);

    const clientError = validate();
    if (clientError) {
      setError(clientError);
      return;
    }

    setLoading(true);
    try {
      const res = await fetch("/api/web/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          nombre: nombre.trim(),
          correo,
          contrasena,
          nombre_organizacion: nombreOrg.trim(),
        }),
      });

      if (res.status === 201) {
        router.push("/login?registered=1");
        return;
      }

      if (res.status === 409) {
        setError("Email already registered. Try logging in instead.");
        return;
      }

      if (res.status === 422) {
        const body = (await res.json().catch(() => ({}))) as {
          detail?: ApiValidationError[] | string;
        };
        if (Array.isArray(body.detail) && body.detail.length > 0) {
          setError(body.detail[0].msg);
        } else if (typeof body.detail === "string") {
          setError(body.detail);
        } else {
          setError("Validation error. Please check your data.");
        }
        return;
      }

      // Other error
      const body = (await res.json().catch(() => ({}))) as { detail?: string };
      setError(body.detail ?? `Error ${res.status}. Please try again.`);
    } catch {
      setError("Network error. Please check your connection and try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthLayout
      title="Crear cuenta"
      subtitle="Portal de Validación · Registro de usuario"
      cardMaxWidth={420}
      afterForm={
        <>
          <p className="sv-a sv-a7" style={{ marginTop: "1.5rem", textAlign: "center", fontSize: "0.875rem", color: "#434654" }}>
            Already have an account?{" "}
            <Link href="/login" style={{ color: "#003d9b", fontWeight: 600, textDecoration: "none" }}>
              Log in
            </Link>
          </p>

          <p style={{ marginTop: "1rem", textAlign: "center", fontSize: "0.75rem", color: "#737685" }}>
            Acceso restringido a usuarios autorizados.{" "}
            <span style={{ color: "#003d9b", fontWeight: 500 }}>Uso corporativo exclusivo.</span>
          </p>
        </>
      }
    >
      <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }} noValidate>
        {/* Name */}
        <div className="sv-a sv-a2" style={{ display: "flex", flexDirection: "column", gap: "0.375rem" }}>
          <label htmlFor="nombre" style={{ fontSize: "0.875rem", fontWeight: 500, color: "#141b2b" }}>
            Nombre completo
          </label>
          <Input
            id="nombre"
            type="text"
            autoComplete="name"
            required
            value={nombre}
            onChange={(e) => setNombre(e.target.value)}
            placeholder="Juan Pérez"
            aria-describedby={error ? "register-error" : undefined}
            className="sv-input"
          />
        </div>

        {/* Organización */}
        <div className="sv-a sv-a3" style={{ display: "flex", flexDirection: "column", gap: "0.375rem" }}>
          <label htmlFor="nombre-org" style={{ fontSize: "0.875rem", fontWeight: 500, color: "#141b2b" }}>
            Nombre de la organización
          </label>
          <Input
            id="nombre-org"
            type="text"
            autoComplete="organization"
            required
            value={nombreOrg}
            onChange={(e) => setNombreOrg(e.target.value)}
            placeholder="Mi Empresa S.A."
            aria-describedby={error ? "register-error" : undefined}
            className="sv-input"
          />
        </div>

        {/* Email */}
        <div className="sv-a sv-a4" style={{ display: "flex", flexDirection: "column", gap: "0.375rem" }}>
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
            aria-describedby={error ? "register-error" : undefined}
            className="sv-input"
          />
        </div>

        {/* Password */}
        <div className="sv-a sv-a4" style={{ display: "flex", flexDirection: "column", gap: "0.375rem" }}>
          <label htmlFor="contrasena" style={{ fontSize: "0.875rem", fontWeight: 500, color: "#141b2b" }}>
            Contraseña
          </label>
          <Input
            id="contrasena"
            type="password"
            autoComplete="new-password"
            required
            minLength={8}
            value={contrasena}
            onChange={(e) => setContrasena(e.target.value)}
            placeholder="Mínimo 8 caracteres"
            aria-describedby={error ? "register-error" : undefined}
            className="sv-input"
          />
        </div>

        {/* Confirm password */}
        <div className="sv-a sv-a5" style={{ display: "flex", flexDirection: "column", gap: "0.375rem" }}>
          <label htmlFor="confirmar" style={{ fontSize: "0.875rem", fontWeight: 500, color: "#141b2b" }}>
            Confirmar contraseña
          </label>
          <Input
            id="confirmar"
            type="password"
            autoComplete="new-password"
            required
            value={confirmar}
            onChange={(e) => setConfirmar(e.target.value)}
            placeholder="••••••••"
            aria-describedby={error ? "register-error" : undefined}
            className="sv-input"
          />
        </div>

        {/* Inline error */}
        {error && (
          <div
            id="register-error"
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
        <div className={cn("sv-a sv-a6", error ? "" : "mt-1")}>
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
                Creando cuenta…
              </span>
            ) : "Crear cuenta"}
          </Button>
        </div>
      </form>
    </AuthLayout>
  );
}
