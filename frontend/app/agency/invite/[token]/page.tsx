"use client";

import { useParams, useRouter } from "next/navigation";
import React, { useEffect, useRef, useState } from "react";
import { acceptInvitation, getInvitationDetails } from "@/services/agencies";
import type { InvitationDetails } from "@/services/agencies";

// ── Role display helpers ──────────────────────────────────────────────────────

const ROLE_LABELS: Record<string, string> = {
  AGENCY_OFFICER: "Agency Officer",
  REVIEWER: "Reviewer",
};

function roleLabel(role: string): string {
  return ROLE_LABELS[role] ?? role;
}

// ── Page states ───────────────────────────────────────────────────────────────

type PageState = "loading" | "form" | "expired" | "success" | "error";

// ── Component ─────────────────────────────────────────────────────────────────

export default function InviteAcceptPage() {
  const params = useParams<{ token: string }>();
  const token = params?.token ?? "";
  const router = useRouter();

  const [pageState, setPageState] = useState<PageState>("loading");
  const [invitation, setInvitation] = useState<InvitationDetails | null>(null);
  const [errorMessage, setErrorMessage] = useState<string>("");

  // Form state
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [serverError, setServerError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const calledRef = useRef(false);

  // Fetch invitation details on mount
  useEffect(() => {
    if (!token || calledRef.current) return;
    calledRef.current = true;

    getInvitationDetails(token)
      .then((details) => {
        setInvitation(details);
        setPageState("form");
      })
      .catch((err: unknown) => {
        const axiosErr = err as {
          response?: { status?: number; data?: { detail?: string } };
        };
        const status = axiosErr?.response?.status;
        const detail = axiosErr?.response?.data?.detail;

        if (status === 410) {
          setPageState("expired");
        } else {
          setErrorMessage(detail ?? "Unable to load invitation details. Please try again.");
          setPageState("error");
        }
      });
  }, [token]);

  // ── Form validation ────────────────────────────────────────────────────────
  function validateForm(): Record<string, string> {
    const errors: Record<string, string> = {};
    if (!username.trim()) errors.username = "Username is required.";
    if (!password) {
      errors.password = "Password is required.";
    } else if (password.length < 8) {
      errors.password = "Password must be at least 8 characters.";
    }
    if (!confirmPassword) {
      errors.confirmPassword = "Please confirm your password.";
    } else if (password !== confirmPassword) {
      errors.confirmPassword = "Passwords do not match.";
    }
    return errors;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setServerError(null);

    const errors = validateForm();
    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors);
      return;
    }

    setSubmitting(true);
    try {
      await acceptInvitation(token, password, username.trim());
      setPageState("success");
    } catch (err: unknown) {
      const axiosErr = err as {
        response?: { status?: number; data?: Record<string, string | string[]> };
      };
      const status = axiosErr?.response?.status;
      const data = axiosErr?.response?.data;

      if (status === 410) {
        setPageState("expired");
        return;
      }

      if (data) {
        const newFieldErrors: Record<string, string> = {};
        let hasFieldError = false;
        for (const key of ["username", "password"]) {
          if (data[key]) {
            const msg = Array.isArray(data[key])
              ? (data[key] as string[]).join(" ")
              : String(data[key]);
            newFieldErrors[key] = msg;
            hasFieldError = true;
          }
        }
        if (hasFieldError) {
          setFieldErrors(newFieldErrors);
        } else if (data.detail) {
          setServerError(String(data.detail));
        } else {
          setServerError("Registration failed. Please try again.");
        }
      } else {
        setServerError("Unable to connect. Please try again.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  // ── Render states ──────────────────────────────────────────────────────────

  if (pageState === "loading") {
    return (
      <Shell>
        <div
          style={{
            width: 48,
            height: 48,
            borderRadius: "50%",
            border: "3px solid rgba(59,130,246,0.2)",
            borderTopColor: "#3b82f6",
            animation: "spin 1s linear infinite",
            margin: "0 auto 1.5rem",
          }}
        />
        <h1 style={{ fontSize: "1.1rem", fontWeight: 700, letterSpacing: "-0.02em", marginBottom: "0.5rem" }}>
          Loading invitation…
        </h1>
        <p style={{ fontSize: "0.82rem", color: "var(--text-secondary)" }}>
          Please wait.
        </p>
      </Shell>
    );
  }

  if (pageState === "expired") {
    return (
      <Shell>
        <div
          style={{
            width: 56,
            height: 56,
            borderRadius: "50%",
            background: "rgba(245,158,11,0.15)",
            border: "1px solid rgba(245,158,11,0.3)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            margin: "0 auto 1.25rem",
            color: "#fbbf24",
          }}
        >
          <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10"/>
            <polyline points="12 6 12 12 16 14"/>
          </svg>
        </div>
        <h1 style={{ fontSize: "1.2rem", fontWeight: 700, letterSpacing: "-0.02em", marginBottom: "0.75rem" }}>
          Invitation expired
        </h1>
        <p style={{ fontSize: "0.85rem", color: "var(--text-secondary)", lineHeight: 1.65, marginBottom: "1.75rem" }}>
          This invitation link has expired or has already been used. Please ask
          your Agency Admin to send a new invitation.
        </p>
        <button
          onClick={() => router.push("/")}
          className="ts-btn ts-btn-ghost"
          style={{ width: "100%", height: "2.5rem", fontSize: "0.875rem" }}
        >
          Back to Home
        </button>
      </Shell>
    );
  }

  if (pageState === "error") {
    return (
      <Shell>
        <div
          style={{
            width: 56,
            height: 56,
            borderRadius: "50%",
            background: "rgba(239,68,68,0.15)",
            border: "1px solid rgba(239,68,68,0.3)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            margin: "0 auto 1.25rem",
            color: "#f87171",
          }}
        >
          <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10"/>
            <line x1="12" y1="8" x2="12" y2="12"/>
            <line x1="12" y1="16" x2="12.01" y2="16"/>
          </svg>
        </div>
        <h1 style={{ fontSize: "1.2rem", fontWeight: 700, letterSpacing: "-0.02em", marginBottom: "0.75rem" }}>
          Unable to load invitation
        </h1>
        <p style={{ fontSize: "0.85rem", color: "var(--text-secondary)", lineHeight: 1.65, marginBottom: "1.75rem" }}>
          {errorMessage}
        </p>
        <button
          onClick={() => router.push("/")}
          className="ts-btn ts-btn-ghost"
          style={{ width: "100%", height: "2.5rem", fontSize: "0.875rem" }}
        >
          Back to Home
        </button>
      </Shell>
    );
  }

  if (pageState === "success") {
    return (
      <Shell>
        <div
          style={{
            width: 56,
            height: 56,
            borderRadius: "50%",
            background: "rgba(34,197,94,0.15)",
            border: "1px solid rgba(34,197,94,0.3)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            margin: "0 auto 1.25rem",
            color: "#4ade80",
          }}
        >
          <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M20 6L9 17l-5-5"/>
          </svg>
        </div>
        <h1 style={{ fontSize: "1.2rem", fontWeight: 700, letterSpacing: "-0.02em", marginBottom: "0.75rem" }}>
          Account created
        </h1>
        <p style={{ fontSize: "0.85rem", color: "var(--text-secondary)", lineHeight: 1.65, marginBottom: "1.75rem" }}>
          You&apos;ve successfully joined{" "}
          <strong style={{ color: "var(--text-primary)" }}>
            {invitation?.agency_name}
          </strong>{" "}
          as a{" "}
          <strong style={{ color: "var(--text-primary)" }}>
            {invitation ? roleLabel(invitation.role) : ""}
          </strong>
          . You can now sign in to access the portal.
        </p>
        <button
          onClick={() => router.push("/login")}
          className="ts-btn ts-btn-primary"
          style={{ width: "100%", height: "2.5rem", fontSize: "0.875rem" }}
        >
          Sign In
        </button>
      </Shell>
    );
  }

  // ── Form ───────────────────────────────────────────────────────────────────
  return (
    <div
      style={{
        minHeight: "100vh",
        background: "var(--bg-base)",
        display: "flex",
        alignItems: "flex-start",
        justifyContent: "center",
        padding: "2rem 1rem",
      }}
    >
      <div
        aria-hidden="true"
        style={{
          position: "fixed",
          inset: 0,
          pointerEvents: "none",
          backgroundImage:
            "linear-gradient(rgba(255,255,255,0.015) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.015) 1px, transparent 1px)",
          backgroundSize: "48px 48px",
        }}
      />

      <div style={{ width: "100%", maxWidth: 440, position: "relative", zIndex: 1 }}>
        <div
          style={{
            background: "var(--bg-card)",
            borderRadius: 20,
            padding: "clamp(1.5rem, 4vw, 2rem)",
            boxShadow: "0 24px 64px rgba(0,0,0,0.6)",
          }}
        >
          {/* Logo */}
          <div style={{ display: "flex", alignItems: "center", gap: "0.625rem", marginBottom: "1.5rem" }}>
            <div
              style={{
                width: 36,
                height: 36,
                borderRadius: 10,
                background: "linear-gradient(135deg, #3b82f6, #8b5cf6)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                flexShrink: 0,
              }}
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
              </svg>
            </div>
            <span style={{ fontWeight: 700, fontSize: "0.95rem", letterSpacing: "-0.02em" }}>
              TenderShield
            </span>
          </div>

          {/* Invitation context */}
          {invitation && (
            <div
              style={{
                background: "rgba(59,130,246,0.08)",
                border: "1px solid rgba(59,130,246,0.2)",
                borderRadius: 10,
                padding: "0.875rem 1rem",
                marginBottom: "1.5rem",
              }}
            >
              <p style={{ fontSize: "0.78rem", color: "var(--text-secondary)", marginBottom: "0.375rem" }}>
                You&apos;ve been invited to join
              </p>
              <p style={{ fontSize: "0.95rem", fontWeight: 700, color: "var(--text-primary)", letterSpacing: "-0.01em", marginBottom: "0.25rem" }}>
                {invitation.agency_name}
              </p>
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", flexWrap: "wrap" }}>
                <span
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: "0.25rem",
                    background: "rgba(59,130,246,0.15)",
                    border: "1px solid rgba(59,130,246,0.25)",
                    borderRadius: 6,
                    padding: "0.2rem 0.625rem",
                    fontSize: "0.7rem",
                    fontWeight: 600,
                    color: "#60a5fa",
                    letterSpacing: "0.02em",
                  }}
                >
                  {roleLabel(invitation.role)}
                </span>
              </div>
            </div>
          )}

          <h1 style={{ fontSize: "1.1rem", fontWeight: 700, letterSpacing: "-0.02em", marginBottom: "0.375rem" }}>
            Complete your registration
          </h1>
          <p style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginBottom: "1.5rem" }}>
            Create a username and password to activate your account.
          </p>

          {/* Server error */}
          {serverError && (
            <div
              role="alert"
              style={{
                borderRadius: 8,
                border: "1px solid rgba(239,68,68,0.25)",
                background: "rgba(239,68,68,0.1)",
                padding: "0.625rem 0.875rem",
                fontSize: "0.8rem",
                color: "#f87171",
                marginBottom: "1.25rem",
              }}
            >
              {serverError}
            </div>
          )}

          <form onSubmit={handleSubmit} noValidate style={{ display: "flex", flexDirection: "column", gap: "0.875rem" }}>
            {/* Pre-filled email (read-only) */}
            {invitation && (
              <div>
                <label
                  style={{
                    display: "block",
                    fontSize: "0.68rem",
                    fontWeight: 600,
                    color: "var(--text-muted)",
                    textTransform: "uppercase",
                    letterSpacing: "0.06em",
                    marginBottom: "0.375rem",
                  }}
                >
                  Email
                </label>
                <input
                  type="email"
                  value={invitation.email}
                  readOnly
                  aria-readonly="true"
                  className="ts-input"
                  style={{ opacity: 0.6, cursor: "not-allowed" }}
                />
                <p style={{ fontSize: "0.68rem", color: "var(--text-muted)", marginTop: "0.25rem" }}>
                  This email was set by your invitation and cannot be changed.
                </p>
              </div>
            )}

            {/* Username */}
            <div>
              <label
                htmlFor="username"
                style={{
                  display: "block",
                  fontSize: "0.68rem",
                  fontWeight: 600,
                  color: "var(--text-muted)",
                  textTransform: "uppercase",
                  letterSpacing: "0.06em",
                  marginBottom: "0.375rem",
                }}
              >
                Username *
              </label>
              <input
                id="username"
                type="text"
                value={username}
                onChange={(e) => {
                  setUsername(e.target.value);
                  if (fieldErrors.username) setFieldErrors((p) => ({ ...p, username: "" }));
                  setServerError(null);
                }}
                placeholder="Choose a username"
                autoComplete="username"
                disabled={submitting}
                aria-invalid={!!fieldErrors.username}
                aria-describedby={fieldErrors.username ? "username-error" : undefined}
                className="ts-input"
                style={{ borderColor: fieldErrors.username ? "rgba(239,68,68,0.5)" : undefined }}
              />
              {fieldErrors.username && (
                <p id="username-error" role="alert" style={{ fontSize: "0.72rem", color: "#f87171", marginTop: "0.3rem" }}>
                  {fieldErrors.username}
                </p>
              )}
            </div>

            {/* Password */}
            <div>
              <label
                htmlFor="password"
                style={{
                  display: "block",
                  fontSize: "0.68rem",
                  fontWeight: 600,
                  color: "var(--text-muted)",
                  textTransform: "uppercase",
                  letterSpacing: "0.06em",
                  marginBottom: "0.375rem",
                }}
              >
                Password *
              </label>
              <div style={{ position: "relative" }}>
                <input
                  id="password"
                  type={showPw ? "text" : "password"}
                  value={password}
                  onChange={(e) => {
                    setPassword(e.target.value);
                    if (fieldErrors.password) setFieldErrors((p) => ({ ...p, password: "" }));
                    setServerError(null);
                  }}
                  placeholder="Minimum 8 characters"
                  autoComplete="new-password"
                  disabled={submitting}
                  aria-invalid={!!fieldErrors.password}
                  aria-describedby={fieldErrors.password ? "password-error" : undefined}
                  className="ts-input"
                  style={{
                    borderColor: fieldErrors.password ? "rgba(239,68,68,0.5)" : undefined,
                    paddingRight: "2.5rem",
                  }}
                />
                <button
                  type="button"
                  onClick={() => setShowPw((p) => !p)}
                  aria-label={showPw ? "Hide password" : "Show password"}
                  style={{
                    position: "absolute",
                    right: "0.625rem",
                    top: "50%",
                    transform: "translateY(-50%)",
                    background: "none",
                    border: "none",
                    cursor: "pointer",
                    color: "var(--text-muted)",
                    padding: 4,
                    display: "flex",
                    alignItems: "center",
                  }}
                >
                  {showPw ? (
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/>
                      <line x1="1" y1="1" x2="23" y2="23"/>
                    </svg>
                  ) : (
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                      <circle cx="12" cy="12" r="3"/>
                    </svg>
                  )}
                </button>
              </div>
              {fieldErrors.password && (
                <p id="password-error" role="alert" style={{ fontSize: "0.72rem", color: "#f87171", marginTop: "0.3rem" }}>
                  {fieldErrors.password}
                </p>
              )}
            </div>

            {/* Confirm password */}
            <div>
              <label
                htmlFor="confirmPassword"
                style={{
                  display: "block",
                  fontSize: "0.68rem",
                  fontWeight: 600,
                  color: "var(--text-muted)",
                  textTransform: "uppercase",
                  letterSpacing: "0.06em",
                  marginBottom: "0.375rem",
                }}
              >
                Confirm Password *
              </label>
              <input
                id="confirmPassword"
                type={showPw ? "text" : "password"}
                value={confirmPassword}
                onChange={(e) => {
                  setConfirmPassword(e.target.value);
                  if (fieldErrors.confirmPassword) setFieldErrors((p) => ({ ...p, confirmPassword: "" }));
                }}
                placeholder="Re-enter your password"
                autoComplete="new-password"
                disabled={submitting}
                aria-invalid={!!fieldErrors.confirmPassword}
                aria-describedby={fieldErrors.confirmPassword ? "confirmPassword-error" : undefined}
                className="ts-input"
                style={{ borderColor: fieldErrors.confirmPassword ? "rgba(239,68,68,0.5)" : undefined }}
              />
              {fieldErrors.confirmPassword && (
                <p id="confirmPassword-error" role="alert" style={{ fontSize: "0.72rem", color: "#f87171", marginTop: "0.3rem" }}>
                  {fieldErrors.confirmPassword}
                </p>
              )}
            </div>

            <button
              type="submit"
              disabled={submitting}
              className="ts-btn ts-btn-primary"
              style={{ width: "100%", height: "2.75rem", fontSize: "0.875rem", marginTop: "0.25rem", borderRadius: 10 }}
            >
              {submitting ? (
                <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <div
                    style={{
                      width: 14,
                      height: 14,
                      borderRadius: "50%",
                      border: "2px solid rgba(255,255,255,0.4)",
                      borderTopColor: "#fff",
                      animation: "spin 1s linear infinite",
                    }}
                  />
                  Creating account…
                </span>
              ) : (
                "Accept Invitation"
              )}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}

// ── Shell layout (for non-form states) ───────────────────────────────────────

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        minHeight: "100vh",
        background: "var(--bg-base)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "1rem",
      }}
    >
      <div
        aria-hidden="true"
        style={{
          position: "fixed",
          inset: 0,
          pointerEvents: "none",
          backgroundImage:
            "linear-gradient(rgba(255,255,255,0.015) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.015) 1px, transparent 1px)",
          backgroundSize: "48px 48px",
        }}
      />
      <div
        style={{
          width: "100%",
          maxWidth: 400,
          background: "var(--bg-card)",
          borderRadius: 20,
          padding: "2.5rem 2rem",
          textAlign: "center",
          boxShadow: "0 24px 64px rgba(0,0,0,0.6)",
          position: "relative",
          zIndex: 1,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: "0.5rem", marginBottom: "2rem" }}>
          <div
            style={{
              width: 32,
              height: 32,
              borderRadius: 9,
              background: "linear-gradient(135deg, #3b82f6, #8b5cf6)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              flexShrink: 0,
            }}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
            </svg>
          </div>
          <span style={{ fontWeight: 700, fontSize: "0.95rem", letterSpacing: "-0.02em" }}>
            TenderShield
          </span>
        </div>
        {children}
      </div>
    </div>
  );
}
