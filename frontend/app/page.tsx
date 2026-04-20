"use client";

import { useRouter } from "next/navigation";
import React from "react";

// ── Value proposition data ────────────────────────────────────────────────────

const VALUE_PROPS = [
  {
    icon: (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
        <path d="M9 12l2 2 4-4"/>
      </svg>
    ),
    title: "Fraud Detection",
    description:
      "AI-powered analysis flags suspicious patterns in government tenders before they cause harm — protecting public funds at scale.",
  },
  {
    icon: (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="3" y="3" width="18" height="18" rx="2"/>
        <path d="M9 9h6M9 12h6M9 15h4"/>
      </svg>
    ),
    title: "Rule Engine",
    description:
      "Six deterministic rule-based detectors run on every submission — catching bid rigging, price manipulation, and specification tailoring instantly.",
  },
  {
    icon: (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="10"/>
        <path d="M12 8v4l3 3"/>
      </svg>
    ),
    title: "ML Scoring",
    description:
      "Isolation Forest and Random Forest models produce a 0–100 fraud risk score with SHAP explanations, so reviewers understand exactly why a tender was flagged.",
  },
  {
    icon: (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
        <polyline points="14 2 14 8 20 8"/>
        <line x1="16" y1="13" x2="8" y2="13"/>
        <line x1="16" y1="17" x2="8" y2="17"/>
        <polyline points="10 9 9 9 8 9"/>
      </svg>
    ),
    title: "Audit Trail",
    description:
      "Every action — submission, review, status change, and access event — is recorded in an immutable audit log with actor, timestamp, and IP address.",
  },
];

const STATS = [
  { value: "6", label: "Rule-based detectors" },
  { value: "2", label: "ML models (IF + RF)" },
  { value: "100%", label: "Immutable audit coverage" },
  { value: "< 30s", label: "Scoring turnaround" },
];

// ── Component ─────────────────────────────────────────────────────────────────

export default function LandingPage() {
  const router = useRouter();

  return (
    <div
      style={{
        minHeight: "100vh",
        background: "var(--bg-base)",
        color: "var(--text-primary)",
        overflowX: "hidden",
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

      {/* ── Nav ── */}
      <header
        style={{
          position: "sticky",
          top: 0,
          zIndex: 40,
          borderBottom: "1px solid var(--border)",
          background: "rgba(13,13,13,0.85)",
          backdropFilter: "blur(16px)",
          WebkitBackdropFilter: "blur(16px)",
        }}
      >
        <div
          style={{
            maxWidth: 1100,
            margin: "0 auto",
            padding: "0 1rem",
            height: 56,
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          {/* Logo */}
          <div style={{ display: "flex", alignItems: "center", gap: "0.625rem" }}>
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

          {/* Nav actions */}
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <button
              onClick={() => router.push("/login")}
              className="ts-btn ts-btn-ghost"
              style={{ fontSize: "0.8rem", padding: "0.375rem 0.875rem" }}
            >
              Sign In
            </button>
            <button
              onClick={() => router.push("/agency/register")}
              className="ts-btn ts-btn-primary"
              style={{ fontSize: "0.8rem", padding: "0.375rem 0.875rem" }}
            >
              Register Agency
            </button>
          </div>
        </div>
      </header>

      {/* ── Hero ── */}
      <section
        style={{
          maxWidth: 1100,
          margin: "0 auto",
          padding: "4rem 1rem 3rem",
          textAlign: "center",
        }}
      >
        {/* Badge */}
        <div
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "0.375rem",
            background: "rgba(59,130,246,0.1)",
            border: "1px solid rgba(59,130,246,0.25)",
            borderRadius: 9999,
            padding: "0.25rem 0.875rem",
            fontSize: "0.72rem",
            fontWeight: 600,
            color: "#60a5fa",
            letterSpacing: "0.04em",
            marginBottom: "1.5rem",
          }}
        >
          <span
            style={{
              width: 6,
              height: 6,
              borderRadius: "50%",
              background: "#3b82f6",
              flexShrink: 0,
            }}
          />
          GeM · CPPP · Government Procurement
        </div>

        {/* Headline */}
        <h1
          style={{
            fontSize: "clamp(2rem, 5vw, 3.25rem)",
            fontWeight: 800,
            letterSpacing: "-0.04em",
            lineHeight: 1.1,
            marginBottom: "1.25rem",
            maxWidth: 720,
            margin: "0 auto 1.25rem",
          }}
        >
          AI-Powered Fraud Detection for{" "}
          <span
            style={{
              background: "linear-gradient(135deg, #60a5fa, #a78bfa)",
              WebkitBackgroundClip: "text",
              WebkitTextFillColor: "transparent",
              backgroundClip: "text",
            }}
          >
            Government Tenders
          </span>
        </h1>

        {/* Sub-headline */}
        <p
          style={{
            fontSize: "clamp(0.9rem, 2vw, 1.05rem)",
            color: "var(--text-secondary)",
            lineHeight: 1.65,
            maxWidth: 580,
            margin: "0 auto 2.5rem",
          }}
        >
          TenderShield gives procurement agencies a single portal to submit tenders,
          receive instant fraud risk scores, and maintain a complete audit trail —
          all powered by rule-based detectors and machine learning.
        </p>

        {/* CTA */}
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: "0.75rem",
            justifyContent: "center",
          }}
        >
          <button
            onClick={() => router.push("/agency/register")}
            className="ts-btn ts-btn-primary"
            style={{
              fontSize: "0.9rem",
              padding: "0.75rem 1.75rem",
              borderRadius: 12,
              boxShadow: "0 8px 32px rgba(59,130,246,0.3)",
            }}
            aria-label="Register your agency on TenderShield"
          >
            Register Your Agency
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M5 12h14M12 5l7 7-7 7"/>
            </svg>
          </button>
          <button
            onClick={() => router.push("/login")}
            className="ts-btn ts-btn-ghost"
            style={{ fontSize: "0.9rem", padding: "0.75rem 1.75rem", borderRadius: 12 }}
          >
            Sign In
          </button>
        </div>
      </section>

      {/* ── Stats strip ── */}
      <section
        style={{
          borderTop: "1px solid var(--border)",
          borderBottom: "1px solid var(--border)",
          background: "var(--bg-surface)",
        }}
      >
        <div
          style={{
            maxWidth: 1100,
            margin: "0 auto",
            padding: "1.5rem 1rem",
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
            gap: "1rem",
          }}
        >
          {STATS.map((s) => (
            <div key={s.label} style={{ textAlign: "center", padding: "0.5rem" }}>
              <div
                style={{
                  fontSize: "clamp(1.4rem, 3vw, 1.75rem)",
                  fontWeight: 800,
                  letterSpacing: "-0.03em",
                  color: "var(--text-primary)",
                  lineHeight: 1,
                  marginBottom: "0.375rem",
                }}
              >
                {s.value}
              </div>
              <div style={{ fontSize: "0.72rem", color: "var(--text-muted)", fontWeight: 500 }}>
                {s.label}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ── Value propositions ── */}
      <section
        style={{
          maxWidth: 1100,
          margin: "0 auto",
          padding: "4rem 1rem",
        }}
      >
        <div style={{ textAlign: "center", marginBottom: "3rem" }}>
          <h2
            style={{
              fontSize: "clamp(1.4rem, 3vw, 1.875rem)",
              fontWeight: 700,
              letterSpacing: "-0.03em",
              marginBottom: "0.75rem",
            }}
          >
            Everything your agency needs
          </h2>
          <p style={{ fontSize: "0.9rem", color: "var(--text-secondary)", maxWidth: 480, margin: "0 auto" }}>
            From submission to clearance, TenderShield covers the full procurement
            integrity lifecycle.
          </p>
        </div>

        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))",
            gap: "1.25rem",
          }}
        >
          {VALUE_PROPS.map((vp) => (
            <div
              key={vp.title}
              style={{
                background: "var(--bg-card)",
                border: "1px solid var(--border)",
                borderRadius: 16,
                padding: "1.5rem",
                transition: "border-color 0.15s, background 0.15s",
              }}
              onMouseEnter={(e) => {
                (e.currentTarget as HTMLDivElement).style.borderColor = "rgba(59,130,246,0.3)";
                (e.currentTarget as HTMLDivElement).style.background = "var(--bg-card-hover)";
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLDivElement).style.borderColor = "var(--border)";
                (e.currentTarget as HTMLDivElement).style.background = "var(--bg-card)";
              }}
            >
              <div
                style={{
                  width: 44,
                  height: 44,
                  borderRadius: 12,
                  background: "rgba(59,130,246,0.1)",
                  border: "1px solid rgba(59,130,246,0.2)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  color: "#60a5fa",
                  marginBottom: "1rem",
                  flexShrink: 0,
                }}
              >
                {vp.icon}
              </div>
              <h3
                style={{
                  fontSize: "0.95rem",
                  fontWeight: 700,
                  letterSpacing: "-0.02em",
                  marginBottom: "0.5rem",
                  color: "var(--text-primary)",
                }}
              >
                {vp.title}
              </h3>
              <p style={{ fontSize: "0.82rem", color: "var(--text-secondary)", lineHeight: 1.6 }}>
                {vp.description}
              </p>
            </div>
          ))}
        </div>
      </section>

      {/* ── How it works ── */}
      <section
        style={{
          background: "var(--bg-surface)",
          borderTop: "1px solid var(--border)",
          borderBottom: "1px solid var(--border)",
        }}
      >
        <div
          style={{
            maxWidth: 1100,
            margin: "0 auto",
            padding: "4rem 1rem",
          }}
        >
          <div style={{ textAlign: "center", marginBottom: "3rem" }}>
            <h2
              style={{
                fontSize: "clamp(1.4rem, 3vw, 1.875rem)",
                fontWeight: 700,
                letterSpacing: "-0.03em",
                marginBottom: "0.75rem",
              }}
            >
              How it works
            </h2>
            <p style={{ fontSize: "0.9rem", color: "var(--text-secondary)", maxWidth: 480, margin: "0 auto" }}>
              Get your agency up and running in minutes.
            </p>
          </div>

          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
              gap: "1.5rem",
            }}
          >
            {[
              { step: "01", title: "Register", desc: "Submit your agency's GSTIN, legal name, and contact details." },
              { step: "02", title: "Verify", desc: "Click the verification link sent to your official email address." },
              { step: "03", title: "Submit Tenders", desc: "Upload tender details through the portal for instant analysis." },
              { step: "04", title: "Review Scores", desc: "Receive fraud risk scores and act on flagged submissions." },
            ].map((item) => (
              <div key={item.step} style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                <div
                  style={{
                    fontSize: "0.68rem",
                    fontWeight: 700,
                    color: "#3b82f6",
                    letterSpacing: "0.08em",
                    fontFamily: "var(--font-geist-mono), monospace",
                  }}
                >
                  {item.step}
                </div>
                <h3 style={{ fontSize: "0.95rem", fontWeight: 700, letterSpacing: "-0.02em" }}>
                  {item.title}
                </h3>
                <p style={{ fontSize: "0.82rem", color: "var(--text-secondary)", lineHeight: 1.6 }}>
                  {item.desc}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── CTA banner ── */}
      <section
        style={{
          maxWidth: 1100,
          margin: "0 auto",
          padding: "4rem 1rem",
          textAlign: "center",
        }}
      >
        <div
          style={{
            background: "linear-gradient(135deg, rgba(59,130,246,0.1), rgba(139,92,246,0.1))",
            border: "1px solid rgba(59,130,246,0.2)",
            borderRadius: 20,
            padding: "clamp(2rem, 5vw, 3.5rem) clamp(1rem, 4vw, 3rem)",
          }}
        >
          <h2
            style={{
              fontSize: "clamp(1.4rem, 3vw, 2rem)",
              fontWeight: 800,
              letterSpacing: "-0.03em",
              marginBottom: "0.875rem",
            }}
          >
            Ready to protect your procurement?
          </h2>
          <p
            style={{
              fontSize: "0.9rem",
              color: "var(--text-secondary)",
              maxWidth: 480,
              margin: "0 auto 2rem",
              lineHeight: 1.65,
            }}
          >
            Join government agencies already using TenderShield to detect fraud,
            maintain compliance, and build public trust.
          </p>
          <button
            onClick={() => router.push("/agency/register")}
            className="ts-btn ts-btn-primary"
            style={{
              fontSize: "0.9rem",
              padding: "0.75rem 2rem",
              borderRadius: 12,
              boxShadow: "0 8px 32px rgba(59,130,246,0.3)",
            }}
            aria-label="Get started by registering your agency"
          >
            Get Started — Register Your Agency
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M5 12h14M12 5l7 7-7 7"/>
            </svg>
          </button>
        </div>
      </section>

      {/* ── Footer ── */}
      <footer
        style={{
          borderTop: "1px solid var(--border)",
          padding: "1.5rem 1rem",
        }}
      >
        <div
          style={{
            maxWidth: 1100,
            margin: "0 auto",
            display: "flex",
            flexWrap: "wrap",
            alignItems: "center",
            justifyContent: "space-between",
            gap: "0.75rem",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <div
              style={{
                width: 24,
                height: 24,
                borderRadius: 7,
                background: "linear-gradient(135deg, #3b82f6, #8b5cf6)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                flexShrink: 0,
              }}
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
              </svg>
            </div>
            <span style={{ fontSize: "0.78rem", fontWeight: 600, color: "var(--text-secondary)" }}>
              TenderShield
            </span>
          </div>
          <p style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>
            Authorised personnel only · All access is audited
          </p>
        </div>
      </footer>
    </div>
  );
}
