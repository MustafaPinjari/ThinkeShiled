"use client";

import Link from "next/link";
import React from "react";
import { format } from "date-fns";
import { motion } from "framer-motion";
import type { TenderListItem } from "@/types/tender";

// ── Avatar gradient by index ──────────────────────────────────────────────────
const GRADIENTS = [
  "linear-gradient(135deg, #6366f1, #8b5cf6)",
  "linear-gradient(135deg, #3b82f6, #06b6d4)",
  "linear-gradient(135deg, #10b981, #3b82f6)",
  "linear-gradient(135deg, #f59e0b, #ef4444)",
  "linear-gradient(135deg, #ec4899, #8b5cf6)",
  "linear-gradient(135deg, #14b8a6, #6366f1)",
  "linear-gradient(135deg, #f97316, #eab308)",
  "linear-gradient(135deg, #06b6d4, #10b981)",
];

function getGradient(str: string) {
  let hash = 0;
  for (let i = 0; i < str.length; i++) hash = str.charCodeAt(i) + ((hash << 5) - hash);
  return GRADIENTS[Math.abs(hash) % GRADIENTS.length];
}

function getInitials(name: string) {
  return name.split(" ").map(w => w[0]).join("").slice(0, 2).toUpperCase();
}

// ── Score badge ───────────────────────────────────────────────────────────────
function ScoreBadge({ score }: { score: number | null }) {
  if (score === null || score === undefined) return <span className="badge badge-gray">N/A</span>;
  if (score >= 70) return <span className="bg-red-100 text-red-800 score-high">{score}</span>;
  if (score >= 40) return <span className="bg-amber-100 text-amber-800 score-medium">{score}</span>;
  return <span className="bg-green-100 text-green-800 score-low">{score}</span>;
}

// ── Sort icon ─────────────────────────────────────────────────────────────────
function SortIcon({ field, ordering }: { field: string; ordering: string }) {
  const isActive = ordering === field || ordering === `-${field}`;
  const isDesc = ordering === `-${field}`;
  return (
    <span style={{ marginLeft: 4, fontSize: "0.65rem", color: isActive ? "var(--accent)" : "var(--text-muted)", opacity: isActive ? 1 : 0.5 }}>
      {isActive ? (isDesc ? "↓" : "↑") : "↕"}
    </span>
  );
}

function sortToggle(field: string, current: string) {
  return current === field ? `-${field}` : field;
}

// ── Skeleton ──────────────────────────────────────────────────────────────────
function SkeletonRow() {
  return (
    <tr className="animate-pulse">
      <td style={{ padding: "0.875rem 1rem", borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
        <div className="skeleton" style={{ height: 14, width: 90 }} />
      </td>
      <td style={{ padding: "0.875rem 1rem", borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.625rem" }}>
          <div className="skeleton" style={{ width: 32, height: 32, borderRadius: "50%", flexShrink: 0 }} />
          <div>
            <div className="skeleton" style={{ height: 12, width: 120, marginBottom: 4 }} />
            <div className="skeleton" style={{ height: 10, width: 80 }} />
          </div>
        </div>
      </td>
      <td style={{ padding: "0.875rem 1rem", borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
        <div className="skeleton" style={{ height: 12, width: 80 }} />
      </td>
      <td style={{ padding: "0.875rem 1rem", borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
        <div className="skeleton" style={{ height: 12, width: 70 }} />
      </td>
      <td style={{ padding: "0.875rem 1rem", borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
        <div className="skeleton" style={{ height: 22, width: 44, borderRadius: 6 }} />
      </td>
      <td style={{ padding: "0.875rem 1rem", borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
        <div className="skeleton" style={{ height: 22, width: 28, borderRadius: 6 }} />
      </td>
      <td style={{ padding: "0.875rem 1rem", borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
        <div style={{ display: "flex", gap: 4 }}>
          <div className="skeleton" style={{ width: 28, height: 28, borderRadius: 6 }} />
          <div className="skeleton" style={{ width: 28, height: 28, borderRadius: 6 }} />
        </div>
      </td>
    </tr>
  );
}

// ── Pagination ────────────────────────────────────────────────────────────────
function Pagination({ currentPage, totalPages, totalCount, pageSize, onPageChange }: {
  currentPage: number; totalPages: number; totalCount: number;
  pageSize: number; onPageChange: (p: number) => void;
}) {
  const from = Math.min((currentPage - 1) * pageSize + 1, totalCount);
  const to = Math.min(currentPage * pageSize, totalCount);

  const btn = (disabled: boolean): React.CSSProperties => ({
    padding: "0.25rem 0.5rem", borderRadius: 6, background: "transparent",
    border: "1px solid var(--border)", color: disabled ? "var(--text-muted)" : "var(--text-secondary)",
    cursor: disabled ? "not-allowed" : "pointer", opacity: disabled ? 0.35 : 1,
    fontSize: "0.78rem", transition: "all 0.15s",
  });

  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0.75rem 1rem", borderTop: "1px solid var(--border)" }}>
      <span style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>
        {totalCount === 0 ? "No results" : `Showing ${from}–${to} of ${totalCount.toLocaleString()}`}
      </span>
      <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
        <button onClick={() => onPageChange(1)} disabled={currentPage === 1} style={btn(currentPage === 1)} aria-label="First page">«</button>
        <button onClick={() => onPageChange(currentPage - 1)} disabled={currentPage === 1} style={btn(currentPage === 1)} aria-label="Previous page">‹</button>
        <span style={{ fontSize: "0.72rem", color: "var(--text-secondary)", padding: "0 0.5rem" }}>
          {currentPage} / {totalPages || 1}
        </span>
        <button onClick={() => onPageChange(currentPage + 1)} disabled={currentPage >= totalPages} style={btn(currentPage >= totalPages)} aria-label="Next page">›</button>
        <button onClick={() => onPageChange(totalPages)} disabled={currentPage >= totalPages} style={btn(currentPage >= totalPages)} aria-label="Last page">»</button>
      </div>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────
interface TenderTableProps {
  tenders: TenderListItem[]; loading: boolean; totalCount: number;
  currentPage: number; totalPages: number; ordering: string;
  onPageChange: (p: number) => void; onSortChange: (o: string) => void;
}

export default function TenderTable({ tenders, loading, totalCount, currentPage, totalPages, ordering, onPageChange, onSortChange }: TenderTableProps) {
  const PAGE_SIZE = 25;

  const thStyle = (sortable?: boolean): React.CSSProperties => ({
    padding: "0.625rem 1rem", textAlign: "left", fontSize: "0.68rem",
    fontWeight: 500, color: "var(--text-muted)", letterSpacing: "0.04em",
    borderBottom: "1px solid var(--border)", whiteSpace: "nowrap",
    cursor: sortable ? "pointer" : "default", userSelect: "none",
    background: "transparent",
  });

  return (
    <div style={{ background: "var(--bg-card)", borderRadius: 16, overflow: "hidden" }}>
      {/* Table header bar */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0.875rem 1rem", borderBottom: "1px solid var(--border)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.625rem" }}>
          <span style={{ fontFamily: "var(--font-fraunces), Georgia, serif", fontSize: "0.9rem", fontWeight: 600, color: "var(--text-primary)" }}>
            All Tenders
          </span>
          {!loading && (
            <span style={{ fontSize: "0.72rem", fontWeight: 600, color: "var(--text-muted)", background: "rgba(255,255,255,0.06)", padding: "2px 8px", borderRadius: 6 }}>
              {totalCount}
            </span>
          )}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <span style={{ fontSize: "0.65rem", color: "var(--text-muted)" }}>Scores are advisory only. Human review is required before any action.</span>
        </div>
      </div>

      {/* Table */}
      <div style={{ overflowX: "auto" }}>
        <table className="ts-table">
          <thead>
            <tr>
              <th style={thStyle()}>Tender ID</th>
              <th style={thStyle()}>Buyer</th>
              <th style={thStyle(true)} onClick={() => onSortChange(sortToggle("category", ordering))}>
                Category <SortIcon field="category" ordering={ordering} />
              </th>
              <th style={thStyle(true)} onClick={() => onSortChange(sortToggle("deadline", ordering))}>
                Deadline <SortIcon field="deadline" ordering={ordering} />
              </th>
              <th style={{ ...thStyle(true), textAlign: "right" }} onClick={() => onSortChange(sortToggle("score", ordering))}>
                Risk Score <SortIcon field="score" ordering={ordering} />
              </th>
              <th style={{ ...thStyle(), textAlign: "right" }}>Flags</th>
              <th style={{ ...thStyle(), textAlign: "right" }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              [...Array(8)].map((_, i) => <SkeletonRow key={i} />)
            ) : tenders.length === 0 ? (
              <tr>
                <td colSpan={7} style={{ padding: "3rem 1rem", textAlign: "center", color: "var(--text-muted)", fontSize: "0.82rem" }}>
                  No tenders found matching your filters.
                </td>
              </tr>
            ) : (
              tenders.map((tender, idx) => (
                <motion.tr
                  key={tender.id}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ duration: 0.15, delay: idx * 0.03 }}
                >
                  {/* Tender ID — Fraunces font */}
                  <td style={{ padding: "0.875rem 1rem", borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                      <Link href={`/tenders/${tender.id}`}
                        style={{ fontFamily: "var(--font-fraunces), Georgia, serif", fontSize: "0.82rem", fontWeight: 600, color: "var(--text-primary)", textDecoration: "none" }}
                        onMouseEnter={e => (e.currentTarget.style.color = "var(--accent)")}
                        onMouseLeave={e => (e.currentTarget.style.color = "var(--text-primary)")}
                      >
                        {tender.tender_id}
                      </Link>
                    </div>
                    <p style={{ fontSize: "0.68rem", color: "var(--text-muted)", marginTop: 2, maxWidth: 160, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {tender.title}
                    </p>
                  </td>

                  {/* Buyer — avatar + name like reference */}
                  <td style={{ padding: "0.875rem 1rem", borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
                    <div className="ts-member-cell">
                      <div className="ts-avatar" style={{ background: getGradient(tender.buyer_name) }}>
                        {getInitials(tender.buyer_name)}
                      </div>
                      <div>
                        <p className="ts-member-name">{tender.buyer_name.length > 22 ? tender.buyer_name.slice(0, 22) + "…" : tender.buyer_name}</p>
                        <p className="ts-member-sub">{tender.buyer_id}</p>
                      </div>
                    </div>
                  </td>

                  {/* Category */}
                  <td style={{ padding: "0.875rem 1rem", borderBottom: "1px solid rgba(255,255,255,0.04)", fontSize: "0.8rem", color: "var(--text-secondary)", whiteSpace: "nowrap" }}>
                    {tender.category}
                  </td>

                  {/* Deadline */}
                  <td style={{ padding: "0.875rem 1rem", borderBottom: "1px solid rgba(255,255,255,0.04)", fontSize: "0.78rem", color: "var(--text-muted)", whiteSpace: "nowrap" }}>
                    {(() => { try { return format(new Date(tender.submission_deadline), "dd MMM yyyy"); } catch { return tender.submission_deadline; } })()}
                  </td>

                  {/* Risk Score */}
                  <td style={{ padding: "0.875rem 1rem", borderBottom: "1px solid rgba(255,255,255,0.04)", textAlign: "right" }}>
                    <ScoreBadge score={tender.latest_score ?? null} />
                  </td>

                  {/* Flags */}
                  <td style={{ padding: "0.875rem 1rem", borderBottom: "1px solid rgba(255,255,255,0.04)", textAlign: "right" }}>
                    {tender.active_red_flag_count > 0 ? (
                      <span className="badge badge-red">{tender.active_red_flag_count}</span>
                    ) : (
                      <span style={{ color: "var(--text-muted)", fontSize: "0.75rem" }}>—</span>
                    )}
                  </td>

                  {/* Actions — eye + edit icons like reference */}
                  <td style={{ padding: "0.875rem 1rem", borderBottom: "1px solid rgba(255,255,255,0.04)", textAlign: "right" }}>
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 4 }}>
                      <Link href={`/tenders/${tender.id}`}>
                        <button className="ts-action-btn" title="View details">
                          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>
                          </svg>
                        </button>
                      </Link>
                      <button className="ts-action-btn danger" title="Flag for review">
                        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/><line x1="4" y1="22" x2="4" y2="15"/>
                        </svg>
                      </button>
                    </div>
                  </td>
                </motion.tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <Pagination currentPage={currentPage} totalPages={totalPages} totalCount={totalCount} pageSize={PAGE_SIZE} onPageChange={onPageChange} />
    </div>
  );
}
