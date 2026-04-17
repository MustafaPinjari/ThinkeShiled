"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { format } from "date-fns";
import { motion } from "framer-motion";
import Layout from "@/components/Layout";
import api from "@/lib/api";
import type { CompanyFilters, CompanyProfile, RiskStatus } from "@/types/company";
import type { PaginatedResponse } from "@/types/tender";

const PAGE_SIZE = 20;

// ── Risk status helpers ───────────────────────────────────────────────────────

const RISK_BADGE_CLASS: Record<RiskStatus, string> = {
  LOW: "badge badge-green",
  MEDIUM: "badge badge-amber",
  HIGH_RISK: "badge badge-red",
};

const RISK_LABELS: Record<RiskStatus, string> = {
  LOW: "Low",
  MEDIUM: "Medium",
  HIGH_RISK: "High Risk",
};

function RiskBadge({ status }: { status: RiskStatus }) {
  return (
    <span className={RISK_BADGE_CLASS[status]}>
      {RISK_LABELS[status]}
    </span>
  );
}

// ── Skeleton row ──────────────────────────────────────────────────────────────

function SkeletonRow() {
  return (
    <tr>
      {[...Array(9)].map((_, i) => (
        <td key={i} style={{ padding: "0.75rem 1rem", borderBottom: "1px solid var(--border)" }}>
          <div className="skeleton h-4" style={{ width: i === 0 ? "70%" : "50%" }} />
        </td>
      ))}
    </tr>
  );
}

// ── Pagination ────────────────────────────────────────────────────────────────

interface PaginationProps {
  currentPage: number;
  totalPages: number;
  totalCount: number;
  onPageChange: (page: number) => void;
}

function Pagination({ currentPage, totalPages, totalCount, onPageChange }: PaginationProps) {
  const from = Math.min((currentPage - 1) * PAGE_SIZE + 1, totalCount);
  const to = Math.min(currentPage * PAGE_SIZE, totalCount);

  const btnStyle = (disabled: boolean): React.CSSProperties => ({
    padding: "0.25rem 0.5rem",
    borderRadius: "6px",
    background: "transparent",
    border: "1px solid var(--border)",
    color: disabled ? "var(--text-muted)" : "var(--text-secondary)",
    cursor: disabled ? "not-allowed" : "pointer",
    opacity: disabled ? 0.4 : 1,
    fontSize: "0.8rem",
    transition: "all 0.15s",
  });

  return (
    <div
      className="flex items-center justify-between px-4 py-3"
      style={{ borderTop: "1px solid var(--border)" }}
    >
      <span style={{ color: "var(--text-muted)", fontSize: "0.75rem" }}>
        {totalCount === 0
          ? "No results"
          : `Showing ${from}–${to} of ${totalCount.toLocaleString()}`}
      </span>
      <div className="flex items-center gap-1">
        <button onClick={() => onPageChange(1)} disabled={currentPage === 1} style={btnStyle(currentPage === 1)} aria-label="First page">«</button>
        <button onClick={() => onPageChange(currentPage - 1)} disabled={currentPage === 1} style={btnStyle(currentPage === 1)} aria-label="Previous page">‹</button>
        <span style={{ color: "var(--text-secondary)", fontSize: "0.75rem", padding: "0 0.5rem" }}>
          {currentPage} / {totalPages || 1}
        </span>
        <button onClick={() => onPageChange(currentPage + 1)} disabled={currentPage >= totalPages} style={btnStyle(currentPage >= totalPages)} aria-label="Next page">›</button>
        <button onClick={() => onPageChange(totalPages)} disabled={currentPage >= totalPages} style={btnStyle(currentPage >= totalPages)} aria-label="Last page">»</button>
      </div>
    </div>
  );
}

// ── Filter bar ────────────────────────────────────────────────────────────────

interface FilterBarProps {
  filters: CompanyFilters;
  onChange: (f: Partial<CompanyFilters>) => void;
}

function FilterBar({ filters, onChange }: FilterBarProps) {
  return (
    <div className="flex flex-wrap gap-3 items-end">
      <div className="flex flex-col gap-1">
        <label style={{ fontSize: "0.68rem", fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.07em" }}>
          Company name
        </label>
        <input
          type="text"
          value={filters.bidder_name ?? ""}
          onChange={(e) => onChange({ bidder_name: e.target.value })}
          placeholder="Search…"
          className="ts-input"
          style={{ width: "12rem" }}
        />
      </div>

      <div className="flex flex-col gap-1">
        <label style={{ fontSize: "0.68rem", fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.07em" }}>
          Risk status
        </label>
        <select
          value={filters.risk_status ?? ""}
          onChange={(e) => onChange({ risk_status: e.target.value as RiskStatus | "" })}
          className="ts-input"
        >
          <option value="">All statuses</option>
          <option value="HIGH_RISK">High Risk</option>
          <option value="MEDIUM">Medium</option>
          <option value="LOW">Low</option>
        </select>
      </div>

      {(filters.bidder_name || filters.risk_status) && (
        <button
          onClick={() => onChange({ bidder_name: "", risk_status: "" })}
          style={{ fontSize: "0.75rem", color: "var(--accent)", background: "none", border: "none", cursor: "pointer", alignSelf: "flex-end", paddingBottom: "0.5rem" }}
        >
          Clear filters
        </button>
      )}
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function CompaniesPage() {
  const [companies, setCompanies] = useState<CompanyProfile[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [filters, setFilters] = useState<CompanyFilters>({ page: 1, page_size: PAGE_SIZE });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchCompanies = useCallback(async (f: CompanyFilters) => {
    setLoading(true);
    setError(null);
    try {
      const params: Record<string, string | number> = {
        page: f.page ?? 1,
        page_size: f.page_size ?? PAGE_SIZE,
      };
      if (f.risk_status) params.risk_status = f.risk_status;
      if (f.bidder_name) params.bidder_name = f.bidder_name;

      const { data } = await api.get<PaginatedResponse<CompanyProfile>>(
        "/companies/",
        { params }
      );
      setCompanies(data.results);
      setTotalCount(data.count);
    } catch {
      setError("Failed to load companies. Please try again.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchCompanies(filters);
  }, [fetchCompanies]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleFilterChange = useCallback(
    (newFilters: Partial<CompanyFilters>) => {
      const updated: CompanyFilters = { ...filters, ...newFilters, page: 1 };
      setFilters(updated);
      fetchCompanies(updated);
    },
    [filters, fetchCompanies]
  );

  const handlePageChange = useCallback(
    (page: number) => {
      const updated = { ...filters, page };
      setFilters(updated);
      fetchCompanies(updated);
    },
    [filters, fetchCompanies]
  );

  const totalPages = Math.ceil(totalCount / PAGE_SIZE);

  const thStyle: React.CSSProperties = {
    padding: "0.625rem 1rem",
    background: "rgba(255,255,255,0.02)",
    color: "var(--text-muted)",
    fontSize: "0.68rem",
    fontWeight: 600,
    letterSpacing: "0.07em",
    textTransform: "uppercase",
    borderBottom: "1px solid var(--border)",
    whiteSpace: "nowrap",
  };

  const tdStyle: React.CSSProperties = {
    padding: "0.75rem 1rem",
    borderBottom: "1px solid var(--border)",
    color: "var(--text-secondary)",
    fontSize: "0.875rem",
  };

  return (
    <Layout>
      <div className="space-y-6">
        {/* Header */}
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.25 }}>
          <div>
            <h1 style={{ fontSize: "1.2rem", fontWeight: 700, color: "var(--text-primary)", letterSpacing: "-0.02em" }}>
              Companies
            </h1>
            <p style={{ marginTop: "0.25rem", fontSize: "0.78rem", color: "var(--text-muted)" }}>
              Bidder risk profiles and behavioral metrics
            </p>
          </div>
        </motion.div>

        {/* Filters */}
        <FilterBar filters={filters} onChange={handleFilterChange} />

        {/* Error */}
        {error && (
          <div style={{ borderRadius: "0.5rem", border: "1px solid rgba(239,68,68,0.3)", background: "rgba(239,68,68,0.08)", padding: "0.75rem 1rem", fontSize: "0.875rem", color: "#f87171" }}>
            {error}{" "}
            <button
              onClick={() => fetchCompanies(filters)}
              style={{ textDecoration: "underline", background: "none", border: "none", color: "inherit", cursor: "pointer" }}
            >
              Retry
            </button>
          </div>
        )}

        {/* Table */}
        <div
          className="rounded-2xl overflow-hidden"
          style={{ background: "var(--bg-card)", border: "1px solid var(--border)" }}
        >
          {/* Advisory disclaimer */}
          <div style={{ padding: "0.5rem 1rem", background: "rgba(251,191,36,0.08)", borderBottom: "1px solid rgba(251,191,36,0.2)", fontSize: "0.75rem", color: "rgba(251,191,36,0.9)" }}>
            ⚠️ Risk scores are advisory only. Human review is required before initiating any legal or administrative action.
          </div>

          <div className="overflow-x-auto">
            <table className="ts-table">
              <thead>
                <tr>
                  <th style={thStyle}>Company</th>
                  <th style={{ ...thStyle, textAlign: "right" }}>Total Bids</th>
                  <th style={{ ...thStyle, textAlign: "right" }}>Wins</th>
                  <th style={{ ...thStyle, textAlign: "right" }}>Win Rate</th>
                  <th style={{ ...thStyle, textAlign: "right" }}>Avg Deviation</th>
                  <th style={{ ...thStyle, textAlign: "right" }}>Highest Score</th>
                  <th style={{ ...thStyle, textAlign: "right" }}>Active Flags</th>
                  <th style={thStyle}>Risk Status</th>
                  <th style={{ ...thStyle, whiteSpace: "nowrap" }}>Updated</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  [...Array(10)].map((_, i) => <SkeletonRow key={i} />)
                ) : companies.length === 0 ? (
                  <tr>
                    <td colSpan={9} style={{ padding: "3rem 1rem", textAlign: "center", color: "var(--text-muted)", fontSize: "0.875rem" }}>
                      No companies found.
                    </td>
                  </tr>
                ) : (
                  companies.map((company) => (
                    <tr key={company.id}>
                      <td style={tdStyle}>
                        <Link
                          href={`/companies/${company.id}`}
                          style={{ color: "var(--accent)", fontWeight: 500 }}
                          className="hover:underline"
                        >
                          {company.bidder_name}
                        </Link>
                        <p style={{ fontSize: "0.7rem", color: "var(--text-muted)", fontFamily: "monospace", marginTop: "0.125rem" }}>
                          {company.bidder_id}
                        </p>
                      </td>
                      <td style={{ ...tdStyle, textAlign: "right" }}>{company.total_bids}</td>
                      <td style={{ ...tdStyle, textAlign: "right" }}>{company.total_wins}</td>
                      <td style={{ ...tdStyle, textAlign: "right" }}>
                        {(parseFloat(company.win_rate) * 100).toFixed(1)}%
                      </td>
                      <td style={{ ...tdStyle, textAlign: "right" }}>
                        {(parseFloat(company.avg_bid_deviation) * 100).toFixed(1)}%
                      </td>
                      <td style={{ ...tdStyle, textAlign: "right" }}>
                        <span
                          className={
                            company.highest_fraud_risk_score >= 70
                              ? "badge badge-red"
                              : company.highest_fraud_risk_score >= 40
                              ? "badge badge-amber"
                              : "badge badge-green"
                          }
                          style={{ fontWeight: 600 }}
                        >
                          {company.highest_fraud_risk_score}
                        </span>
                      </td>
                      <td style={{ ...tdStyle, textAlign: "right" }}>
                        {company.active_red_flag_count > 0 ? (
                          <span className="badge badge-red" style={{ fontSize: "0.65rem" }}>
                            {company.active_red_flag_count}
                          </span>
                        ) : (
                          <span style={{ color: "var(--text-muted)", fontSize: "0.75rem" }}>—</span>
                        )}
                      </td>
                      <td style={tdStyle}>
                        <RiskBadge status={company.risk_status} />
                        {company.collusion_ring_id && (
                          <p style={{ fontSize: "0.7rem", color: "#f87171", marginTop: "0.125rem" }}>
                            Ring: {company.collusion_ring_id}
                          </p>
                        )}
                      </td>
                      <td style={{ ...tdStyle, fontSize: "0.75rem", color: "var(--text-muted)", whiteSpace: "nowrap" }}>
                        {format(new Date(company.updated_at), "dd MMM yyyy")}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          <Pagination
            currentPage={filters.page ?? 1}
            totalPages={totalPages}
            totalCount={totalCount}
            onPageChange={handlePageChange}
          />
        </div>
      </div>
    </Layout>
  );
}
