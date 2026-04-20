"use client";

import React from "react";
import { format } from "date-fns";
import type { RedFlag } from "@/types/tender";

const FLAG_LABELS: Record<string, string> = {
  SINGLE_BIDDER: "Single Bidder",
  PRICE_ANOMALY: "Price Anomaly",
  REPEAT_WINNER: "Repeat Winner",
  SHORT_DEADLINE: "Short Deadline",
  LINKED_ENTITIES: "Linked Entities",
  COVER_BID_PATTERN: "Cover Bid Pattern",
};

function getSeverityStyle(severity: string) {
  if (severity === "HIGH") return { color: "#f87171", bg: "rgba(239,68,68,0.1)", border: "rgba(239,68,68,0.25)", dot: "#ef4444" };
  if (severity === "MEDIUM") return { color: "#fbbf24", bg: "rgba(245,158,11,0.1)", border: "rgba(245,158,11,0.25)", dot: "#f59e0b" };
  return { color: "#60a5fa", bg: "rgba(59,130,246,0.1)", border: "rgba(59,130,246,0.25)", dot: "#3b82f6" };
}

function TriggerData({ data }: { data: Record<string, unknown> }) {
  const entries = Object.entries(data);
  if (entries.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-3 mt-2">
      {entries.map(([key, value]) => (
        <div key={key}>
          <span style={{ color: "var(--text-muted)", fontSize: "0.68rem" }}>{key.replace(/_/g, " ")}: </span>
          <span style={{ color: "var(--text-secondary)", fontSize: "0.72rem", fontWeight: 500 }}>
            {typeof value === "number" ? (Number.isInteger(value) ? value : value.toFixed(3)) : String(value)}
          </span>
        </div>
      ))}
    </div>
  );
}

function FlagRow({ flag }: { flag: RedFlag }) {
  const s = getSeverityStyle(flag.severity);
  return (
    <li
      className="flex items-start gap-3 p-3 rounded-xl transition-all duration-150"
      style={{ background: s.bg, border: `1px solid ${s.border}` }}
    >
      <div className="mt-1 w-2 h-2 rounded-full flex-shrink-0" style={{ background: s.dot, boxShadow: `0 0 6px ${s.dot}` }} />
      <div className="flex-1 min-w-0">
        <div className="flex flex-wrap items-center gap-2 mb-1">
          <span style={{ color: "var(--text-primary)", fontSize: "0.875rem", fontWeight: 600 }}>
            {FLAG_LABELS[flag.flag_type] ?? flag.flag_type.replace(/_/g, " ")}
          </span>
          <span className="badge" style={{ background: s.bg, color: s.color, border: `1px solid ${s.border}`, fontSize: "0.65rem" }}>
            {flag.severity}
          </span>
          {!flag.is_active && (
            <span className="badge badge-gray" style={{ fontSize: "0.65rem" }}>Cleared</span>
          )}
        </div>
        {flag.rule_description && (
          <p style={{ color: "var(--text-secondary)", fontSize: "0.8rem", lineHeight: 1.5 }}>{flag.rule_description}</p>
        )}
        {flag.trigger_data && Object.keys(flag.trigger_data).length > 0 && (
          <TriggerData data={flag.trigger_data} />
        )}
        <p style={{ color: "var(--text-muted)", fontSize: "0.68rem", marginTop: "0.5rem" }}>
          Raised: {flag.raised_at ? format(new Date(flag.raised_at), "dd MMM yyyy HH:mm") : "—"}
          {flag.cleared_at && ` · Cleared: ${format(new Date(flag.cleared_at), "dd MMM yyyy HH:mm")}`}
          {flag.rule_version && ` · Rule v${flag.rule_version}`}
        </p>
      </div>
    </li>
  );
}

interface RedFlagListProps {
  redFlags: RedFlag[];
  loading?: boolean;
}

export default function RedFlagList({ redFlags, loading = false }: RedFlagListProps) {
  const active = redFlags.filter((f) => f.is_active);
  const cleared = redFlags.filter((f) => !f.is_active);

  return (
    <section aria-labelledby="red-flags-heading">
      <div className="flex items-center justify-between mb-3">
        <h2 id="red-flags-heading" style={{ color: "var(--text-primary)", fontWeight: 600, fontSize: "0.95rem" }}>
          Red Flags
        </h2>
        {!loading && (
          <span style={{ color: "var(--text-muted)", fontSize: "0.72rem" }}>
            {active.length} active{cleared.length > 0 && `, ${cleared.length} cleared`}
          </span>
        )}
      </div>

      {loading ? (
        <div className="space-y-2 animate-pulse">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="skeleton h-16 rounded-xl" />
          ))}
        </div>
      ) : redFlags.length === 0 ? (
        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem", padding: "1rem 0" }}>
          No red flags detected for this tender.
        </p>
      ) : (
        <ul className="space-y-2" aria-label="Red flag list">
          {active.map((flag) => <FlagRow key={flag.id} flag={flag} />)}
          {cleared.map((flag) => <FlagRow key={flag.id} flag={flag} />)}
        </ul>
      )}
    </section>
  );
}
