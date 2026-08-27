/**
 * AuthLayout — shared split-panel chrome for /login and /register.
 *
 * Extracts the duplicated branding panel, CSS, ShieldIcon/Spinner and card
 * chrome that were copy-pasted between login/page.tsx and register/page.tsx
 * (sonar duplicated_lines_density: login 61.6%, register 47.8%). Only the
 * form fields, banners, and footer links stay owned by each page via the
 * `beforeForm` / `children` / `afterForm` slots — visual output is unchanged.
 */

import type { ReactNode } from "react";

const CSS = `
  @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');

  .sv-root { display: flex; min-height: 100vh; font-family: 'Plus Jakarta Sans', ui-sans-serif, system-ui, sans-serif; }

  /* Left panel — hidden on mobile */
  .sv-left {
    display: none;
    position: relative;
    overflow: hidden;
    flex-direction: column;
    justify-content: space-between;
    padding: 3rem;
    background: linear-gradient(145deg, #001848 0%, #003d9b 55%, #0052cc 100%);
  }

  /* Right panel — full width on mobile, 45% on desktop */
  .sv-right {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 3rem 2rem;
    background: #f9f9ff;
  }

  /* Breakpoint 1024px */
  @media (min-width: 1024px) {
    .sv-left  { display: flex; width: 52%; flex-shrink: 0; }
    .sv-right { flex: 1; }
    .sv-mobile-logo { display: none !important; }
  }

  /* Entry animation */
  @keyframes sv-up {
    from { opacity: 0; transform: translateY(16px); }
    to   { opacity: 1; transform: translateY(0); }
  }
  .sv-a  { animation: sv-up 0.4s cubic-bezier(0.22,1,0.36,1) both; }
  .sv-a1 { animation-delay: 0.04s; }
  .sv-a2 { animation-delay: 0.10s; }
  .sv-a3 { animation-delay: 0.16s; }
  .sv-a4 { animation-delay: 0.22s; }
  .sv-a5 { animation-delay: 0.28s; }
  .sv-a6 { animation-delay: 0.34s; }
  .sv-a7 { animation-delay: 0.40s; }

  /* Input overrides */
  .sv-input { height: 2.75rem; font-size: 1rem; border-color: #c3c6d6; }
  .sv-input:focus-visible { border-color: #003d9b; outline: none; box-shadow: 0 0 0 3px rgba(0,61,155,0.15); }

  /* Pill */
  .sv-pill {
    display: inline-flex; align-items: center; gap: 6px;
    padding: 4px 12px; border-radius: 99px; font-size: 0.72rem;
    font-weight: 600; letter-spacing: 0.06em;
    background: rgba(255,255,255,0.12); color: #c4d2ff;
  }

  /* Feature row */
  .sv-feat {
    display: flex; align-items: center; gap: 12px;
    padding: 12px 16px; border-radius: 14px;
    background: rgba(255,255,255,0.08);
    font-size: 0.875rem; font-weight: 500; color: #dae2ff;
  }
`;

const FEATURES = [
  { icon: "🔒", text: "Validación en tiempo real" },
  { icon: "📄", text: "Soporte CFDI 4.0 y XML SAT" },
  { icon: "⚡", text: "Resultados instantáneos" },
] as const;

interface ShieldIconProps {
  size?: number;
  dark?: boolean;
}

/** Shield SVG shared by branding panel and mobile header. */
export function ShieldIcon({ size = 36, dark = false }: Readonly<ShieldIconProps>) {
  return (
    <svg width={size} height={size} viewBox="0 0 36 36" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect width="36" height="36" rx="9" fill={dark ? "#003d9b" : "rgba(255,255,255,0.15)"} />
      <path
        d="M18 7L8 11v8c0 5.25 4.5 10 10 11.5C23.5 29 28 24.25 28 19v-8L18 7Z"
        fill="white"
        fillOpacity="0.9"
      />
      <path d="M14 18.5l2.5 2.5 5.5-6" stroke="#003d9b" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/** Inline spinner used by submit buttons while a request is in flight. */
export function Spinner() {
  return (
    <svg
      style={{ animation: "spin 1s linear infinite" }}
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="none"
      aria-hidden="true"
    >
      <circle cx="8" cy="8" r="6" stroke="currentColor" strokeOpacity="0.25" strokeWidth="2" />
      <path d="M14 8A6 6 0 0 0 8 2" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

export interface AuthLayoutProps {
  /** Card heading, e.g. "Iniciar sesión" or "Crear cuenta". */
  title: string;
  /** Card subheading under the title. */
  subtitle: string;
  /** The `<form>` element (and its animated field groups) owned by the page. */
  children: ReactNode;
  /** Max width of the form card in px. Login uses 400, register 420. */
  cardMaxWidth?: number;
  /** Optional content rendered between the header and the form (e.g. success banner). */
  beforeForm?: ReactNode;
  /** Optional content rendered after the form (e.g. "Already have an account?" link, footer note). */
  afterForm?: ReactNode;
}

/**
 * Shared split-panel layout for /login and /register.
 * Left: branding panel (hidden on mobile). Right: form card with header + slots.
 */
export function AuthLayout({
  title,
  subtitle,
  children,
  cardMaxWidth = 400,
  beforeForm,
  afterForm,
}: Readonly<AuthLayoutProps>) {
  return (
    <>
      <style dangerouslySetInnerHTML={{ __html: CSS }} />

      <div className="sv-root">
        {/* ── LEFT PANEL — Branding ──────────────────────────────── */}
        <div className="sv-left" aria-hidden="true">
          {/* Background geometric shapes */}
          <svg
            style={{ position: "absolute", inset: 0, width: "100%", height: "100%", pointerEvents: "none" }}
            viewBox="0 0 600 900"
            preserveAspectRatio="xMidYMid slice"
            fill="none"
          >
            <circle cx="560" cy="-40" r="280" fill="white" fillOpacity="0.04" />
            <circle cx="-60" cy="900" r="340" fill="white" fillOpacity="0.035" />
            <line x1="0" y1="600" x2="600" y2="180" stroke="white" strokeOpacity="0.06" strokeWidth="1.5" />
            <line x1="0" y1="660" x2="600" y2="240" stroke="white" strokeOpacity="0.035" strokeWidth="1" />
            <rect x="30" y="30" width="50" height="50" rx="10" fill="white" fillOpacity="0.05" transform="rotate(12 30 30)" />
            <polygon points="510,760 545,740 580,760 580,800 545,820 510,800" fill="white" fillOpacity="0.05" />
            {([0, 1, 2, 3, 4] as const).map((row) =>
              ([0, 1, 2] as const).map((col) => (
                <circle key={`${row}-${col}`} cx={100 + col * 180} cy={200 + row * 130} r="1.5" fill="white" fillOpacity="0.18" />
              )),
            )}
          </svg>

          {/* Logo */}
          <div style={{ position: "relative", zIndex: 1, display: "flex", alignItems: "center", gap: 12 }}>
            <ShieldIcon />
            <span style={{ color: "white", fontSize: "1.25rem", fontWeight: 800, letterSpacing: "-0.02em" }}>
              SmartVoucher
            </span>
          </div>

          {/* Center content */}
          <div style={{ position: "relative", zIndex: 1, display: "flex", flexDirection: "column", gap: 24, maxWidth: 380 }}>
            <div className="sv-pill">
              <svg width="8" height="8" viewBox="0 0 8 8">
                <circle cx="4" cy="4" r="3.5" fill="#4ade80" />
              </svg>
              Sistema activo · México
            </div>

            <h1 style={{ color: "white", fontSize: "2.25rem", fontWeight: 800, lineHeight: 1.2, letterSpacing: "-0.02em", margin: 0 }}>
              Verificación inteligente de comprobantes bancarios
            </h1>

            <p style={{ color: "#c4d2ff", fontSize: "1rem", lineHeight: 1.6, margin: 0 }}>
              Detectá duplicados, validá CFDIs y procesá transferencias en segundos.
            </p>

            <div style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 8 }}>
              {FEATURES.map(({ icon, text }) => (
                <div key={text} className="sv-feat">
                  <span style={{ fontSize: "1rem" }}>{icon}</span>
                  {text}
                </div>
              ))}
            </div>
          </div>

          {/* Footer */}
          <p style={{ position: "relative", zIndex: 1, color: "#7895cc", fontSize: "0.75rem" }}>
            © 2026 SmartVoucher · Uso exclusivo corporativo
          </p>
        </div>

        {/* ── RIGHT PANEL — Form ──────────────────────────────── */}
        <div className="sv-right">
          {/* Mobile logo (visible < 1024px) */}
          <div className="sv-mobile-logo" style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: "2.5rem" }}>
            <ShieldIcon size={32} dark />
            <span style={{ color: "#003d9b", fontSize: "1.125rem", fontWeight: 800 }}>SmartVoucher</span>
          </div>

          {/* Card */}
          <div style={{ width: "100%", maxWidth: cardMaxWidth }}>
            {/* Header */}
            <div className="sv-a sv-a1" style={{ marginBottom: "2rem" }}>
              <h2 style={{ fontSize: "1.5rem", fontWeight: 700, color: "#141b2b", margin: "0 0 6px", letterSpacing: "-0.02em" }}>
                {title}
              </h2>
              <p style={{ fontSize: "0.875rem", color: "#434654", margin: 0 }}>{subtitle}</p>
            </div>

            {beforeForm}
            {children}
            {afterForm}
          </div>
        </div>
      </div>
    </>
  );
}
