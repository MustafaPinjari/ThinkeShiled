"use client";

import React, { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { motion } from "framer-motion";
import AgencyLayout from "@/components/AgencyLayout";
import RiskBadge from "@/components/ui/RiskBadge";
import { useAuth } from "@/contexts/AuthContext";
import {
  getCrossAgencyTenders,
  type TenderSubmission,
  type SubmissionStatus,
  type CrossAgencyTenderFilters,
} from "@/services/agencies";

// ── Constants ─────────────────────────────────────────────────────────────────

const PAGE_SIZE = 25;

const GEM_CATEGORIES = [
  "IT", "Infrastructure", "Healthcare", "Education", "Defence",
  "Agriculture", "Energy", "Transport", "Finance", "Other",
];

const STATUS_OPTIONS: SubmissionStatus[] = [
  "DRAFT", "SUBMITTED", "UNDER_REVIEW", "FLAGGED", "CLEARED",
];

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

// ── Page ──────────────────────────────────────────────────────────────────────

export default function CrossAgencyTendersPage() {
  const { role } = useAuth();
  const router = useRouter();

  // Only GOVERNMENT_AUDITOR and ADMIN can access this page
  useEffect(() => {
    if (role && role !== "GOVERNMENT_AUDITOR" && role !== "ADMIN") {
      router.replace("/agency/dashboard");
    }
  }, [role, router]);

  const [tenders, setTenders] = useState<TenderSubmission[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [statusFilter, setStatusFilter] = useState<SubmissionStatus | "">("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [agencyFilter, setAgencyFilter] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [ordering, setOrdering] = useState("-created_at");
  const [page, setPage] = useState(1);

  const fetchTenders = useCallback(async (filters: CrossAgencyTenderFilters) => {
    setLoading(true);
    setError(null);
    try {
      const data = await getCrossAgencyTenders(filters);
      setTenders(data.results);
      setTotalCount(data.count);
    } catch {
      setError("Failed to load tenders.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const filters: CrossAgencyTenderFilters = {
      status: statusFilter || undefined,
      category: categoryFilter || undefined,
      agency_id: agencyFilter || undefined,
      date_from: dateFrom || undefined,
      date_to: dateTo || undefined,
      ordering,
      page,
      page_size: PAGE_SIZE,
    };
    fetchTenders(filters);
  }, [fetchTenders, statusFilter, categoryFilter, agencyFilter, dateFrom, dateTo, ordering, page]);

  function handleFilterChange() {
    setPage(1);
  }

  const totalPages = Math.ceil(totalCount / PAGE_SIZE);

  if (role !== "GOVERNMENT_AUDITOR" && role !== "ADMIN") {
    return null;
  }

  return (
    <AgencyLayout>
      <div className="space-y-5">
        {/* Header */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "0.75rem" }}>
          <div>
            <h1 style={{ fontSize: "1.1rem", fontWeight: 700, color: "var(--text-primary)", letterSpacing: "-0.02em" }}>
              Cross-Agency Tender List
            </h1>
            <p style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginTop: 2 }}>
              Read-only view of all tender submissions across all agencies
            </p>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            {/* READ ONLY badge — no write actions for GOVERNMENT_AUDITOR */}
            <div style={{ padding: "0.375rem 0.75rem", borderRadius: 8, background: "rgba(168,85,247,0.1)", border: "1px solid rgba(168,85,247,0.2)" }}>
              <span style={{ fontSize: "0.68rem", color: "#c084fc", fontWeight: 600, letterSpacing: "0.04em" }}>
                READ ONLY — No write actions available
              </span>
            </div>
            <button
              className="ts-btn ts-btn-ghost"
              style={{ fontSize: "0.75rem" }}
              onClick={() => fetchTenders({ page, page_size: PAGE_SIZE, ordering })}
            >
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/>
                <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
              </svg>
              Refresh
            </button>
          </div>
        </div>

        {/* Filters */}
        <div
          style={{
            background: "var(--bg-card)", borderRadius: 12, padding: "1rem",
            display: "flex", flexWrap: "wrap", gap: "0.75rem", alignItems: "flex-end",
          }}
        >
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

          <div style={{ display: "flex", flexDirection: "column", gap: "0.375rem", minWidth: 160 }}>
            <label style={{ fontSize: "0.65rem", fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.06em" }}>
              Agency ID
            </label>
            <input
              type="text"
              value={agencyFilter}
              onChange={(e) => { setAgencyFilter(e.target.value); handleFilterChange(); }}
              placeholder="Filter by agency ID"
              className="ts-input"
              style={{ height: "2rem", fontSize: "0.78rem" }}
            />
          </div>

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

          <div style={{ display: "flex", flexDirection: "column", gap: "0.375rem", minWidth: 180 }}>
            <label style={{ fontSize: "0.65rem", fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.06em" }}>
              Sort By
            </label>
            <select
              value={ordering}
              onChange={(e) => { setOrdering(e.target.value); handleFilterChange(); }}
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

          {(statusFilter || categoryFilter || agencyFilter || dateFrom || dateTo) && (
            <button
              className="ts-btn ts-btn-ghost"
              style={{ fontSize: "0.75rem", height: "2rem" }}
              onClick={() => {
                setStatusFilter("");
                setCategoryFilter("");
                setAgencyFilter("");
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
              <p className="section-title">All Tender Submissions</p>
              <p className="section-sub">
                {loading ? "Loading…" : `${totalCount.toLocaleString()} tender${totalCount !== 1 ? "s" : ""} across all agencies`}
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
                        <th>Agency Name</th>
                        <th>Agency ID</th>
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
                        [...Array(10)].map((_, i) => (
                          <tr key={i}>
                            {[...Array(10)].map((__, j) => (
                              <td key={j}>
                                <div className="skeleton" style={{ height: 14, width: j === 1 ? "80%" : "60%" }} />
                              </td>
                            ))}
                          </tr>
                        ))
                      ) : tenders.length === 0 ? (
                        <tr>
                          <td colSpan={10} style={{ padding: "3rem 1rem", textAlign: "center", color: "var(--text-muted)", fontSize: "0.82rem" }}>
                            No tender submissions found.
                          </td>
                        </tr>
                      ) : (
                        tenders.map((tender) => (
                          <tr key={tender.id}>
                            <td className="col-id" style={{ fontFamily: "monospace", fontSize: "0.75rem" }}>
                              #{tender.id}
                            </td>
                            <td style={{ maxWidth: 200 }}>
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
                            <td style={{ fontSize: "0.78rem", maxWidth: 160 }}>
                              <span className="line-clamp-1">{tender.agency_name ?? "—"}</span>
                            </td>
                            <td style={{ fontSize: "0.72rem", color: "var(--text-muted)", fontFamily: "monospace" }}>
                              {typeof tender.agency === "string" ? tender.agency.slice(0, 8) + "…" : tender.agency}
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
                              {/* View only — no edit/delete/submit/clear actions for GOVERNMENT_AUDITOR */}
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
    </AgencyLayout>
  );
}
