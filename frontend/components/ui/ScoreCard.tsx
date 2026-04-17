"use client";

import React from "react";

function getScoreStyle(score: number | null): {
  color: string; glow: string; label: string; trackColor: string;
} {
  if (score === null || score === undefined) {
    return { color: "var(--text-muted)", glow: "transparent", label: "No Score", trackColor: "rgba(255,255,255,0.05)" };
  }
  if (score >= 70) return { color: "#f87171", glow: "rgba(239,68,68,0.3)", label: "High Risk", trackColor: "rgba(239,68,68,0.15)" };
  if (score >= 40) return { color: "#fbbf24", glow: "rgba(245,158,11,0.3)", label: "Medium Risk", trackColor: "rgba(245,158,11,0.15)" };
  return { color: "#34d399", glow: "rgba(16,185,129,0.3)", label: "Low Risk", trackColor: "rgba(16,185,129,0.15)" };
}

interface ScoreCardProps {
  score: number | null;
  loading?: boolean;
}

export default function ScoreCard({ score, loading = false }: ScoreCardProps) {
  const { color, glow, label, trackColor } = getScoreStyle(score);
  const pct = score !== null ? Math.min(100, Math.max(0, score)) : 0;
  // SVG circle: r=40, circumference = 2π*40 ≈ 251.3
  const circumference = 251.3;
  const dashOffset = circumference - (pct / 100) * circumference;

  if (loading) {
    return (
      <div className="rounded-2xl p-5 w-52" style={{ background: "var(--bg-card)", border: "1px solid var(--border)" }}>
        <div className="skeleton h-3 w-24 mb-4" />
        <div className="skeleton h-32 w-32 rounded-full mx-auto mb-4" />
        <div className="skeleton h-3 w-full mb-2" />
        <div className="skeleton h-3 w-4/5" />
      </div>
    );
  }

  return (
    <div
      className="rounded-2xl p-5 w-52"
      style={{
        background: "var(--bg-card)",
        border: `1px solid ${score !== null ? glow.replace("0.3", "0.25") : "var(--border)"}`,
        boxShadow: score !== null ? `0 0 24px ${glow}` : "none",
      }}
      aria-label="Fraud Risk Score card"
    >
      <p style={{ color: "var(--text-muted)", fontSize: "0.7rem", fontWeight: 600, letterSpacing: "0.06em", textTransform: "uppercase", marginBottom: "1rem" }}>
        Fraud Risk Score
      </p>

      {/* Ring */}
      <div className="flex items-center justify-center mb-3">
        <div className="relative w-32 h-32">
          <svg width="128" height="128" viewBox="0 0 100 100" className="-rotate-90" style={{ display: "block" }}>
            {/* Track */}
            <circle cx="50" cy="50" r="40" fill="none" stroke={trackColor} strokeWidth="8" />
            {/* Progress */}
            <circle
              cx="50" cy="50" r="40"
              fill="none"
              stroke={color}
              strokeWidth="8"
              strokeLinecap="round"
              strokeDasharray={circumference}
              strokeDashoffset={dashOffset}
              style={{ transition: "stroke-dashoffset 0.8s ease-out", filter: `drop-shadow(0 0 6px ${glow})` }}
            />
          </svg>
          {/* Center text */}
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <span style={{ color, fontSize: "1.75rem", fontWeight: 700, lineHeight: 1, fontVariantNumeric: "tabular-nums" }}>
              {score !== null ? score : "—"}
            </span>
            <span style={{ color: "var(--text-muted)", fontSize: "0.65rem" }}>/100</span>
          </div>
        </div>
      </div>

      {/* Label */}
      <div className="text-center mb-3">
        <span
          className="badge"
          style={{
            background: trackColor,
            color,
            border: `1px solid ${glow.replace("0.3", "0.3")}`,
            fontSize: "0.7rem",
          }}
        >
          {label}
        </span>
      </div>

      {/* Advisory */}
      <p style={{ color: "var(--text-muted)", fontSize: "0.68rem", lineHeight: 1.5, textAlign: "center" }}>
        Advisory only. Human review required before any legal action.
      </p>
    </div>
  );
}
