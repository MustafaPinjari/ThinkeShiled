"use client";

import { useRouter } from "next/navigation";
import React, { useState } from "react";
import { registerAgency } from "@/services/agencies";

// ── GSTIN validation ──────────────────────────────────────────────────────────
// Pattern: [0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}
const GSTIN_REGEX = /^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$/;

function validateGstin(value: string): string | null {
  if (!value) return "GSTIN is required.";
  if (!GSTIN_REGEX.test(value)) {
    return "Invalid GSTIN format. Expected: 2 digits, 5 uppercase letters, 4 digits, 1 uppercase letter, 1 alphanumeric (not 0), Z, 1 alphanumeric.";
  }
  return null;
}

// ── Field definitions ─────────────────────────────────────────────────────────

interface FormValues {
  legal_name: string;
  gstin: string;
  ministry: string;
  contact_name: string;
  contact_email: string;
  password: string;
}

type FieldErrors = Partial<Record<keyof FormValues, string>>;

const INITIAL_VALUES: FormValues = {
  legal_name: "",
  gstin: "",
  ministry: "",
  contact_name: "",
  contact_email: "",
  password: "",
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function validateAll(values: FormValues): FieldErrors {
  const errors: FieldErrors = {};

  if (!values.legal_name.trim()) errors.legal_name = "Legal name is required.";
  const gstinError = validateGstin(values.gstin.trim());
  if (gstinError) errors.gstin = gstinError;
  if (!values.ministry.trim()) errors.ministry = "Ministry / department is required.";
  if (!values.contact_name.trim()) errors.contact_name = "Contact name is required.";
  if (!values.contact_email.trim()) {
    errors.contact_email = "Official email is required.";
  } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(values.contact_email)) {
    errors.contact_email = "Enter a valid email address.";
  }
  if (!values.password) {
    errors.password = "Password is required.";
  } else if (values.password.length < 8) {
    errors.password = "Password must be at least 8 characters.";
  }

  return errors;
}

// ── Sub-components ────────────────────────────────────────────────────────────

interface FieldProps {
  id: string;
  label: string;
  type?: string;
  value: string;
  onChange: (v: string) => void;
  error?: string;
  placeholder?: string;
  autoComplete?: string;
  hint?: string;
  disabled?: boolean;
}

function Field({
  id,
  label,
  type = "text",
  value,
  onChange,
  error,
  placeholder,
  autoComplete,
  hint,
  disabled,
}: FieldProps) {
  const [showPw, setShowPw] = useState(false);
  const isPassword = type === "password";
  const inputType = isPassword ? (showPw ? "text" : "password") : type;

  return (
    <div>
      <label
        htmlFor={id}
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
        {label}
      </label>
      <div style={{ position: "relative" }}>
        <input
          id={id}
          type={inputType}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          autoComplete={autoComplete}
          disabled={disabled}
          aria-invalid={!!error}
          aria-describedby={error ? `${id}-error` : hint ? `${id}-hint` : undefined}
          className="ts-input"
          style={{
            borderColor: error ? "rgba(239,68,68,0.5)" : undefined,
            paddingRight: isPassword ? "2.5rem" : undefined,
          }}
        />
        {isPassword && (
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
        )}
      </div>
      {hint && !error && (
        <p id={`${id}-hint`} style={{ fontSize: "0.68rem", color: "var(--text-muted)", marginTop: "0.25rem" }}>
          {hint}
        </p>
      )}
      {error && (
        <p
          id={`${id}-error`}
          role="alert"
          style={{ fontSize: "0.72rem", color: "#f87171", marginTop: "0.3rem" }}
        >
          {error}
        </p>
      )}
    </div>
  );
}

// ── Page component ────────────────────────────────────────────────────────────

export default function AgencyRegistrationPage() {
  const router = useRouter();
  const [values, setValues] = useState<FormValues>(INITIAL_VALUES);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [serverError, setServerError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState(false);

  function set(field: keyof FormValues) {
    return (v: string) => {
      setValues((prev) => ({ ...prev, [field]: v }));
      // Clear field error on change
      if (fieldErrors[field]) {
        setFieldErrors((prev) => ({ ...prev, [field]: undefined }));
      }
      setServerError(null);
    };
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setServerError(null);

    const errors = validateAll(values);
    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors);
      // Focus first error field
      const firstKey = Object.keys(errors)[0] as keyof FormValues;
      document.getElementById(firstKey)?.focus();
      return;
    }

    setSubmitting(true);
    try {
      await registerAgency({
        legal_name: values.legal_name.trim(),
        gstin: values.gstin.trim().toUpperCase(),
        ministry: values.ministry.trim(),
        contact_name: values.contact_name.trim(),
        contact_email: values.contact_email.trim().toLowerCase(),
        password: values.password,
      });
      setSuccess(true);
    } catch (err: unknown) {
      const axiosErr = err as {
        response?: { status?: number; data?: Record<string, string | string[]> };
      };
      const data = axiosErr?.response?.data;
      if (data) {
        // Map server field errors to field-level display
        const newFieldErrors: FieldErrors = {};
        let hasFieldError = false;

        const fieldMap: Record<string, keyof FormValues> = {
          legal_name: "legal_name",
          gstin: "gstin",
          ministry: "ministry",
          contact_name: "contact_name",
          contact_email: "contact_email",
          password: "password",
        };

        for (const [key, fk] of Object.entries(fieldMap)) {
          if (data[key]) {
            const msg = Array.isArray(data[key]) ? (data[key] as string[]).join(" ") : String(data[key]);
            newFieldErrors[fk] = msg;
            hasFieldError = true;
          }
        }

        if (hasFieldError) {
          setFieldErrors(newFieldErrors);
        } else if (data.detail) {
          setServerError(String(data.detail));
        } else if (data.non_field_errors) {
          const msg = Array.isArray(data.non_field_errors)
            ? (data.non_field_errors as string[]).join(" ")
            : String(data.non_field_errors);
          setServerError(msg);
        } else {
          setServerError("Registration failed. Please check your details and try again.");
        }
      } else {
        setServerError("Unable to connect. Please try again.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  // ── Success state ──────────────────────────────────────────────────────────
  if (success) {
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
          style={{
            maxWidth: 440,
            width: "100%",
            background: "var(--bg-card)",
            borderRadius: 20,
            padding: "2.5rem 2rem",
            textAlign: "center",
            boxShadow: "0 24px 64px rgba(0,0,0,0.6)",
          }}
        >
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
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M20 6L9 17l-5-5"/>
            </svg>
          </div>
          <h1
            style={{
              fontSize: "1.2rem",
              fontWeight: 700,
              letterSpacing: "-0.02em",
              marginBottom: "0.75rem",
            }}
          >
            Registration submitted
          </h1>
          <p style={{ fontSize: "0.85rem", color: "var(--text-secondary)", lineHeight: 1.65, marginBottom: "1.75rem" }}>
            We&apos;ve sent a verification email to{" "}
            <strong style={{ color: "var(--text-primary)" }}>{values.contact_email}</strong>.
            Click the link in the email to activate your agency account.
          </p>
          <button
            onClick={() => router.push("/login")}
            className="ts-btn ts-btn-ghost"
            style={{ width: "100%", height: "2.5rem" }}
          >
            Go to Sign In
          </button>
        </div>
      </div>
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
      {/* Background grid */}
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
          maxWidth: 480,
          position: "relative",
          zIndex: 1,
        }}
      >
        {/* Back link */}
        <button
          onClick={() => router.push("/")}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "0.375rem",
            background: "none",
            border: "none",
            cursor: "pointer",
            color: "var(--text-muted)",
            fontSize: "0.78rem",
            padding: 0,
            marginBottom: "1.5rem",
          }}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M19 12H5M12 19l-7-7 7-7"/>
          </svg>
          Back to home
        </button>

        <div
          style={{
            background: "var(--bg-card)",
            borderRadius: 20,
            padding: "clamp(1.5rem, 4vw, 2rem)",
            boxShadow: "0 24px 64px rgba(0,0,0,0.6)",
          }}
        >
          {/* Header */}
          <div style={{ marginBottom: "1.75rem" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "0.625rem", marginBottom: "1rem" }}>
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
            <h1 style={{ fontSize: "1.2rem", fontWeight: 700, letterSpacing: "-0.02em", marginBottom: "0.375rem" }}>
              Register your agency
            </h1>
            <p style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
              Already have an account?{" "}
              <button
                type="button"
                onClick={() => router.push("/login")}
                style={{
                  background: "none",
                  border: "none",
                  cursor: "pointer",
                  color: "#60a5fa",
                  fontSize: "0.78rem",
                  padding: 0,
                  textDecoration: "underline",
                }}
              >
                Sign in
              </button>
            </p>
          </div>

          {/* Server-level error */}
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

          <form onSubmit={handleSubmit} noValidate style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            {/* Agency details section */}
            <div>
              <p
                style={{
                  fontSize: "0.68rem",
                  fontWeight: 600,
                  color: "var(--text-muted)",
                  textTransform: "uppercase",
                  letterSpacing: "0.08em",
                  marginBottom: "0.75rem",
                  paddingBottom: "0.5rem",
                  borderBottom: "1px solid var(--border)",
                }}
              >
                Agency Details
              </p>
              <div style={{ display: "flex", flexDirection: "column", gap: "0.875rem" }}>
                <Field
                  id="legal_name"
                  label="Legal Name *"
                  value={values.legal_name}
                  onChange={set("legal_name")}
                  error={fieldErrors.legal_name}
                  placeholder="e.g. National Highways Authority of India"
                  autoComplete="organization"
                  disabled={submitting}
                />
                <Field
                  id="gstin"
                  label="GSTIN *"
                  value={values.gstin}
                  onChange={(v) => set("gstin")(v.toUpperCase())}
                  error={fieldErrors.gstin}
                  placeholder="e.g. 07AAACN0081N1ZC"
                  autoComplete="off"
                  hint="15-character Indian GST Identification Number"
                  disabled={submitting}
                />
                <Field
                  id="ministry"
                  label="Ministry / Department *"
                  value={values.ministry}
                  onChange={set("ministry")}
                  error={fieldErrors.ministry}
                  placeholder="e.g. Ministry of Road Transport and Highways"
                  disabled={submitting}
                />
              </div>
            </div>

            {/* Admin account section */}
            <div>
              <p
                style={{
                  fontSize: "0.68rem",
                  fontWeight: 600,
                  color: "var(--text-muted)",
                  textTransform: "uppercase",
                  letterSpacing: "0.08em",
                  marginBottom: "0.75rem",
                  paddingBottom: "0.5rem",
                  borderBottom: "1px solid var(--border)",
                }}
              >
                Agency Admin Account
              </p>
              <div style={{ display: "flex", flexDirection: "column", gap: "0.875rem" }}>
                <Field
                  id="contact_name"
                  label="Contact Name *"
                  value={values.contact_name}
                  onChange={set("contact_name")}
                  error={fieldErrors.contact_name}
                  placeholder="Full name of the primary contact"
                  autoComplete="name"
                  disabled={submitting}
                />
                <Field
                  id="contact_email"
                  label="Official Email *"
                  type="email"
                  value={values.contact_email}
                  onChange={set("contact_email")}
                  error={fieldErrors.contact_email}
                  placeholder="official@agency.gov.in"
                  autoComplete="email"
                  hint="A verification link will be sent to this address"
                  disabled={submitting}
                />
                <Field
                  id="password"
                  label="Password *"
                  type="password"
                  value={values.password}
                  onChange={set("password")}
                  error={fieldErrors.password}
                  placeholder="Minimum 8 characters"
                  autoComplete="new-password"
                  disabled={submitting}
                />
              </div>
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
                  Submitting…
                </span>
              ) : (
                "Register Agency"
              )}
            </button>

            <p style={{ fontSize: "0.68rem", color: "var(--text-muted)", textAlign: "center", lineHeight: 1.5 }}>
              By registering, you confirm this is an authorised government procurement body.
              All registrations are reviewed before activation.
            </p>
          </form>
        </div>
      </div>
    </div>
  );
}
