"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import AgencyLayout from "@/components/AgencyLayout";
import RiskBadge from "@/components/ui/RiskBadge";
import { useAuth } from "@/contexts/AuthContext";
import {
  getTenders,
  type TenderSubmission,
  type TenderFilters,
  type SubmissionStatus,
} from "@/services/agencies";
import api from "@/lib/api";
import type { PaginatedResponse } from "@/types/tender";

// ── Constants ─────────────────────────────────────────────────────────────────

const AGENCY_ROLES = ["AGENCY_ADMIN", "AGENCY_OFFICER", "REVIEWER", "GOVERNMENT_AUDITOR"] as const;
const PAGE_SIZE = 20;
const ALERT_POLL_INTERVAL_MS = 30_000; // 30 seconds

const GEM_CATEGORIES = [
  "IT", "Infrastructure", "Healthcare", "Education", "Defence",
  "Agriculture", "Energy", "Transport", "Finance", "Other",
];

const STATUS_OPTIONS: SubmissionStatus[] = [
  "DRAFT", "SUBMITTED", "UNDER_REVIEW", "FLAGGED", "CLEARED",
];

// ── KPI Dashboard Stats ───────────────────────────────────────────────────────

interface AgencyStats {
  total: number;
  highRisk: number;
  activeAlerts: number;
  underReview: number;
}

// ── Alert notification type ───────────────────────────────────────────────────

interface AlertNotification {
  id: number;
  title: string;
  alert_type: string;
  fraud_risk_score: number;
  created_at: string;
  is_read: boolean;
}

// ── KPI Card ──────────────────────────────────────────────────────────────────

function KpiCard({
  label, value, loading, color, sub,
}: {
  label: string; value: number | null; loading: boolean; color?: string; sub?: string;
}) {
  return (
    <motion.div
      className="kpi-card"
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
    >
      <p className="kpi-label">{label}</p>
      {loading ? (
        <div className="skeleton" style={{ height: 32, width: 80 }} />
      ) : (
        <span className="kpi-value" style={color ? { color } : {}}>
          {value !== null ? value.toLocaleString() : "—"}
        </span>
      )}
      {sub && <p style={{ fontSize: "0.68rem", color: "var(--text-muted)", marginTop: "0.375rem" }}>{sub}</p>}
    </motion.div>
  );
}

// ── Status Badge ──────────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: SubmissionStatus }) {
  const map: Record<SubmissionStatus, string> = {
    DRAFT: "badge-gray",
    SUBMITTED: "badge-blue",
    UNDER_REVIEW: "badge-amber",
    FLAGGED: "badge-red",
    CLEARED: "badge-green",
  };
  return <span className={`badge ${map[status] ?? "badge-gray"}`}>{status.replace("_", " ")}</span>;
}

// ── Alert Toast ───────────────────────────────────────────────────────────────

function AlertToast({
  alerts, onDismiss,
}: {
  alerts: AlertNotification[]; onDismiss: (id: number) => void;
}) {
  if (alerts.length === 0) return null;
  return (
    <div
      style={{
        position: "fixed", bottom: "1.5rem", right: "1.5rem",
        display: "flex", flexDirection: "column", gap: "0.5rem",
        zIndex: 100, maxWidth: 360,
      }}
      role="alert"
      aria-live="polite"
    >
      {alerts.slice(0, 3).map((alert) => (
        <motion.div
          key={alert.id}
          initial={{ opacity: 0, x: 40 }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0, x: 40 }}
          style={{
            background: "var(--bg-elevated)",
            border: "1px solid rgba(239,68,68,0.3)",
            borderRadius: 12,
            padding: "0.875rem 1rem",
            boxShadow: "0 8px 32px rgba(0,0,0,0.5)",
          }}
        >
          <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: "0.5rem" }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <p style={{ fontSize: "0.75rem", fontWeight: 600, color: "var(--text-primary)", marginBottom: "0.25rem" }}>
                🚨 New Alert
              </p>
              <p style={{ fontSize: "0.72rem", color: "var(--text-secondary)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {alert.title}
              </p>
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginTop: "0.375rem" }}>
                <RiskBadge score={alert.fraud_risk_score} />
                <span style={{ fontSize: "0.65rem", color: "var(--text-muted)" }}>
                  {new Date(alert.created_at).toLocaleTimeString()}
                </span>
              </div>
            </div>
            <button
              onClick={() => onDismiss(alert.id)}
              style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-muted)", padding: 2, flexShrink: 0 }}
              aria-label="Dismiss alert"
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
              </svg>
            </button>
          </div>
        </motion.div>
      ))}
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function AgencyDashboardPage() {
  const { role } = useAuth();

  // Tender list state
  const [tenders, setTenders] = useState<TenderSubmission[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters & sort
  const [statusFilter, setStatusFilter] = useState<SubmissionStatus | "">("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [ordering, setOrdering] = useState<TenderFilters["ordering"]>("-created_at");
  const [page, setPage] = useState(1);

  // KPI stats
  const [stats, setStats] = useState<AgencyStats | null>(null);
  const [statsLoading, setStatsLoading] = useState(true);

  // Alert notifications (for AGENCY_ADMIN and AGENCY_OFFICER)
  const [newAlerts, setNewAlerts] = useState<AlertNotification[]>([]);
  const lastAlertIdRef = useRef<number | null>(null);
  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const canSeeAlerts = role === "AGENCY_ADMIN" || role === "AGENCY_OFFICER";
  const canCreateTender = role === "AGENCY_ADMIN" || role === "AGENCY_OFFICER";

  // ── Fetch tenders ──────────────────────────────────────────────────────────

  const fetchTenders = useCallback(async (filters: TenderFilters) => {
    setLoading(true);
    setError(null);
    try {
      const data = await getTenders(filters);
      setTenders(data.results);
      setTotalCount(data.count);
    } catch {
      setError("Failed to load tenders.");
    } finally {
      setLoading(false);
    }
  }, []);

  // ── Compute KPI stats from tender list ────────────────────────────────────

  const fetchStats = useCallback(async () => {
    setStatsLoading(true);
    try {
      // Fetch all tenders without pagination to compute stats
      const [allData, alertsData] = await Promise.all([
        getTenders({ page_size: 1000 }),
        canSeeAlerts
          ? api.get<PaginatedResponse<AlertNotification>>("/api/v1/alerts/", { params: { page_size: 100, is_read: false } }).catch(() => null)
          : Promise.resolve(null),
      ]);

      const all = allData.results;
      const highRisk = all.filter(t => t.fraud_risk_score !== null && t.fraud_risk_score >= 70).length;
      const underReview = all.filter(t => t.status === "UNDER_REVIEW").length;
      const activeAlerts = alertsData
        ? (alertsData as { data: PaginatedResponse<AlertNotification> }).data?.count ?? 0
        : 0;

      setStats({
        total: allData.count,
        highRisk,
        activeAlerts,
        underReview,
      });
    } catch {
      // non-critical
    } finally {
      setStatsLoading(false);
    }
  }, [canSeeAlerts]);

  // ── Alert polling ──────────────────────────────────────────────────────────

  const pollAlerts = useCallback(async () => {
    if (!canSeeAlerts) return;
    try {
      const { data } = await api.get<PaginatedResponse<AlertNotification>>(
        "/api/v1/alerts/",
        { params: { page_size: 10, ordering: "-created_at" } }
      );
      const latest = data.results;
      if (latest.length === 0) return;

      const latestId = latest[0].id;
      if (lastAlertIdRef.current === null) {
        lastAlertIdRef.current = latestId;
        return;
      }

      const newOnes = latest.filter(a => a.id > (lastAlertIdRef.current ?? 0) && !a.is_read);
      if (newOnes.length > 0) {
        lastAlertIdRef.current = latestId;
        setNewAlerts(prev => [...newOnes, ...prev].slice(0, 5));
        // Refresh stats
        fetchStats();
      }
    } catch {
      // non-critical
    }
  }, [canSeeAlerts, fetchStats]);

  // ── Effects ────────────────────────────────────────────────────────────────

  useEffect(() => {
    const filters: TenderFilters = {
      status: statusFilter || undefined,
      category: categoryFilter || undefined,
      date_from: dateFrom || undefined,
      date_to: dateTo || undefined,
      ordering,
      page,
      page_size: PAGE_SIZE,
    };
    fetchTenders(filters);
  }, [fetchTenders, statusFilter, categoryFilter, dateFrom, dateTo, ordering, page]);

  useEffect(() => {
    fetchStats();
  }, [fetchStats]);

  useEffect(() => {
    if (!canSeeAlerts) return;
    // Initial poll to set baseline
    pollAlerts();
    pollIntervalRef.current = setInterval(pollAlerts, ALERT_POLL_INTERVAL_MS);
    return () => {
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
    };
  }, [canSeeAlerts, pollAlerts]);

  // ── Handlers ───────────────────────────────────────────────────────────────

  function handleFilterChange() {
    setPage(1);
  }

  function handleDismissAlert(id: number) {
    setNewAlerts(prev => prev.filter(a => a.id !== id));
    // Mark as read
    api.post(`/api/v1/alerts/${id}/read/`).catch(() => {});
  }

  const totalPages = Math.ceil(totalCount / PAGE_SIZE);

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <AgencyLayout>
      <div className="space-y-5">

        {/* Page header */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "0.75rem" }}>
          <div>
            <h1 style={{ fontSize: "1.1rem", fontWeight: 700, color: "var(--text-primary)", letterSpacing: "-0.02em" }}>
              Agency Dashboard
            </h1>
            <p style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginTop: 2 }}>
              Monitor your agency&apos;s tender submissions and fraud detection status
            </p>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <button
              className="ts-btn ts-btn-ghost"
              style={{ fontSize: "0.75rem" }}
              onClick={() => { fetchTenders({ page, page_size: PAGE_SIZE, ordering }); fetchStats(); }}
            >
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/>
                <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
              </svg>
              Refresh
            </button>
            {canCreateTender && (
              <Link href="/agency/tenders/new" className="ts-btn ts-btn-primary" style={{ fontSize: "0.75rem" }}>
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
                </svg>
                Create Tender
              </Link>
            )}
          </div>
        </div>

        {/* KPI row */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: "0.75rem" }}>
          <KpiCard label="Total Submissions" value={stats?.total ?? null} loading={statsLoading} sub="All tender submissions" />
          <KpiCard label="High Risk" value={stats?.highRisk ?? null} loading={statsLoading} color="#f87171" sub="Score ≥ 70" />
          <KpiCard label="Active Alerts" value={stats?.activeAlerts ?? null} loading={statsLoading} color="#fbbf24" sub="Unread alerts" />
          <KpiCard label="Under Review" value={stats?.underReview ?? null} loading={statsLoading} color="#60a5fa" sub="Awaiting review" />
        </div>

        {/* Filters */}
        <div
          style={{
            background: "var(--bg-card)",
            borderRadius: 12,
            padding: "1rem",
            display: "flex",
            flexWrap: "wrap",
            gap: "0.75rem",
            alignItems: "flex-end",
          }}
        >
          {/* Status filter */}
          <div style={{ display: "flex", flexDirection: "column", gap: "0.375rem", minWidth: 140 }}>
            <label style={{ fontSize: "0.65rem", fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.06em" }}>
              Status
            </label>
            <select
              value={statusFilter}
              onChange={(e) => { setStatusFilter(e.target.value as SubmissionStatus | ""); handleFilterChange(); }}
              className="ts-input"
              style={{ height: "2rem", fontSize: "0.78rem" }}
            >
              <option value="">All statuses</option>
              {STATUS_OPTIONS.map(s => (
                <option key={s} value={s}>{s.replace("_", " ")}</option>
              ))}
            </select>
          </div>

          {/* Category filter */}
          <div style={{ display: "flex", flexDirection: "column", gap: "0.375rem", minWidth: 140 }}>
            <label style={{ fontSize: "0.65rem", fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.06em" }}>
              Category
            </label>
            <select
              value={categoryFilter}
              onChange={(e) => { setCategoryFilter(e.target.value); handleFilterChange(); }}
              className="ts-input"
              style={{ height: "2rem", fontSize: "0.78rem" }}
            >
              <option value="">All categories</option>
              {GEM_CATEGORIES.map(c => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </div>

          {/* Date from */}
          <div style={{ display: "flex", flexDirection: "column", gap: "0.375rem", minWidth: 140 }}>
            <label style={{ fontSize: "0.65rem", fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.06em" }}>
              From Date
            </label>
            <input
              type="date"
              value={dateFrom}
              onChange={(e) => { setDateFrom(e.target.value); handleFilterChange(); }}
              className="ts-input"
              style={{ height: "2rem", fontSize: "0.78rem" }}
            />
          </div>

          {/* Date to */}
          <div style={{ display: "flex", flexDirection: "column", gap: "0.375rem", minWidth: 140 }}>
            <label style={{ fontSize: "0.65rem", fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.06em" }}>
              To Date
            </label>
            <input
              type="date"
              value={dateTo}
              onChange={(e) => { setDateTo(e.target.value); handleFilterChange(); }}
              className="ts-input"
              style={{ height: "2rem", fontSize: "0.78rem" }}
            />
          </div>

          {/* Sort */}
          <div style={{ display: "flex", flexDirection: "column", gap: "0.375rem", minWidth: 180 }}>
            <label style={{ fontSize: "0.65rem", fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.06em" }}>
              Sort By
            </label>
            <select
              value={ordering}
              onChange={(e) => { setOrdering(e.target.value as TenderFilters["ordering"]); handleFilterChange(); }}
              className="ts-input"
              style={{ height: "2rem", fontSize: "0.78rem" }}
            >
              <option value="-created_at">Submission Date (Newest)</option>
              <option value="created_at">Submission Date (Oldest)</option>
              <option value="-estimated_value">Estimated Value (High→Low)</option>
              <option value="estimated_value">Estimated Value (Low→High)</option>
              <option value="-fraud_risk_score">Risk Score (High→Low)</option>
              <option value="fraud_risk_score">Risk Score (Low→High)</option>
            </select>
          </div>

          {/* Clear filters */}
          {(statusFilter || categoryFilter || dateFrom || dateTo) && (
            <button
              className="ts-btn ts-btn-ghost"
              style={{ fontSize: "0.75rem", height: "2rem" }}
              onClick={() => {
                setStatusFilter("");
                setCategoryFilter("");
                setDateFrom("");
                setDateTo("");
                setPage(1);
              }}
            >
              Clear Filters
            </button>
          )}
        </div>

        {/* Tender list */}
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.75rem" }}>
            <div>
              <p className="section-title">Tender Submissions</p>
              <p className="section-sub">
                {loading ? "Loading…" : `${totalCount.toLocaleString()} tender${totalCount !== 1 ? "s" : ""}`}
              </p>
            </div>
          </div>

          <div style={{ background: "var(--bg-card)", borderRadius: 12, overflow: "hidden", border: "1px solid var(--border)" }}>
            {error ? (
              <div style={{ padding: "1.5rem", textAlign: "center" }}>
                <p style={{ color: "#f87171", fontSize: "0.82rem", marginBottom: "0.75rem" }}>{error}</p>
                <button
                  className="ts-btn ts-btn-ghost"
                  style={{ fontSize: "0.75rem" }}
                  onClick={() => fetchTenders({ page, page_size: PAGE_SIZE, ordering })}
                >
                  Retry
                </button>
              </div>
            ) : (
              <>
                <div style={{ overflowX: "auto" }}>
                  <table className="ts-table">
                    <thead>
                      <tr>
                        <th>Tender ID</th>
                        <th>Title</th>
                        <th>Category</th>
                        <th style={{ textAlign: "right" }}>Est. Value (INR)</th>
                        <th>Status</th>
                        <th style={{ textAlign: "right" }}>Risk Score</th>
                        <th>Submission Date</th>
                        <th></th>
                      </tr>
                    </thead>
                    <tbody>
                      {loading ? (
                        [...Array(8)].map((_, i) => (
                          <tr key={i}>
                            {[...Array(8)].map((__, j) => (
                              <td key={j}>
                                <div className="skeleton" style={{ height: 14, width: j === 1 ? "80%" : "60%" }} />
                              </td>
                            ))}
                          </tr>
                        ))
                      ) : tenders.length === 0 ? (
                        <tr>
                          <td colSpan={8} style={{ padding: "3rem 1rem", textAlign: "center", color: "var(--text-muted)", fontSize: "0.82rem" }}>
                            No tender submissions found.
                            {canCreateTender && (
                              <>
                                {" "}
                                <Link href="/agency/tenders/new" style={{ color: "var(--accent)", textDecoration: "underline" }}>
                                  Create your first tender
                                </Link>
                              </>
                            )}
                          </td>
                        </tr>
                      ) : (
                        tenders.map((tender) => (
                          <tr key={tender.id}>
                            <td className="col-id" style={{ fontFamily: "monospace", fontSize: "0.75rem" }}>
                              #{tender.id}
                            </td>
                            <td style={{ maxWidth: 220 }}>
                              <Link
                                href={`/agency/tenders/${tender.id}`}
                                style={{ color: "var(--text-primary)", fontWeight: 500, fontSize: "0.82rem" }}
                                className="hover:underline line-clamp-2"
                              >
                                {tender.title}
                              </Link>
                              <p style={{ fontSize: "0.68rem", color: "var(--text-muted)", marginTop: 2, fontFamily: "monospace" }}>
                                {tender.tender_ref}
                              </p>
                            </td>
                            <td>
                              <span className="badge badge-gray" style={{ fontSize: "0.65rem" }}>{tender.category}</span>
                            </td>
                            <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums", fontSize: "0.82rem" }}>
                              ₹{parseFloat(tender.estimated_value).toLocaleString("en-IN")}
                            </td>
                            <td>
                              <StatusBadge status={tender.status} />
                            </td>
                            <td style={{ textAlign: "right" }}>
                              <RiskBadge score={tender.fraud_risk_score} />
                            </td>
                            <td style={{ fontSize: "0.75rem", color: "var(--text-muted)", whiteSpace: "nowrap" }}>
                              {new Date(tender.created_at).toLocaleDateString("en-IN", {
                                day: "2-digit", month: "short", year: "numeric",
                              })}
                            </td>
                            <td>
                              <Link
                                href={`/agency/tenders/${tender.id}`}
                                className="ts-action-btn"
                                aria-label={`View tender ${tender.id}`}
                              >
                                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                  <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                                  <circle cx="12" cy="12" r="3"/>
                                </svg>
                              </Link>
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>

                {/* Pagination */}
                {totalPages > 1 && (
                  <div
                    style={{
                      display: "flex", alignItems: "center", justifyContent: "space-between",
                      padding: "0.75rem 1rem", borderTop: "1px solid var(--border)",
                    }}
                  >
                    <span style={{ color: "var(--text-muted)", fontSize: "0.75rem" }}>
                      {Math.min((page - 1) * PAGE_SIZE + 1, totalCount)}–{Math.min(page * PAGE_SIZE, totalCount)} of {totalCount.toLocaleString()}
                    </span>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.25rem" }}>
                      {[
                        { label: "«", target: 1, disabled: page === 1 },
                        { label: "‹", target: page - 1, disabled: page === 1 },
                        { label: "›", target: page + 1, disabled: page >= totalPages },
                        { label: "»", target: totalPages, disabled: page >= totalPages },
                      ].map(({ label, target, disabled }) => (
                        <button
                          key={label}
                          onClick={() => setPage(target)}
                          disabled={disabled}
                          style={{
                            padding: "0.25rem 0.5rem", borderRadius: 6,
                            background: "transparent", border: "1px solid var(--border)",
                            color: disabled ? "var(--text-muted)" : "var(--text-secondary)",
                            cursor: disabled ? "not-allowed" : "pointer",
                            opacity: disabled ? 0.4 : 1, fontSize: "0.8rem",
                          }}
                        >
                          {label}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        </motion.div>
      </div>

      {/* Alert notifications */}
      {canSeeAlerts && (
        <AlertToast alerts={newAlerts} onDismiss={handleDismissAlert} />
      )}
    </AgencyLayout>
  );
}
