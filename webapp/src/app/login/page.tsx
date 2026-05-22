"use client";

/**
 * Login page — 4.C.13, S-19, S-01.
 *
 * Public page (middleware skips /login).
 * Form: correo + contrasena → calls useAuth().login() → redirects to / on success.
 *
 * Layout: split — left branding panel (hidden on mobile) + right form panel.
 */

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

/* ─── Keyframe animation injected via a <style> tag ─────────────────────── */
const ANIMATION_CSS = `
  @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');

  @keyframes svd-fade-up {
    from { opacity: 0; transform: translateY(18px); }
    to   { opacity: 1; transform: translateY(0);    }
  }
  .svd-animate {
    animation: svd-fade-up 0.45s cubic-bezier(0.22, 1, 0.36, 1) both;
  }
  .svd-animate-delay-1 { animation-delay: 0.05s; }
  .svd-animate-delay-2 { animation-delay: 0.10s; }
  .svd-animate-delay-3 { animation-delay: 0.15s; }
  .svd-animate-delay-4 { animation-delay: 0.20s; }
  .svd-animate-delay-5 { animation-delay: 0.25s; }

  .svd-font { font-family: 'Plus Jakarta Sans', ui-sans-serif, system-ui, sans-serif; }

  /* Custom focus ring override for inputs inside this page */
  .svd-input:focus-visible {
    border-color: #003d9b !important;
    ring-color: #dae2ff !important;
  }
`;

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
    <>
      {/* Inject font + keyframes without an external package */}
      <style dangerouslySetInnerHTML={{ __html: ANIMATION_CSS }} />

      <div className="svd-font flex min-h-screen bg-[#f9f9ff]">

        {/* ── LEFT — Branding panel (hidden on mobile) ────────────────────── */}
        <div
          className="hidden lg:flex lg:w-[52%] xl:w-[55%] flex-col justify-between relative overflow-hidden"
          style={{ background: "linear-gradient(145deg, #001848 0%, #003d9b 55%, #0052cc 100%)" }}
          aria-hidden="true"
        >
          {/* Geometric background shapes */}
          <svg
            className="absolute inset-0 w-full h-full"
            viewBox="0 0 800 900"
            preserveAspectRatio="xMidYMid slice"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
          >
            {/* Large circle top-right */}
            <circle cx="720" cy="-60" r="340" fill="white" fillOpacity="0.04" />
            {/* Medium circle bottom-left */}
            <circle cx="-80" cy="920" r="420" fill="white" fillOpacity="0.035" />
            {/* Diagonal accent lines */}
            <line x1="0" y1="650" x2="800" y2="200" stroke="white" strokeOpacity="0.06" strokeWidth="1.5" />
            <line x1="0" y1="700" x2="800" y2="250" stroke="white" strokeOpacity="0.04" strokeWidth="1" />
            <line x1="0" y1="750" x2="800" y2="300" stroke="white" strokeOpacity="0.03" strokeWidth="1" />
            {/* Small geometric accent — top-left */}
            <rect x="40" y="40" width="60" height="60" rx="12" fill="white" fillOpacity="0.05" transform="rotate(15 40 40)" />
            <rect x="80" y="55" width="30" height="30" rx="6" fill="white" fillOpacity="0.07" transform="rotate(15 80 55)" />
            {/* Hexagon-ish accent bottom-right */}
            <polygon
              points="680,780 720,756 760,780 760,828 720,852 680,828"
              fill="white"
              fillOpacity="0.04"
            />
            <polygon
              points="700,795 720,783 740,795 740,819 720,831 700,819"
              fill="white"
              fillOpacity="0.06"
            />
            {/* Subtle grid dots */}
            {[...Array(6)].map((_, row) =>
              [...Array(4)].map((_, col) => (
                <circle
                  key={`dot-${row}-${col}`}
                  cx={120 + col * 160}
                  cy={200 + row * 120}
                  r="1.5"
                  fill="white"
                  fillOpacity="0.15"
                />
              ))
            )}
          </svg>

          {/* Content over the background */}
          <div className="relative z-10 flex flex-col h-full px-12 py-12 justify-between">
            {/* Logo area */}
            <div className="flex items-center gap-3">
              {/* Inline SVG shield icon */}
              <svg width="36" height="36" viewBox="0 0 36 36" fill="none" xmlns="http://www.w3.org/2000/svg">
                <rect width="36" height="36" rx="9" fill="white" fillOpacity="0.15" />
                <path
                  d="M18 6L7 10.5V18.75C7 24.3 12 29.4 18 31C24 29.4 29 24.3 29 18.75V10.5L18 6Z"
                  fill="white"
                  fillOpacity="0.9"
                />
                <path
                  d="M14 18.5L16.5 21L22 15"
                  stroke="#003d9b"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
              <span className="text-white text-xl font-800 tracking-tight" style={{ fontWeight: 800 }}>
                SmartVoucher
              </span>
            </div>

            {/* Center content */}
            <div className="flex flex-col gap-6 max-w-sm">
              <div className="flex flex-col gap-3">
                <span className="inline-flex w-fit items-center gap-1.5 rounded-full px-3 py-1 text-xs font-600 tracking-wide"
                  style={{
                    background: "rgba(255,255,255,0.12)",
                    color: "#c4d2ff",
                    fontWeight: 600,
                    letterSpacing: "0.06em",
                  }}
                >
                  <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                    <circle cx="5" cy="5" r="4" fill="#4ade80" />
                    <circle cx="5" cy="5" r="2" fill="#86efac" />
                  </svg>
                  Sistema activo · México
                </span>

                <h1 className="text-white text-4xl leading-tight" style={{ fontWeight: 800 }}>
                  Verificación inteligente de comprobantes bancarios
                </h1>
              </div>

              <p className="text-[#c4d2ff] text-base leading-relaxed" style={{ fontWeight: 400 }}>
                Validá CFDIs, transferencias y estados de cuenta en segundos.
                Tecnología bancaria al servicio de tu equipo.
              </p>

              {/* Feature pills */}
              <div className="flex flex-col gap-2.5 mt-2">
                {[
                  { icon: "🔒", text: "Validación en tiempo real" },
                  { icon: "📄", text: "Soporte CFDI 4.0 y XML SAT" },
                  { icon: "⚡", text: "Resultados instantáneos" },
                ].map(({ icon, text }) => (
                  <div
                    key={text}
                    className="flex items-center gap-3 rounded-xl px-4 py-3"
                    style={{ background: "rgba(255,255,255,0.08)" }}
                  >
                    <span className="text-base leading-none">{icon}</span>
                    <span className="text-sm text-[#dae2ff]" style={{ fontWeight: 500 }}>
                      {text}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            {/* Footer */}
            <p className="text-[#7895cc] text-xs" style={{ fontWeight: 400 }}>
              © 2025 SmartVoucher · Uso exclusivo corporativo
            </p>
          </div>
        </div>

        {/* ── RIGHT — Form panel ───────────────────────────────────────────── */}
        <div className="flex flex-1 flex-col items-center justify-center px-6 py-12 sm:px-10 lg:px-16">
          {/* Mobile-only logo */}
          <div className="flex lg:hidden items-center gap-2 mb-10">
            <svg width="28" height="28" viewBox="0 0 36 36" fill="none" xmlns="http://www.w3.org/2000/svg">
              <rect width="36" height="36" rx="9" fill="#003d9b" />
              <path
                d="M18 6L7 10.5V18.75C7 24.3 12 29.4 18 31C24 29.4 29 24.3 29 18.75V10.5L18 6Z"
                fill="white"
                fillOpacity="0.9"
              />
              <path
                d="M14 18.5L16.5 21L22 15"
                stroke="#003d9b"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
            <span className="text-[#003d9b] text-lg" style={{ fontWeight: 800 }}>
              SmartVoucher
            </span>
          </div>

          {/* Form card */}
          <div className="w-full max-w-[400px]">

            {/* Header */}
            <div className="svd-animate svd-animate-delay-1 mb-8">
              <h2
                className="text-[#141b2b] text-2xl leading-tight mb-1.5"
                style={{ fontWeight: 700 }}
              >
                Iniciar sesión
              </h2>
              <p className="text-sm text-[#434654]">
                Portal de Validación · Acceso autorizado
              </p>
            </div>

            {/* Form */}
            <form
              onSubmit={handleSubmit}
              className="flex flex-col gap-5"
              noValidate
            >
              {/* Email */}
              <div className="svd-animate svd-animate-delay-2 flex flex-col gap-1.5">
                <label
                  htmlFor="correo"
                  className="text-sm text-[#141b2b]"
                  style={{ fontWeight: 500 }}
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
                  className="h-11 border-[#c3c6d6] text-base"
                />
              </div>

              {/* Password */}
              <div className="svd-animate svd-animate-delay-3 flex flex-col gap-1.5">
                <label
                  htmlFor="contrasena"
                  className="text-sm text-[#141b2b]"
                  style={{ fontWeight: 500 }}
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
                  className="h-11 border-[#c3c6d6] text-base"
                />
              </div>

              {/* Error */}
              {error && (
                <div
                  id="login-error"
                  role="alert"
                  className="flex items-start gap-2.5 rounded-xl border border-[#ffdad6] bg-[#fff4f4] px-4 py-3"
                >
                  <span className="text-base leading-none mt-px" aria-hidden="true">⚠️</span>
                  <p className="text-sm text-[#93000a]" style={{ fontWeight: 500 }}>
                    {error}
                  </p>
                </div>
              )}

              {/* Submit */}
              <div className={cn("svd-animate svd-animate-delay-4", error ? "" : "mt-1")}>
                <Button
                  type="submit"
                  variant="primary"
                  size="lg"
                  className="w-full h-12 text-base rounded-xl"
                  disabled={loading}
                  aria-busy={loading}
                >
                  {loading ? (
                    <span className="flex items-center gap-2">
                      <svg
                        className="animate-spin"
                        width="16"
                        height="16"
                        viewBox="0 0 16 16"
                        fill="none"
                        xmlns="http://www.w3.org/2000/svg"
                        aria-hidden="true"
                      >
                        <circle
                          cx="8" cy="8" r="6"
                          stroke="currentColor"
                          strokeOpacity="0.25"
                          strokeWidth="2"
                        />
                        <path
                          d="M14 8A6 6 0 0 0 8 2"
                          stroke="currentColor"
                          strokeWidth="2"
                          strokeLinecap="round"
                        />
                      </svg>
                      Ingresando…
                    </span>
                  ) : (
                    "Ingresar"
                  )}
                </Button>
              </div>
            </form>

            {/* Footer note */}
            <p className="svd-animate svd-animate-delay-5 mt-8 text-center text-xs text-[#737685]">
              Acceso restringido a usuarios autorizados.{" "}
              <span className="text-[#003d9b]" style={{ fontWeight: 500 }}>
                Uso corporativo exclusivo.
              </span>
            </p>
          </div>
        </div>
      </div>
    </>
  );
}
