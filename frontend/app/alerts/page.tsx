"use client";

import React, { useCallback, useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import Layout from "@/components/Layout";
import AlertList, { type AlertItem } from "@/components/ui/AlertList";
import ThresholdSettings from "@/components/ui/ThresholdSettings";
import { useAuth } from "@/contexts/AuthContext";
import api from "@/lib/api";
import type { PaginatedResponse } from "@/types/tender";

const PAGE_SIZE = 20;

export default function AlertsPage() {
  const { role } = useAuth();

  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchAlerts = useCallback(async (page: number) => {
    setLoading(true); setError(null);
    try {
      const { data } = await api.get<PaginatedResponse<AlertItem>>(
        "/alerts/", { params: { page, page_size: PAGE_SIZE } }
      );
      setAlerts(data.results);
      setTotalCount(data.count);
    } catch { setError("Failed to load alerts. Please try again."); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchAlerts(1); }, [fetchAlerts]);

  function handlePageChange(page: number) {
    setCurrentPage(page);
    fetchAlerts(page);
  }

  async function handleMarkRead(id: number) {
    try {
      await api.post(`/alerts/${id}/read/`);
      setAlerts((prev) => prev.map((a) => (a.id === id ? { ...a, is_read: true } : a)));
    } catch { /* non-critical */ }
  }

  const totalPages = Math.ceil(totalCount / PAGE_SIZE);
  const unreadCount = alerts.filter((a) => !a.is_read).length;

  return (
    <Layout>
      <div className="space-y-6">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.25 }}
          className="flex items-center justify-between"
        >
          <div>
            <div className="flex items-center gap-3">
              <h1 style={{ color: "var(--text-primary)", fontWeight: 700, fontSize: "1.2rem", letterSpacing: "-0.02em" }}>
                Alerts
              </h1>
              <AnimatePresence>
                {unreadCount > 0 && (
                  <motion.span
                    initial={{ scale: 0 }}
                    animate={{ scale: 1 }}
                    exit={{ scale: 0 }}
                    className="badge badge-red"
                    style={{ fontSize: "0.65rem" }}
                  >
                    {unreadCount} unread
                  </motion.span>
                )}
              </AnimatePresence>
            </div>
            <p style={{ color: "var(--text-muted)", fontSize: "0.78rem", marginTop: "2px" }}>
              Alert history for the last 90 days
            </p>
          </div>
          <div className="flex items-center gap-2">
            <div className="px-3 py-1.5 rounded-lg" style={{ background: "rgba(251,191,36,0.08)", border: "1px solid rgba(251,191,36,0.2)" }}>
              <span style={{ color: "rgba(251,191,36,0.9)", fontSize: "0.68rem", fontWeight: 600 }}>
                ⚠️ Advisory Only
              </span>
            </div>
          </div>
        </motion.div>

        {/* Alert list */}
        {error ? (
          <div style={{ borderRadius: "0.75rem", border: "1px solid rgba(239,68,68,0.25)", background: "rgba(239,68,68,0.1)", padding: "0.75rem 1rem", fontSize: "0.875rem", color: "#fca5a5", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <span>{error}</span>
            <button onClick={() => fetchAlerts(currentPage)} style={{ textDecoration: "underline", background: "none", border: "none", color: "inherit", cursor: "pointer" }}>Retry</button>
          </div>
        ) : (
          <AlertList
            alerts={alerts} loading={loading} totalCount={totalCount}
            currentPage={currentPage} totalPages={totalPages} pageSize={PAGE_SIZE}
            onPageChange={handlePageChange} onMarkRead={handleMarkRead}
          />
        )}

        {/* Threshold settings — ADMIN only */}
        {role === "ADMIN" && (
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, delay: 0.2 }}
          >
            <ThresholdSettings />
          </motion.div>
        )}
      </div>
    </Layout>
  );
}
