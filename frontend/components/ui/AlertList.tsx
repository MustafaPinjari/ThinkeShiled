"use client";

import Link from "next/link";
import React from "react";
import { format } from "date-fns";

export interface RedFlagSummary {
  flag_type: string;
  severity: "HIGH" | "MEDIUM" | "LOW";
}

export interface AlertItem {
  id: number;
  tender_id: number;
  tender_external_id: string;
  title: string;
  detail_link: string;
  alert_type: string;
  fraud_risk_score: number;
  top_red_flags: RedFlagSummary[];
  delivery_status: string;
  retry_count: number;
  is_read: boolean;
  created_at: string;
  delivered_at: string | null;
}

function ScoreBadge({ score }: { score: number }) {
  if (score >= 70) return <span className="badge badge-red">{score}</span>;
  if (score >= 40) return <span className="badge badge-amber">{score}</span>;
  return <span className="badge badge-green">{score}</span>;
}

function DeliveryBadge({ status }: { status: string }) {
  const label = status.replace(/_/g, " ");
  if (status === "DELIVERED") return <span className="badge badge-green">{label}</span>;
  if (status === "FAILED" || status === "PERMANENTLY_FAILED") return <span className="badge badge-red">{label}</span>;
  if (status === "RETRYING") return <span className="badge badge-amber">{label}</span>;
  return <span className="badge badge-gray">{label}</span>;
}

function FlagChip({ flag }: { flag: RedFlagSummary }) {
  const label = flag.flag_type.replace(/_/g, " ").toLowerCase().replace(/\b\w/g, c => c.toUpperCase());
  if (flag.severity === "HIGH") return <span className="badge badge-red" style={{ fontSize: "0.62rem" }}>{label}</span>;
  if (flag.severity === "MEDIUM") return <span className="badge badge-amber" style={{ fontSize: "0.62rem" }}>{label}</span>;
  return <span className="badge badge-blue" style={{ fontSize: "0.62rem" }}>{label}</span>;
}

function SkeletonRow() {
  return (
    <tr>
      {[...Array(6)].map((_, i) => (
        <td key={i} style={{ padding: "0.75rem 1rem", borderBottom: "1px solid var(--border)" }}>
          <div className="skeleton h-4" style={{ width: i === 1 ? "70%" : "50%" }} />
        </td>
      ))}
    </tr>
  );
}

interface PaginationProps {
  currentPage: number; totalPages: number; totalCount: number;
  pageSize: number; onPageChange: (page: number) => void;
}

function Pagination({ currentPage, totalPages, totalCount, pageSize, onPageChange }: PaginationProps) {
  const from = Math.min((currentPage - 1) * pageSize + 1, totalCount);
  const to = Math.min(currentPage * pageSize, totalCount);
  const btnStyle = (disabled: boolean): React.CSSProperties => ({
    padding: "0.25rem 0.5rem", borderRadius: "6px", background: "transparent",
    border: "1px solid var(--border)", color: disabled ? "var(--text-muted)" : "var(--text-secondary)",
    cursor: disabled ? "not-allowed" : "pointer", opacity: disabled ? 0.4 : 1, fontSize: "0.8rem",
  });
  return (
    <div className="flex items-center justify-between px-4 py-3" style={{ borderTop: "1px solid var(--border)" }}>
      <span style={{ color: "var(--text-muted)", fontSize: "0.75rem" }}>
        {totalCount === 0 ? "No alerts" : `${from}–${to} of ${totalCount.toLocaleString()}`}
      </span>
      <div className="flex items-center gap-1">
        <button onClick={() => onPageChange(1)} disabled={currentPage === 1} style={btnStyle(currentPage === 1)}>«</button>
        <button onClick={() => onPageChange(currentPage - 1)} disabled={currentPage === 1} style={btnStyle(currentPage === 1)}>‹</button>
        <span style={{ color: "var(--text-secondary)", fontSize: "0.75rem", padding: "0 0.5rem" }}>{currentPage} / {totalPages || 1}</span>
        <button onClick={() => onPageChange(currentPage + 1)} disabled={currentPage >= totalPages} style={btnStyle(currentPage >= totalPages)}>›</button>
        <button onClick={() => onPageChange(totalPages)} disabled={currentPage >= totalPages} style={btnStyle(currentPage >= totalPages)}>»</button>
      </div>
    </div>
  );
}

interface AlertListProps {
  alerts: AlertItem[]; loading: boolean; totalCount: number;
  currentPage: number; totalPages: number; pageSize: number;
  onPageChange: (page: number) => void; onMarkRead: (id: number) => void;
}

export default function AlertList({ alerts, loading, totalCount, currentPage, totalPages, pageSize, onPageChange, onMarkRead }: AlertListProps) {
  return (
    <div className="rounded-2xl overflow-hidden" style={{ background: "var(--bg-card)", border: "1px solid var(--border)" }}>
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3" style={{ borderBottom: "1px solid var(--border)" }}>
        <div className="flex items-center gap-2">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ color: "var(--text-muted)" }}>
            <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/>
            <path d="M13.73 21a2 2 0 0 1-3.46 0"/>
          </svg>
          <span style={{ color: "var(--text-primary)", fontSize: "0.8rem", fontWeight: 600 }}>Alerts</span>
          {!loading && totalCount > 0 && (
            <span className="badge badge-blue" style={{ fontSize: "0.6rem" }}>{totalCount}</span>
          )}
        </div>
        <span style={{ color: "var(--text-muted)", fontSize: "0.68rem" }}>Last 90 days · Advisory only</span>
      </div>

      <div className="overflow-x-auto">
        <table className="ts-table">
          <thead>
            <tr>
              {["Date / Time", "Tender", "Risk Score", "Top Red Flags", "Delivery", "Actions"].map((h, i) => (
                <th key={h} style={{ textAlign: i === 2 ? "right" : "left" }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              [...Array(8)].map((_, i) => <SkeletonRow key={i} />)
            ) : alerts.length === 0 ? (
              <tr>
                <td colSpan={6} style={{ padding: "3rem 1rem", textAlign: "center", color: "var(--text-muted)", fontSize: "0.875rem" }}>
                  No alerts in the last 90 days.
                </td>
              </tr>
            ) : (
              alerts.map((alert) => (
                <tr key={alert.id} style={{ background: !alert.is_read ? "rgba(59,130,246,0.04)" : "transparent" }}>
                  <td style={{ whiteSpace: "nowrap", fontSize: "0.75rem" }}>
                    {format(new Date(alert.created_at), "dd MMM yyyy HH:mm")}
                  </td>
                  <td style={{ maxWidth: "240px" }}>
                    <Link href={`/tenders/${alert.tender_id}`} style={{ color: "var(--accent)", fontWeight: 500, fontSize: "0.875rem" }} className="hover:underline line-clamp-2">
                      {alert.title || alert.tender_external_id}
                    </Link>
                    <div style={{ color: "var(--text-muted)", fontSize: "0.68rem", fontFamily: "monospace", marginTop: "2px" }}>
                      {alert.tender_external_id}
                    </div>
                  </td>
                  <td style={{ textAlign: "right" }}>
                    <ScoreBadge score={alert.fraud_risk_score} />
                  </td>
                  <td>
                    <div className="flex flex-wrap gap-1">
                      {alert.top_red_flags.length === 0 ? (
                        <span style={{ color: "var(--text-muted)", fontSize: "0.75rem" }}>—</span>
                      ) : (
                        alert.top_red_flags.slice(0, 3).map((flag, idx) => (
                          <FlagChip key={idx} flag={flag} />
                        ))
                      )}
                    </div>
                  </td>
                  <td style={{ whiteSpace: "nowrap" }}>
                    <DeliveryBadge status={alert.delivery_status} />
                  </td>
                  <td style={{ whiteSpace: "nowrap" }}>
                    {!alert.is_read ? (
                      <button onClick={() => onMarkRead(alert.id)} style={{ color: "var(--accent)", fontSize: "0.75rem", background: "none", border: "none", cursor: "pointer" }}>
                        Mark read
                      </button>
                    ) : (
                      <span style={{ color: "var(--text-muted)", fontSize: "0.75rem" }}>Read</span>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      <Pagination currentPage={currentPage} totalPages={totalPages} totalCount={totalCount} pageSize={pageSize} onPageChange={onPageChange} />
    </div>
  );
}
