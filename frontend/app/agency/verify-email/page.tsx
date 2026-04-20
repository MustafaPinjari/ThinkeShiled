"use client";

import { useRouter, useSearchParams } from "next/navigation";
import React, { Suspense, useEffect, useRef, useState } from "react";
import { verifyEmail } from "@/services/agencies";

type VerifyState = "loading" | "success" | "error" | "missing_token";

// Wrap in Suspense because useSearchParams() requires it in Next.js 14
export default function VerifyEmailPage() {
  return (
    <Suspense fallback={<LoadingShell />}>
      <VerifyEmailContent />
    </Suspense>
  );
}

function VerifyEmailContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get("token");

  const [state, setState] = useState<VerifyState>(
    token ? "loading" : "missing_token"
  );
  const [errorMessage, setErrorMessage] = useState<string>(
    "Email verification failed. The link may have expired or already been used."
  );

  // Prevent double-invocation in React Strict Mode
  const calledRef = useRef(false);

  useEffect(() => {
    if (!token || calledRef.current) return;
    calledRef.current = true;

    verifyEmail(token)
      .then(() => setState("success"))
      .catch((err: unknown) => {
        const axiosErr = err as {
          response?: { status?: number; data?: { detail?: string } };
        };
        const detail = axiosErr?.response?.data?.detail;
        if (detail) setErrorMessage(detail);
        setState("error");
      });
  }, [token]);

  // ── Loading ──────────────────────────────────────────────────────────────
  if (state === "loading") {
    return (
      <StatusLayout>
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
        <h1 style={{ fontSize: "1.15rem", fontWeight: 700, letterSpacing: "-0.02em", marginBottom: "0.5rem" }}>
          Verifying your email…
        </h1>
        <p style={{ fontSize: "0.82rem", color: "var(--text-secondary)" }}>
          Please wait while we confirm your email address.
        </p>
      </StatusLayout>
    );
  }

  // ── Success ──────────────────────────────────────────────────────────────
  if (state === "success") {
    return (
      <StatusLayout>
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
          Email verified
        </h1>
        <p style={{ fontSize: "0.85rem", color: "var(--text-secondary)", lineHeight: 1.65, marginBottom: "1.75rem" }}>
          Your agency account is now active. You can sign in to access the
          TenderShield portal.
        </p>
        <button
          onClick={() => router.push("/login")}
          className="ts-btn ts-btn-primary"
          style={{ width: "100%", height: "2.5rem", fontSize: "0.875rem" }}
        >
          Sign In
        </button>
      </StatusLayout>
    );
  }

  // ── Missing token ────────────────────────────────────────────────────────
  if (state === "missing_token") {
    return (
      <StatusLayout>
        <ErrorIcon />
        <h1 style={{ fontSize: "1.2rem", fontWeight: 700, letterSpacing: "-0.02em", marginBottom: "0.75rem" }}>
          Invalid verification link
        </h1>
        <p style={{ fontSize: "0.85rem", color: "var(--text-secondary)", lineHeight: 1.65, marginBottom: "1.75rem" }}>
          This link is missing a verification token. Please use the link from
          your verification email.
        </p>
        <button
          onClick={() => router.push("/")}
          className="ts-btn ts-btn-ghost"
          style={{ width: "100%", height: "2.5rem", fontSize: "0.875rem" }}
        >
          Back to Home
        </button>
      </StatusLayout>
    );
  }

  // ── Error ────────────────────────────────────────────────────────────────
  return (
    <StatusLayout>
      <ErrorIcon />
      <h1 style={{ fontSize: "1.2rem", fontWeight: 700, letterSpacing: "-0.02em", marginBottom: "0.75rem" }}>
        Verification failed
      </h1>
      <p style={{ fontSize: "0.85rem", color: "var(--text-secondary)", lineHeight: 1.65, marginBottom: "1.75rem" }}>
        {errorMessage}
      </p>
      <div style={{ display: "flex", flexDirection: "column", gap: "0.625rem" }}>
        <button
          onClick={() => router.push("/agency/register")}
          className="ts-btn ts-btn-primary"
          style={{ width: "100%", height: "2.5rem", fontSize: "0.875rem" }}
        >
          Register Again
        </button>
        <button
          onClick={() => router.push("/")}
          className="ts-btn ts-btn-ghost"
          style={{ width: "100%", height: "2.5rem", fontSize: "0.875rem" }}
        >
          Back to Home
        </button>
      </div>
    </StatusLayout>
  );
}

// ── Shared layout ─────────────────────────────────────────────────────────────

function StatusLayout({ children }: { children: React.ReactNode }) {
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
        {/* Logo */}
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

// ── Suspense fallback ─────────────────────────────────────────────────────────

function LoadingShell() {
  return (
    <StatusLayout>
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
        Loading…
      </h1>
    </StatusLayout>
  );
}

function ErrorIcon() {
  return (
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
  );
}
