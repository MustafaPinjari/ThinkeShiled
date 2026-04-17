"use client";

import React, { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import Layout from "@/components/Layout";
import ExportPanel from "@/components/ui/ExportPanel";
import { useAuth } from "@/contexts/AuthContext";
import api from "@/lib/api";
import type { PaginatedResponse } from "@/types/tender";

interface AuditLogEntry {
  id: number;
  event_type: string;
  timestamp: string;
  user_id: number | null;
  affected_entity_type: string;
  affected_entity_id: number | null;
  data_snapshot: Record<string, unknown>;
  ip_address: string | null;
}

const EVENT_TYPE_LABELS: Record<string, string> = {
  USER_LOGIN: "User Login", USER_LOGOUT: "User Logout",
  TENDER_INGESTED: "Tender Ingested", SCORE_COMPUTED: "Score Computed",
  RED_FLAG_RAISED: "Red Flag Raised", RED_FLAG_CLEARED: "Red Flag Cleared",
  ALERT_SENT: "Alert Sent", STATUS_CHANGE: "Status Change",
};

const EVENT_TYPE_BADGE: Record<string, string> = {
  USER_LOGIN: "badge badge-blue", USER_LOGOUT: "badge badge-gray",
  TENDER_INGESTED: "badge badge-green", SCORE_COMPUTED: "badge badge-blue",
  RED_FLAG_RAISED: "badge badge-red", RED_FLAG_CLEARED: "badge badge-green",
  ALERT_SENT: "badge badge-amber", STATUS_CHANGE: "badge badge-blue",
};

function formatTimestamp(ts: string): string {
  try {
    return new Date(ts).toLocaleString(undefined, {
      year: "numeric", month: "short", day: "numeric",
      hour: "2-digit", minute: "2-digit", second: "2-digit",
    });
  } catch { return ts; }
}

function SkeletonRow() {
  return (
    <tr>
      {[...Array(6)].map((_, i) => (
        <td key={i} style={{ padding: "0.75rem 1rem", borderBottom: "1px solid var(--border)" }}>
          <div className="skeleton h-4" style={{ width: i === 1 ? "60%" : "50%" }} />
        </td>
      ))}
    </tr>
  );
}

function Pagination({ currentPage, totalPages, onPageChange }: {
  currentPage: number; totalPages: number; onPageChange: (p: number) => void;
}) {
  if (totalPages <= 1) return null;
  const pages: (number | "…")[] = [];
  if (totalPages <= 7) {
    for (let i = 1; i <= totalPages; i++) pages.push(i);
  } else {
    pages.push(1);
    if (currentPage > 3) pages.push("…");
    for (let i = Math.max(2, currentPage - 1); i <= Math.min(totalPages - 1, currentPage + 1); i++) pages.push(i);
    if (currentPage < totalPages - 2) pages.push("…");
    pages.push(totalPages);
  }

  const btnBase: React.CSSProperties = {
    padding: "0.25rem 0.5rem", borderRadius: "6px", background: "transparent",
    border: "none", cursor: "pointer", fontSize: "0.875rem", transition: "all 0.15s",
  };

  return (
    <nav className="flex items-center justify-center gap-1 pt-4">
      <button onClick={() => onPageChange(currentPage - 1)} disabled={currentPage === 1}
        style={{ ...btnBase, color: "var(--text-muted)", opacity: currentPage === 1 ? 0.4 : 1, cursor: currentPage === 1 ? "not-allowed" : "pointer" }}>‹</button>
      {pages.map((p, idx) =>
        p === "…" ? (
          <span key={`e-${idx}`} style={{ padding: "0.25rem 0.5rem", fontSize: "0.875rem", color: "var(--text-muted)" }}>…</span>
        ) : (
          <button key={p} onClick={() => onPageChange(p as number)}
            style={{ ...btnBase, background: p === currentPage ? "var(--accent)" : "transparent", color: p === currentPage ? "#fff" : "var(--text-secondary)", fontWeight: p === currentPage ? 600 : 400 }}>
            {p}
          </button>
        )
      )}
      <button onClick={() => onPageChange(currentPage + 1)} disabled={currentPage === totalPages}
        style={{ ...btnBase, color: "var(--text-muted)", opacity: currentPage === totalPages ? 0.4 : 1, cursor: currentPage === totalPages ? "not-allowed" : "pointer" }}>›</button>
    </nav>
  );
}

const PAGE_SIZE = 25;

export default function AuditLogPage() {
  const { role, isLoading: authLoading } = useAuth();
  const router = useRouter();

  const [entries, setEntries] = useState<AuditLogEntry[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!authLoading && role !== "ADMIN") router.replace("/dashboard");
  }, [authLoading, role, router]);

  const fetchEntries = useCallback(async (page: number) => {
    setLoading(true); setError(null);
    try {
      const { data } = await api.get<PaginatedResponse<AuditLogEntry>>(
        "/audit-log/", { params: { page, page_size: PAGE_SIZE } }
      );
      setEntries(data.results);
      setTotalCount(data.count);
    } catch { setError("Failed to load audit log."); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => {
    if (!authLoading && role === "ADMIN") fetchEntries(1);
  }, [authLoading, role, fetchEntries]);

  function handlePageChange(page: number) {
    setCurrentPage(page);
    fetchEntries(page);
  }

  const totalPages = Math.ceil(totalCount / PAGE_SIZE);

  if (authLoading || role !== "ADMIN") return null;

  const thStyle: React.CSSProperties = {
    padding: "0.625rem 1rem", background: "rgba(255,255,255,0.02)",
    color: "var(--text-muted)", fontSize: "0.68rem", fontWeight: 600,
    letterSpacing: "0.07em", textTransform: "uppercase",
    borderBottom: "1px solid var(--border)", whiteSpace: "nowrap", textAlign: "left",
  };

  const tdStyle: React.CSSProperties = {
    padding: "0.75rem 1rem", borderBottom: "1px solid var(--border)",
    color: "var(--text-secondary)", fontSize: "0.875rem", whiteSpace: "nowrap",
  };

  return (
    <Layout>
      <div className="space-y-6">
        {/* Header */}
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.25 }}>
          <div className="flex items-center justify-between">
            <div>
              <h1 style={{ color: "var(--text-primary)", fontWeight: 700, fontSize: "1.2rem", letterSpacing: "-0.02em" }}>
                Audit Log
              </h1>
              <p style={{ color: "var(--text-muted)", fontSize: "0.78rem", marginTop: "2px" }}>
                Immutable record of all system events · Retained for 7+ years
              </p>
            </div>
            {!loading && totalCount > 0 && (
              <span className="badge badge-blue" style={{ fontSize: "0.65rem" }}>
                {totalCount.toLocaleString()} entries
              </span>
            )}
          </div>
        </motion.div>

        {/* Table */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3, delay: 0.1 }}
          className="rounded-2xl overflow-hidden"
          style={{ background: "var(--bg-card)", border: "1px solid var(--border)" }}
        >
          {error ? (
            <div style={{ padding: "2rem 1.5rem", textAlign: "center" }}>
              <p style={{ fontSize: "0.875rem", color: "#f87171", marginBottom: "0.75rem" }}>{error}</p>
              <button onClick={() => fetchEntries(currentPage)} style={{ fontSize: "0.875rem", color: "var(--accent)", background: "none", border: "none", cursor: "pointer", textDecoration: "underline" }}>Retry</button>
            </div>
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="ts-table">
                  <thead>
                    <tr>
                      <th style={thStyle}>Timestamp</th>
                      <th style={thStyle}>Event</th>
                      <th style={thStyle}>User ID</th>
                      <th style={thStyle}>Entity</th>
                      <th style={thStyle}>Entity ID</th>
                      <th style={thStyle}>IP Address</th>
                    </tr>
                  </thead>
                  <tbody>
                    {loading ? (
                      [...Array(10)].map((_, i) => <SkeletonRow key={i} />)
                    ) : entries.length === 0 ? (
                      <tr>
                        <td colSpan={6} style={{ padding: "2.5rem 1rem", textAlign: "center", color: "var(--text-muted)", fontSize: "0.875rem" }}>
                          No audit log entries found.
                        </td>
                      </tr>
                    ) : (
                      entries.map((entry) => (
                        <tr key={entry.id}>
                          <td style={{ ...tdStyle, fontFamily: "monospace", fontSize: "0.75rem" }}>
                            {formatTimestamp(entry.timestamp)}
                          </td>
                          <td style={tdStyle}>
                            <span className={EVENT_TYPE_BADGE[entry.event_type] ?? "badge badge-gray"}>
                              {EVENT_TYPE_LABELS[entry.event_type] ?? entry.event_type}
                            </span>
                          </td>
                          <td style={tdStyle}>{entry.user_id ?? <span style={{ color: "var(--text-muted)" }}>—</span>}</td>
                          <td style={tdStyle}>{entry.affected_entity_type || <span style={{ color: "var(--text-muted)" }}>—</span>}</td>
                          <td style={tdStyle}>{entry.affected_entity_id ?? <span style={{ color: "var(--text-muted)" }}>—</span>}</td>
                          <td style={{ ...tdStyle, fontFamily: "monospace", fontSize: "0.75rem" }}>
                            {entry.ip_address ?? <span style={{ color: "var(--text-muted)" }}>—</span>}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>

              {!loading && totalCount > 0 && (
                <div className="flex flex-col sm:flex-row items-center justify-between gap-2 px-4 py-3"
                  style={{ borderTop: "1px solid var(--border)" }}>
                  <p style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                    Showing{" "}
                    <span style={{ fontWeight: 500, color: "var(--text-secondary)" }}>
                      {(currentPage - 1) * PAGE_SIZE + 1}–{Math.min(currentPage * PAGE_SIZE, totalCount)}
                    </span>{" "}
                    of{" "}
                    <span style={{ fontWeight: 500, color: "var(--text-secondary)" }}>
                      {totalCount.toLocaleString()}
                    </span>{" "}
                    entries
                  </p>
                  <Pagination currentPage={currentPage} totalPages={totalPages} onPageChange={handlePageChange} />
                </div>
              )}
            </>
          )}
        </motion.div>

        {/* Export panel */}
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3, delay: 0.2 }}>
          <ExportPanel />
        </motion.div>
      </div>
    </Layout>
  );
}
