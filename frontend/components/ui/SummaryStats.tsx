"use client";

import React from "react";
import { motion } from "framer-motion";
import type { DashboardStats } from "@/types/tender";

interface KpiCardProps {
  label: string;
  value: number | null;
  loading: boolean;
  color: string;
  glow: string;
  icon: React.ReactNode;
  description?: string;
  index: number;
}

function KpiCard({ label, value, loading, color, glow, icon, description, index }: KpiCardProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay: index * 0.07, ease: "easeOut" }}
      whileHover={{ y: -3, transition: { duration: 0.15 } }}
      className="rounded-2xl p-5 relative overflow-hidden cursor-default"
      style={{
        background: "var(--bg-card)",
        border: "1px solid var(--border)",
        transition: "border-color 0.2s, box-shadow 0.2s",
      }}
      onMouseEnter={(e) => {
        (e.currentTarget as HTMLElement).style.borderColor = glow.replace("0.2", "0.35");
        (e.currentTarget as HTMLElement).style.boxShadow = `0 0 24px ${glow}`;
      }}
      onMouseLeave={(e) => {
        (e.currentTarget as HTMLElement).style.borderColor = "var(--border)";
        (e.currentTarget as HTMLElement).style.boxShadow = "none";
      }}
    >
      {/* Corner glow */}
      <div
        className="absolute top-0 right-0 w-28 h-28 pointer-events-none"
        style={{ background: `radial-gradient(circle at top right, ${glow} 0%, transparent 70%)` }}
      />

      <div className="flex items-start justify-between mb-4">
        <p style={{ color: "var(--text-muted)", fontSize: "0.68rem", fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase" }}>
          {label}
        </p>
        <div
          className="flex items-center justify-center w-9 h-9 rounded-xl flex-shrink-0"
          style={{ background: glow, color }}
        >
          {icon}
        </div>
      </div>

      {loading ? (
        <div className="skeleton h-10 w-24 mb-1" />
      ) : (
        <motion.p
          initial={{ scale: 0.8, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ duration: 0.4, delay: index * 0.07 + 0.15 }}
          style={{ color, fontSize: "2.25rem", fontWeight: 800, lineHeight: 1, fontVariantNumeric: "tabular-nums", letterSpacing: "-0.03em" }}
        >
          {value !== null && value !== undefined ? value.toLocaleString() : "—"}
        </motion.p>
      )}

      {description && (
        <p style={{ color: "var(--text-muted)", fontSize: "0.7rem", marginTop: "0.375rem" }}>
          {description}
        </p>
      )}
    </motion.div>
  );
}

interface SummaryStatsProps {
  stats: DashboardStats | null;
  loading: boolean;
}

export default function SummaryStats({ stats, loading }: SummaryStatsProps) {
  const cards = [
    {
      label: "Total Tenders",
      value: stats?.total_tenders ?? null,
      color: "#60a5fa",
      glow: "rgba(59,130,246,0.18)",
      description: "All procurement tenders",
      icon: (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
          <polyline points="14 2 14 8 20 8"/>
        </svg>
      ),
    },
    {
      label: "High Risk",
      value: stats?.high_risk_count ?? null,
      color: "#f87171",
      glow: "rgba(239,68,68,0.18)",
      description: "Score ≥ 70 — requires review",
      icon: (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
          <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
        </svg>
      ),
    },
    {
      label: "Active Red Flags",
      value: stats?.high_flag_count ?? null,
      color: "#fbbf24",
      glow: "rgba(245,158,11,0.18)",
      description: "Unresolved fraud indicators",
      icon: (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/>
          <line x1="4" y1="22" x2="4" y2="15"/>
        </svg>
      ),
    },
    {
      label: "Collusion Rings",
      value: stats?.collusion_ring_count ?? null,
      color: "#c084fc",
      glow: "rgba(167,139,250,0.18)",
      description: "Detected bid-rigging networks",
      icon: (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/>
          <line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/>
          <line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/>
        </svg>
      ),
    },
  ];

  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "1rem" }} aria-label="Dashboard summary statistics">
      {cards.map((card, i) => (
        <KpiCard key={card.label} {...card} loading={loading} index={i} />
      ))}
    </div>
  );
}
