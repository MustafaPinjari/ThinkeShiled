"use client";

import { useRouter } from "next/navigation";
import React, { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { useAuth } from "@/contexts/AuthContext";

export default function LoginPage() {
  const { login, isAuthenticated, isLoading } = useAuth();
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!isLoading && isAuthenticated) router.replace("/dashboard");
  }, [isAuthenticated, isLoading, router]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null); setSubmitting(true);
    try {
      await login(username, password);
      router.replace("/dashboard");
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status;
      if (status === 401) setError("Invalid username or password.");
      else if (status === 429) setError("Too many attempts. Please wait.");
      else setError("Unable to connect. Please try again.");
    } finally { setSubmitting(false); }
  }

  if (isLoading) {
    return (
      <div style={{ display: "flex", minHeight: "100vh", alignItems: "center", justifyContent: "center", background: "var(--bg-base)" }}>
        <div style={{ width: 28, height: 28, borderRadius: "50%", border: "2px solid #3b82f6", borderTopColor: "transparent", animation: "spin 1s linear infinite" }} />
      </div>
    );
  }

  return (
    <div style={{ display: "flex", minHeight: "100vh", alignItems: "center", justifyContent: "center", background: "var(--bg-base)", padding: "1rem" }}>
      {/* Subtle grid */}
      <div style={{ position: "fixed", inset: 0, pointerEvents: "none", backgroundImage: "linear-gradient(rgba(255,255,255,0.015) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.015) 1px, transparent 1px)", backgroundSize: "48px 48px" }} />

      <motion.div
        initial={{ opacity: 0, y: 20, scale: 0.97 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.35, ease: "easeOut" }}
        style={{ width: "100%", maxWidth: 360, background: "var(--bg-card)", borderRadius: 20, padding: "2rem", boxShadow: "0 24px 64px rgba(0,0,0,0.6)", position: "relative", zIndex: 1 }}
      >
        {/* Logo */}
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", marginBottom: "2rem" }}>
          <div style={{ width: 48, height: 48, borderRadius: 14, background: "linear-gradient(135deg, #3b82f6, #8b5cf6)", display: "flex", alignItems: "center", justifyContent: "center", marginBottom: "0.875rem", boxShadow: "0 8px 24px rgba(59,130,246,0.3)" }}>
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
            </svg>
          </div>
          <h1 style={{ fontSize: "1.15rem", fontWeight: 700, color: "var(--text-primary)", letterSpacing: "-0.02em" }}>TenderShield</h1>
          <p style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginTop: 3 }}>Fraud Intelligence Platform</p>
        </div>

        <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "0.875rem" }}>
          <div>
            <label style={{ display: "block", fontSize: "0.68rem", fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: "0.375rem" }}>
              Username
            </label>
            <input type="text" autoComplete="username" value={username} onChange={e => setUsername(e.target.value)}
              required disabled={submitting} placeholder="Enter username"
              className="ts-input" />
          </div>

          <div>
            <label style={{ display: "block", fontSize: "0.68rem", fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: "0.375rem" }}>
              Password
            </label>
            <div style={{ position: "relative" }}>
              <input type={showPw ? "text" : "password"} autoComplete="current-password" value={password}
                onChange={e => setPassword(e.target.value)} required disabled={submitting} placeholder="Enter password"
                className="ts-input" style={{ paddingRight: "2.5rem" }} />
              <button type="button" onClick={() => setShowPw(!showPw)}
                style={{ position: "absolute", right: "0.625rem", top: "50%", transform: "translateY(-50%)", background: "none", border: "none", cursor: "pointer", color: "var(--text-muted)", padding: 4 }}>
                {showPw
                  ? <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>
                  : <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
                }
              </button>
            </div>
          </div>

          {error && (
            <motion.div initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }} role="alert"
              style={{ borderRadius: 8, border: "1px solid rgba(239,68,68,0.25)", background: "rgba(239,68,68,0.1)", padding: "0.5rem 0.75rem", fontSize: "0.78rem", color: "#f87171" }}>
              {error}
            </motion.div>
          )}

          <button type="submit" disabled={submitting || !username || !password} className="ts-btn ts-btn-primary"
            style={{ width: "100%", height: "2.5rem", fontSize: "0.85rem", marginTop: "0.25rem", borderRadius: 10 }}>
            {submitting
              ? <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <div style={{ width: 14, height: 14, borderRadius: "50%", border: "2px solid rgba(255,255,255,0.4)", borderTopColor: "#fff", animation: "spin 1s linear infinite" }} />
                  Signing in…
                </span>
              : "Sign In"
            }
          </button>
        </form>

        <p style={{ marginTop: "1.25rem", textAlign: "center", fontSize: "0.65rem", color: "var(--text-muted)" }}>
          Authorised personnel only · All access is audited
        </p>
      </motion.div>
    </div>
  );
}
