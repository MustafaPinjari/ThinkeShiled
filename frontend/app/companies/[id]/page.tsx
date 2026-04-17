"use client";

import React, { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { format } from "date-fns";
import { motion } from "framer-motion";
import Layout from "@/components/Layout";
import api from "@/lib/api";
import type { CompanyProfile, CompanyRedFlag, CompanyTender, RiskStatus } from "@/types/company";
import type { PaginatedResponse } from "@/types/tender";

// ── Risk helpers ──────────────────────────────────────────────────────────────

const RISK_CONFIG: Record<RiskStatus, { badge: string; color: string; glow: string; label: string }> = {
  LOW: { badge: "badge badge-green", color: "#34d399", glow: "rgba(16,185,129,0.2)", label: "Low Risk" },
  MEDIUM: { badge: "badge badge-amber", color: "#fbbf24", glow: "rgba(245,158,11,0.2)", label: "Medium Risk" },
  HIGH_RISK: { badge: "badge badge-red", color: "#f87171", glow: "rgba(239,68,68,0.2)", label: "High Risk" },
};

const FLAG_LABELS: Record<string, string> = {
  SINGLE_BIDDER: "Single Bidder", PRICE_ANOMALY: "Price Anomaly",
  REPEAT_WINNER: "Repeat Winner", SHORT_DEADLINE: "Short Deadline",
  LINKED_ENTITIES: "Linked Entities", COVER_BID_PATTERN: "Cover Bid Pattern",
};

// ── Metric card ───────────────────────────────────────────────────────────────

function MetricCard({ label, value, sub, highlight, index }: {
  label: string; value: React.ReactNode; sub?: string; highlight?: boolean; index: number;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, delay: index * 0.06 }}
      className="rounded-2xl p-4 relative overflow-hidden"
      style={{
        background: "var(--bg-card)",
        border: `1px solid ${highlight ? "rgba(239,68,68,0.25)" : "var(--border)"}`,
        boxShadow: highlight ? "0 0 20px rgba(239,68,68,0.1)" : "none",
      }}
    >
      {highlight && (
        <div className="absolute top-0 right-0 w-20 h-20 pointer-events-none"
          style={{ background: "radial-gradient(circle at top right, rgba(239,68,68,0.12) 0%, transparent 70%)" }} />
      )}
      <p style={{ color: "var(--text-muted)", fontSize: "0.65rem", fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: "0.5rem" }}>
        {label}
      </p>
      <p style={{ color: highlight ? "#f87171" : "var(--text-primary)", fontSize: "1.6rem", fontWeight: 700, lineHeight: 1 }}>
        {value}
      </p>
      {sub && <p style={{ color: "var(--text-muted)", fontSize: "0.68rem", marginTop: "0.25rem" }}>{sub}</p>}
    </motion.div>
  );
}

// ── Tender timeline ───────────────────────────────────────────────────────────

function TenderTimeline({ tenders, loading, totalCount, currentPage, totalPages, onPageChange }: {
  tenders: CompanyTender[]; loading: boolean; totalCount: number;
  currentPage: number; totalPages: number; onPageChange: (p: number) => void;
}) {
  const PAGE_SIZE = 10;
  const from = Math.min((currentPage - 1) * PAGE_SIZE + 1, totalCount);
  const to = Math.min(currentPage * PAGE_SIZE, totalCount);

  return (
    <section>
      <div className="flex items-center justify-between mb-4">
        <h2 style={{ color: "var(--text-primary)", fontSize: "0.9rem", fontWeight: 600 }}>Tender Activity</h2>
        {!loading && (
          <span style={{ color: "var(--text-muted)", fontSize: "0.72rem" }}>
            {totalCount} tender{totalCount !== 1 ? "s" : ""}
          </span>
        )}
      </div>

      {loading ? (
        <div className="space-y-3">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="flex gap-4 py-3" style={{ borderBottom: "1px solid var(--border)" }}>
              <div className="skeleton h-4 w-24 shrink-0" />
              <div className="flex-1 space-y-2">
                <div className="skeleton h-4 w-3/4" />
                <div className="skeleton h-3 w-1/2" />
              </div>
            </div>
          ))}
        </div>
      ) : tenders.length === 0 ? (
        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem", padding: "1rem 0" }}>No tender activity recorded.</p>
      ) : (
        <>
          <div className="space-y-0">
            {tenders.map((tender, i) => (
              <motion.div
                key={tender.id}
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.2, delay: i * 0.04 }}
                className="flex items-start justify-between gap-4 py-3"
                style={{ borderBottom: "1px solid var(--border)" }}
              >
                <div className="flex items-start gap-3 min-w-0">
                  <div className="mt-1.5 w-2 h-2 rounded-full flex-shrink-0" style={{ background: "#3b82f6" }} />
                  <div className="min-w-0">
                    <Link href={`/tenders/${tender.id}`}
                      style={{ color: "var(--accent)", fontSize: "0.875rem", fontWeight: 500 }}
                      className="hover:underline line-clamp-1">
                      {tender.title}
                    </Link>
                    <p style={{ color: "var(--text-muted)", fontSize: "0.72rem", marginTop: "2px" }}>
                      {tender.category} · {tender.currency} {Number(tender.estimated_value).toLocaleString()}
                    </p>
                  </div>
                </div>
                <div className="shrink-0 flex items-center gap-2">
                  <span className={
                    tender.status === "ACTIVE" ? "badge badge-green" :
                    tender.status === "CLOSED" ? "badge badge-gray" : "badge badge-blue"
                  } style={{ fontSize: "0.6rem" }}>
                    {tender.status}
                  </span>
                  <span style={{ color: "var(--text-muted)", fontSize: "0.72rem", whiteSpace: "nowrap" }}>
                    {format(new Date(tender.submission_deadline), "dd MMM yyyy")}
                  </span>
                </div>
              </motion.div>
            ))}
          </div>

          {totalPages > 1 && (
            <div className="flex items-center justify-between pt-3" style={{ color: "var(--text-muted)", fontSize: "0.75rem" }}>
              <span>{from}–{to} of {totalCount}</span>
              <div className="flex items-center gap-1">
                <button onClick={() => onPageChange(currentPage - 1)} disabled={currentPage === 1}
                  style={{ padding: "0.2rem 0.5rem", borderRadius: "6px", background: "transparent", border: "1px solid var(--border)", color: "var(--text-secondary)", cursor: currentPage === 1 ? "not-allowed" : "pointer", opacity: currentPage === 1 ? 0.4 : 1 }}>‹</button>
                <span style={{ padding: "0 0.5rem" }}>{currentPage} / {totalPages}</span>
                <button onClick={() => onPageChange(currentPage + 1)} disabled={currentPage >= totalPages}
                  style={{ padding: "0.2rem 0.5rem", borderRadius: "6px", background: "transparent", border: "1px solid var(--border)", color: "var(--text-secondary)", cursor: currentPage >= totalPages ? "not-allowed" : "pointer", opacity: currentPage >= totalPages ? 0.4 : 1 }}>›</button>
              </div>
            </div>
          )}
        </>
      )}
    </section>
  );
}

// ── Red flags section ─────────────────────────────────────────────────────────

function CompanyRedFlagSection({ flags, loading }: { flags: CompanyRedFlag[]; loading: boolean }) {
  const activeFlags = flags.filter((f) => f.is_active);
  const clearedFlags = flags.filter((f) => !f.is_active);

  return (
    <section>
      <div className="flex items-center justify-between mb-4">
        <h2 style={{ color: "var(--text-primary)", fontSize: "0.9rem", fontWeight: 600 }}>Red Flags</h2>
        {!loading && (
          <span style={{ color: "var(--text-muted)", fontSize: "0.72rem" }}>
            {activeFlags.length} active{clearedFlags.length > 0 ? `, ${clearedFlags.length} cleared` : ""}
          </span>
        )}
      </div>

      {loading ? (
        <div className="space-y-3">
          {[...Array(3)].map((_, i) => <div key={i} className="skeleton h-14 rounded-xl" />)}
        </div>
      ) : flags.length === 0 ? (
        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem", padding: "1rem 0" }}>No red flags recorded.</p>
      ) : (
        <ul className="space-y-2">
          {[...activeFlags, ...clearedFlags].map((flag) => {
            const sev = flag.severity === "HIGH"
              ? { color: "#f87171", bg: "rgba(239,68,68,0.08)", border: "rgba(239,68,68,0.2)", dot: "#ef4444" }
              : flag.severity === "MEDIUM"
              ? { color: "#fbbf24", bg: "rgba(245,158,11,0.08)", border: "rgba(245,158,11,0.2)", dot: "#f59e0b" }
              : { color: "#60a5fa", bg: "rgba(59,130,246,0.08)", border: "rgba(59,130,246,0.2)", dot: "#3b82f6" };
            return (
              <li key={flag.id} className="flex items-start gap-3 p-3 rounded-xl"
                style={{ background: sev.bg, border: `1px solid ${sev.border}` }}>
                <div className="mt-1.5 w-2 h-2 rounded-full flex-shrink-0" style={{ background: sev.dot, boxShadow: `0 0 6px ${sev.dot}` }} />
                <div className="flex-1 min-w-0">
                  <div className="flex flex-wrap items-center gap-2 mb-1">
                    <span style={{ color: "var(--text-primary)", fontSize: "0.875rem", fontWeight: 600 }}>
                      {FLAG_LABELS[flag.flag_type] ?? flag.flag_type.replace(/_/g, " ")}
                    </span>
                    <span className="badge" style={{ background: sev.bg, color: sev.color, border: `1px solid ${sev.border}`, fontSize: "0.62rem" }}>
                      {flag.severity}
                    </span>
                    {!flag.is_active && <span className="badge badge-gray" style={{ fontSize: "0.62rem" }}>Cleared</span>}
                    <Link href={`/tenders/${flag.tender_id}`}
                      style={{ color: "var(--accent)", fontSize: "0.7rem", fontFamily: "monospace" }}
                      className="hover:underline">
                      {flag.tender_id}
                    </Link>
                  </div>
                  <p style={{ color: "var(--text-muted)", fontSize: "0.68rem" }}>
                    Raised: {flag.raised_at ? format(new Date(flag.raised_at), "dd MMM yyyy HH:mm") : "—"}
                    {flag.cleared_at && ` · Cleared: ${format(new Date(flag.cleared_at), "dd MMM yyyy HH:mm")}`}
                  </p>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

const TENDER_PAGE_SIZE = 10;

export default function CompanyDetailPage() {
  const params = useParams<{ id: string }>();
  const companyId = params.id;

  const [profile, setProfile] = useState<CompanyProfile | null>(null);
  const [tenders, setTenders] = useState<CompanyTender[]>([]);
  const [tenderCount, setTenderCount] = useState(0);
  const [tenderPage, setTenderPage] = useState(1);
  const [flags, setFlags] = useState<CompanyRedFlag[]>([]);
  const [loading, setLoading] = useState(true);
  const [tendersLoading, setTendersLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchProfile = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const [profileRes, flagsRes] = await Promise.all([
        api.get<CompanyProfile>(`/companies/${companyId}/`),
        api.get<PaginatedResponse<CompanyRedFlag>>(`/companies/${companyId}/red-flags/`, { params: { page_size: 100 } })
          .catch(() => ({ data: { results: [] } })),
      ]);
      setProfile(profileRes.data);
      setFlags(flagsRes.data.results ?? []);
    } catch { setError("Failed to load company profile."); }
    finally { setLoading(false); }
  }, [companyId]);

  const fetchTenders = useCallback(async (page: number) => {
    setTendersLoading(true);
    try {
      const { data } = await api.get<PaginatedResponse<CompanyTender>>(
        `/companies/${companyId}/tenders/`, { params: { page, page_size: TENDER_PAGE_SIZE } }
      );
      setTenders(data.results);
      setTenderCount(data.count);
    } catch { /* non-critical */ }
    finally { setTendersLoading(false); }
  }, [companyId]);

  useEffect(() => { fetchProfile(); fetchTenders(1); }, [fetchProfile, fetchTenders]);

  const handleTenderPageChange = useCallback((page: number) => {
    setTenderPage(page);
    fetchTenders(page);
  }, [fetchTenders]);

  const tenderTotalPages = Math.ceil(tenderCount / TENDER_PAGE_SIZE);
  const riskCfg = profile ? RISK_CONFIG[profile.risk_status] : null;

  const card: React.CSSProperties = {
    background: "var(--bg-card)",
    border: "1px solid var(--border)",
    borderRadius: "1rem",
    padding: "1.25rem",
  };

  return (
    <Layout>
      <div className="space-y-5 max-w-5xl">
        <Link href="/companies" style={{ display: "inline-flex", alignItems: "center", gap: "0.25rem", fontSize: "0.8rem", color: "var(--accent)" }} className="hover:underline">
          ← Back to Companies
        </Link>

        {error && (
          <div style={{ borderRadius: "0.75rem", border: "1px solid rgba(239,68,68,0.25)", background: "rgba(239,68,68,0.1)", padding: "0.75rem 1rem", fontSize: "0.875rem", color: "#fca5a5" }}>
            {error}{" "}
            <button onClick={fetchProfile} style={{ textDecoration: "underline", background: "none", border: "none", color: "inherit", cursor: "pointer" }}>Retry</button>
          </div>
        )}

        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
          <div>
            {loading ? (
              <div className="space-y-2">
                <div className="skeleton h-6 w-64" />
                <div className="skeleton h-4 w-40" />
              </div>
            ) : (
              <>
                <h1 style={{ fontSize: "1.2rem", fontWeight: 700, color: "var(--text-primary)", letterSpacing: "-0.01em" }}>
                  {profile?.bidder_name ?? "—"}
                </h1>
                <p style={{ marginTop: "0.25rem", fontFamily: "monospace", fontSize: "0.72rem", color: "var(--text-muted)" }}>
                  {profile?.bidder_id}
                </p>
              </>
            )}
          </div>
          {!loading && profile && riskCfg && (
            <div className="shrink-0 flex flex-col items-start sm:items-end gap-2">
              <span className={riskCfg.badge}>{riskCfg.label}</span>
              {profile.collusion_ring_id && (
                <p style={{ fontSize: "0.72rem", color: "#f87171" }}>
                  Collusion ring: <span style={{ fontFamily: "monospace" }}>{profile.collusion_ring_id}</span>
                </p>
              )}
            </div>
          )}
        </div>

        {/* Metrics grid */}
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
          {loading ? (
            [...Array(6)].map((_, i) => <div key={i} className="skeleton h-24 rounded-2xl" />)
          ) : profile ? (
            <>
              <MetricCard label="Total Bids" value={profile.total_bids} index={0} />
              <MetricCard label="Total Wins" value={profile.total_wins} index={1} />
              <MetricCard
                label="Win Rate"
                value={`${(parseFloat(profile.win_rate) * 100).toFixed(1)}%`}
                highlight={parseFloat(profile.win_rate) > 0.6}
                sub={parseFloat(profile.win_rate) > 0.6 ? "Exceeds 60%" : undefined}
                index={2}
              />
              <MetricCard
                label="Avg Deviation"
                value={`${(parseFloat(profile.avg_bid_deviation) * 100).toFixed(1)}%`}
                sub="from estimate"
                index={3}
              />
              <MetricCard
                label="Highest Score"
                value={profile.highest_fraud_risk_score}
                highlight={profile.highest_fraud_risk_score >= 70}
                index={4}
              />
              <MetricCard
                label="Active Flags"
                value={profile.active_red_flag_count}
                highlight={profile.active_red_flag_count > 0}
                index={5}
              />
            </>
          ) : null}
        </div>

        {/* Advisory */}
        <div style={{ borderRadius: "0.75rem", border: "1px solid rgba(251,191,36,0.2)", background: "rgba(251,191,36,0.06)", padding: "0.625rem 1rem", fontSize: "0.75rem", color: "rgba(251,191,36,0.85)" }}>
          ⚠️ Risk scores are advisory only. Human review is required before initiating any legal or administrative action.
        </div>

        {/* Tender timeline */}
        <div style={card}>
          <TenderTimeline
            tenders={tenders} loading={tendersLoading} totalCount={tenderCount}
            currentPage={tenderPage} totalPages={tenderTotalPages} onPageChange={handleTenderPageChange}
          />
        </div>

        {/* Red flags */}
        <div style={card}>
          <CompanyRedFlagSection flags={flags} loading={loading} />
        </div>

        {!loading && profile && (
          <p style={{ fontSize: "0.7rem", color: "var(--text-muted)", textAlign: "right" }}>
            Profile last updated: {format(new Date(profile.updated_at), "dd MMM yyyy HH:mm")}
          </p>
        )}
      </div>
    </Layout>
  );
}
