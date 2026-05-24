"use client";

/**
 * ApiKeyCard — R-76, R-77, R-78, R-81.
 *
 * Manages API key state:
 *   - No key  → "Generate API Key" button
 *   - Has key → masked display "••••••••{prefix}" + Regenerate + Revoke
 *
 * onGenerate → calls POST /web/auth/api-key → one-time modal with plaintext + copy button
 * onRevoke   → confirm dialog → calls DELETE /web/auth/api-key
 *
 * Modal is accessible: focus trap on open, ESC closes it.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { fetchApi, ApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";

interface ApiKeyCardProps {
  hasKey: boolean;
  prefix: string | null;
  onGenerate: () => void;
  onRevoke: () => void;
}

interface GenerateResponse {
  api_key: string;
  message: string;
}

// ── One-time key modal ────────────────────────────────────────────────────────

interface KeyModalProps {
  plainKey: string;
  onClose: () => void;
}

function KeyModal({ plainKey, onClose }: KeyModalProps) {
  const [copied, setCopied] = useState(false);
  const closeRef = useRef<HTMLButtonElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);

  // Focus the close button on mount (accessible focus trap start)
  useEffect(() => {
    closeRef.current?.focus();
  }, []);

  // ESC closes the modal
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  // Focus trap: cycle focus within the dialog
  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;

    function handleTab(e: KeyboardEvent) {
      if (e.key !== "Tab") return;
      const focusable = dialog!.querySelectorAll<HTMLElement>(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
      );
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (e.shiftKey) {
        if (document.activeElement === first) {
          e.preventDefault();
          last?.focus();
        }
      } else {
        if (document.activeElement === last) {
          e.preventDefault();
          first?.focus();
        }
      }
    }
    dialog.addEventListener("keydown", handleTab);
    return () => dialog.removeEventListener("keydown", handleTab);
  }, []);

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(plainKey);
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    } catch {
      // Fallback: select the text
      const el = document.getElementById("api-key-display");
      if (el) {
        const range = document.createRange();
        range.selectNodeContents(el);
        window.getSelection()?.removeAllRanges();
        window.getSelection()?.addRange(range);
      }
    }
  }

  return (
    /* Backdrop */
    <div
      role="presentation"
      style={{
        position: "fixed", inset: 0, zIndex: 50,
        background: "rgba(0,0,0,0.45)", display: "flex",
        alignItems: "center", justifyContent: "center",
        padding: "1rem",
      }}
      onClick={(e) => {
        // Close when clicking the backdrop (not the dialog)
        if (e.target === e.currentTarget) onClose();
      }}
    >
      {/* Dialog */}
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="modal-title"
        style={{
          background: "white", borderRadius: 16, padding: "2rem",
          maxWidth: 480, width: "100%",
          boxShadow: "0 20px 60px rgba(0,0,0,0.25)",
        }}
      >
        {/* Header */}
        <div style={{ marginBottom: "1.5rem" }}>
          <h3
            id="modal-title"
            style={{ fontSize: "1.125rem", fontWeight: 700, color: "#141b2b", margin: "0 0 6px", letterSpacing: "-0.01em" }}
          >
            Your API Key
          </h3>
          <p style={{ fontSize: "0.875rem", color: "#434654", margin: 0 }}>
            Copy this key now — it will not be shown again.
          </p>
        </div>

        {/* Warning banner */}
        <div
          role="note"
          style={{
            display: "flex", alignItems: "flex-start", gap: 10,
            padding: "12px 14px", borderRadius: 10, marginBottom: "1rem",
            background: "#fff8e6", border: "1px solid #ffe4a0",
          }}
        >
          <span aria-hidden="true" style={{ fontSize: "1rem", marginTop: 1 }}>⚠️</span>
          <p style={{ margin: 0, fontSize: "0.8125rem", fontWeight: 500, color: "#92400e" }}>
            This key will not be shown again. Store it in a secure location.
          </p>
        </div>

        {/* Key display */}
        <div
          style={{
            display: "flex", alignItems: "center", gap: 8,
            padding: "10px 14px", borderRadius: 10,
            background: "#f4f6fb", border: "1px solid #c3c6d6",
            marginBottom: "1.5rem", overflowX: "auto",
          }}
        >
          <code
            id="api-key-display"
            style={{
              flex: 1, fontSize: "0.8125rem", fontFamily: "monospace",
              color: "#141b2b", wordBreak: "break-all", userSelect: "all",
            }}
          >
            {plainKey}
          </code>
          <button
            type="button"
            onClick={handleCopy}
            aria-label="Copy API key"
            style={{
              flexShrink: 0, padding: "6px 12px", borderRadius: 8,
              fontSize: "0.75rem", fontWeight: 600,
              background: copied ? "#f0fdf4" : "white",
              border: `1px solid ${copied ? "#bbf7d0" : "#c3c6d6"}`,
              color: copied ? "#166534" : "#003d9b",
              cursor: "pointer", transition: "all 0.2s",
            }}
          >
            {copied ? "✓ Copied" : "Copy"}
          </button>
        </div>

        {/* Close button */}
        <Button
          ref={closeRef}
          type="button"
          variant="primary"
          size="md"
          onClick={onClose}
          style={{ width: "100%", borderRadius: 10, height: "2.75rem" }}
        >
          Done
        </Button>
      </div>
    </div>
  );
}

// ── Confirm dialog ────────────────────────────────────────────────────────────

interface ConfirmDialogProps {
  onConfirm: () => void;
  onCancel: () => void;
  loading?: boolean;
}

function ConfirmDialog({ onConfirm, onCancel, loading = false }: ConfirmDialogProps) {
  const cancelRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    cancelRef.current?.focus();
  }, []);

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onCancel();
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onCancel]);

  return (
    <div
      role="presentation"
      style={{
        position: "fixed", inset: 0, zIndex: 50,
        background: "rgba(0,0,0,0.45)", display: "flex",
        alignItems: "center", justifyContent: "center", padding: "1rem",
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-title"
        style={{
          background: "white", borderRadius: 16, padding: "2rem",
          maxWidth: 400, width: "100%",
          boxShadow: "0 20px 60px rgba(0,0,0,0.25)",
        }}
      >
        <h3
          id="confirm-title"
          style={{ fontSize: "1.125rem", fontWeight: 700, color: "#141b2b", margin: "0 0 10px" }}
        >
          Revoke API Key?
        </h3>
        <p style={{ fontSize: "0.875rem", color: "#434654", margin: "0 0 1.5rem" }}>
          This will permanently invalidate your current API key. Any integrations using it will stop working immediately.
        </p>
        <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
          <Button
            ref={cancelRef}
            type="button"
            variant="secondary"
            size="md"
            onClick={onCancel}
            disabled={loading}
            style={{ borderRadius: 10 }}
          >
            Cancel
          </Button>
          <Button
            type="button"
            variant="destructive"
            size="md"
            onClick={onConfirm}
            disabled={loading}
            aria-busy={loading}
            style={{ borderRadius: 10 }}
          >
            {loading ? "Revoking…" : "Revoke key"}
          </Button>
        </div>
      </div>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export function ApiKeyCard({ hasKey, prefix, onGenerate, onRevoke }: ApiKeyCardProps) {
  const [generating, setGenerating] = useState(false);
  const [revoking, setRevoking] = useState(false);
  const [modalKey, setModalKey] = useState<string | null>(null);
  const [showConfirm, setShowConfirm] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleGenerate = useCallback(async () => {
    setError(null);
    setGenerating(true);
    try {
      const data = await fetchApi<GenerateResponse>("/api/web/auth/api-key", {
        method: "POST",
      });
      setModalKey(data.api_key);
      onGenerate();
    } catch (err) {
      if (err instanceof ApiError) {
        setError(`Failed to generate key (${err.status}): ${err.message}`);
      } else {
        setError("Network error. Please try again.");
      }
    } finally {
      setGenerating(false);
    }
  }, [onGenerate]);

  const handleRevoke = useCallback(async () => {
    setError(null);
    setRevoking(true);
    try {
      await fetchApi("/api/web/auth/api-key", { method: "DELETE" });
      setShowConfirm(false);
      onRevoke();
    } catch (err) {
      if (err instanceof ApiError) {
        setError(`Failed to revoke key (${err.status}): ${err.message}`);
      } else {
        setError("Network error. Please try again.");
      }
      setShowConfirm(false);
    } finally {
      setRevoking(false);
    }
  }, [onRevoke]);

  return (
    <>
      {/* One-time key modal */}
      {modalKey && (
        <KeyModal plainKey={modalKey} onClose={() => setModalKey(null)} />
      )}

      {/* Revoke confirmation */}
      {showConfirm && (
        <ConfirmDialog
          onConfirm={handleRevoke}
          onCancel={() => setShowConfirm(false)}
          loading={revoking}
        />
      )}

      {/* Card */}
      <div
        className="bg-white border border-[var(--color-outline-variant)] rounded-xl overflow-hidden"
        aria-label="API Key management"
      >
        {/* Card header */}
        <div className="px-5 py-4 border-b border-[var(--color-outline-variant)] flex items-center justify-between">
          <h2 className="text-sm font-semibold text-[var(--color-on-surface)]">
            API Key
          </h2>
          {/* Status indicator */}
          <span
            style={{
              display: "inline-flex", alignItems: "center", gap: 6,
              padding: "2px 10px", borderRadius: 99,
              fontSize: "0.72rem", fontWeight: 600, letterSpacing: "0.04em",
              ...(hasKey
                ? { background: "#f0fdf4", border: "1px solid #bbf7d0", color: "#166534" }
                : { background: "#f8f9fa", border: "1px solid #c3c6d6", color: "#737685" }),
            }}
          >
            <span
              style={{
                width: 6, height: 6, borderRadius: "50%",
                background: hasKey ? "#22c55e" : "#c3c6d6",
              }}
            />
            {hasKey ? "Active" : "No key configured"}
          </span>
        </div>

        {/* Card body */}
        <div className="px-5 py-5 space-y-4">
          {/* Error */}
          {error && (
            <div
              role="alert"
              style={{
                display: "flex", alignItems: "flex-start", gap: 10,
                padding: "10px 14px", borderRadius: 10,
                background: "#fff4f4", border: "1px solid #ffdad6",
              }}
            >
              <span aria-hidden="true" style={{ fontSize: "0.875rem", marginTop: 1 }}>⚠️</span>
              <p style={{ margin: 0, fontSize: "0.8125rem", fontWeight: 500, color: "#93000a" }}>
                {error}
              </p>
            </div>
          )}

          {hasKey && prefix ? (
            <>
              {/* Masked key display */}
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <div
                  style={{
                    flex: 1, padding: "10px 14px", borderRadius: 10,
                    background: "#f4f6fb", border: "1px solid #c3c6d6",
                    fontFamily: "monospace", fontSize: "0.875rem",
                    color: "#141b2b", letterSpacing: "0.04em",
                  }}
                  aria-label={`API key starting with ${prefix}`}
                >
                  <span style={{ color: "#737685" }}>••••••••</span>
                  {prefix}
                </div>
              </div>

              <p className="text-xs text-[var(--color-on-surface-variant)]">
                Only the prefix is shown. Generate a new key to replace the current one.
              </p>

              {/* Action buttons */}
              <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                <Button
                  type="button"
                  variant="secondary"
                  size="md"
                  onClick={handleGenerate}
                  disabled={generating || revoking}
                  aria-busy={generating}
                  style={{ borderRadius: 10 }}
                >
                  {generating ? "Generating…" : "Regenerate"}
                </Button>
                <Button
                  type="button"
                  variant="destructive"
                  size="md"
                  onClick={() => setShowConfirm(true)}
                  disabled={generating || revoking}
                  style={{ borderRadius: 10 }}
                >
                  Revoke
                </Button>
              </div>
            </>
          ) : (
            <>
              {/* No key state */}
              <p className="text-sm text-[var(--color-on-surface-variant)]">
                Generate an API key to authenticate programmatic access to SmartVoucher.
                The key will only be shown once — store it securely.
              </p>

              <Button
                type="button"
                variant="primary"
                size="md"
                onClick={handleGenerate}
                disabled={generating}
                aria-busy={generating}
                style={{ borderRadius: 10 }}
              >
                {generating ? "Generating…" : "Generate API Key"}
              </Button>
            </>
          )}
        </div>
      </div>
    </>
  );
}
