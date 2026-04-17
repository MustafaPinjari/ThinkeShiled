"use client";

import React, { useCallback, useEffect, useState, useTransition } from "react";
import dynamic from "next/dynamic";
import { motion } from "framer-motion";
import Layout from "@/components/Layout";
import TenderTable from "@/components/tables/TenderTable";
import FilterPanel from "@/components/ui/FilterPanel";
import api from "@/lib/api";
import type { DashboardStats, PaginatedResponse, TenderFilters, TenderListItem } from "@/types/tender";

const FraudTrendChart = dynamic(() => import("@/components/charts/FraudTrendChart"), {
  ssr: false, loading: () => <div className="skeleton" style={{ height: 200, borderRadius: 12 }} />,
});
const RiskDistributionChart = dynamic(() => import("@/components/charts/RiskDistributionChart"), {
  ssr: false, loading: () => <div className="skeleton" style={{ height: 200, borderRadius: 12 }} />,
});

const PAGE_SIZE = 25;
const DEFAULT_FILTERS: TenderFilters = { ordering: "-score", page: 1, page_size: PAGE_SIZE };

function KpiCard({ label, value, loading, color, change, changeUp, sub }: {
  label: string; value: string | number | null; loading: boolean;
  color?: string; change?: string; changeUp?: boolean; sub?: string;
}) {
  return (
    <motion.div
      className="kpi-card"
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
      whileHover={{ scale: 1.01 }}
    >
      <p className="kpi-label">{label}</p>
      <div style={{ display: "flex", alignItems: "baseline", gap: "0.5rem", flexWrap: "wrap" }}>
        {loading ? (
          <div className="skeleton" style={{ height: 32, width: 80 }} />
        ) : (
          <span className="kpi-value" style={color ? { color } : {}}>
            {value !== null && value !== undefined ? value : "—"}
          </span>
        )}
        {!loading && change && (
          <span className={`kpi-change ${changeUp ? "kpi-change-up" : "kpi-change-down"}`}>
            {changeUp ? "↑" : "↓"} {change}
          </span>
        )}
      </div>
      {sub && <p style={{ fontSize: "0.68rem", color: "var(--text-muted)", marginTop: "0.375rem" }}>{sub}</p>}
    </motion.div>
  );
}

export default function DashboardPage() {
  const [tenders, setTenders] = useState<TenderListItem[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [filters, setFilters] = useState<TenderFilters>(DEFAULT_FILTERS);
  const [loading, setLoading] = useState(true);
  const [statsLoading, setStatsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showFilters, setShowFilters] = useState(false);
  const [, startTransition] = useTransition();

  const fetchTenders = useCallback(async (f: TenderFilters) => {
    setLoading(true); setError(null);
    try {
      const params: Record<string, string | number> = {};
      if (f.score_min) params.score_min = f.score_min;
      if (f.score_max) params.score_max = f.score_max;
      if (f.category) params.category = f.category;
      if (f.buyer_name) params.buyer_name = f.buyer_name;
      if (f.date_from) params.date_from = f.date_from;
      if (f.date_to) params.date_to = f.date_to;
      if (f.flag_type) params.flag_type = f.flag_type;
      if (f.ordering) params.ordering = f.ordering;
      params.page = f.page ?? 1;
      params.page_size = f.page_size ?? PAGE_SIZE;
      const { data } = await api.get<PaginatedResponse<TenderListItem>>("/tenders/", { params });
      setTenders(data.results); setTotalCount(data.count);
    } catch { setError("Failed to load tenders."); }
    finally { setLoading(false); }
  }, []);

  const fetchStats = useCallback(async () => {
    setStatsLoading(true);
    try { const { data } = await api.get<DashboardStats>("/tenders/stats/"); setStats(data); }
    catch { /* non-critical */ } finally { setStatsLoading(false); }
  }, []);

  useEffect(() => { fetchTenders(DEFAULT_FILTERS); fetchStats(); }, [fetchTenders, fetchStats]);

  const handleFilterChange = useCallback((newFilters: Partial<TenderFilters>) => {
    startTransition(() => {
      const updated = { ...filters, ...newFilters, page: 1 };
      setFilters(updated); fetchTenders(updated);
    });
  }, [filters, fetchTenders]);

  const handlePageChange = useCallback((page: number) => {
    const updated = { ...filters, page };
    setFilters(updated); fetchTenders(updated);
  }, [filters, fetchTenders]);

  const handleSortChange = useCallback((ordering: string) => {
    const updated = { ...filters, ordering, page: 1 };
    setFilters(updated); fetchTenders(updated);
  }, [filters, fetchTenders]);

  const totalPages = Math.ceil(totalCount / PAGE_SIZE);

  return (
    <Layout>
      <div className="space-y-5">

        {/* Page header */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "0.75rem" }}>
          <div>
            <h1 style={{ fontSize: "1.1rem", fontWeight: 700, color: "var(--text-primary)", letterSpacing: "-0.02em" }}>
              Fraud Intelligence Dashboard
            </h1>
            <p style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginTop: 2 }}>
              Real-time procurement fraud monitoring
            </p>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <button className="ts-btn ts-btn-ghost" style={{ fontSize: "0.75rem" }} onClick={() => { fetchTenders(filters); fetchStats(); }}>
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/>
                <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
              </svg>
              Refresh
            </button>
          </div>
        </div>

        {/* KPI row — matches reference exactly */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: "0.75rem" }}>
          <KpiCard label="Total Tenders" value={stats?.total_tenders ?? null} loading={statsLoading} change="3.5%" changeUp sub="All procurement tenders" />
          <KpiCard label="High Risk" value={stats?.high_risk_count ?? null} loading={statsLoading} color="#f87171" change="3.5%" changeUp={false} sub="Score ≥ 70" />
          <KpiCard label="Active Red Flags" value={stats?.high_flag_count ?? null} loading={statsLoading} color="#fbbf24" change="3.5%" changeUp sub="Unresolved indicators" />
          <KpiCard label="Collusion Rings" value={stats?.collusion_ring_count ?? null} loading={statsLoading} color="#c084fc" change="4.1%" changeUp sub="Detected networks" />
        </div>

        {/* Charts row — side by side like reference */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem" }}>

          {/* Fraud Score Trend — like "Sales Performance" in reference */}
          <motion.div className="card" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}>
            <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: "1rem" }}>
              <div>
                <p className="section-title">Fraud Score Trend</p>
                <p className="section-sub">Average risk score over time</p>
              </div>
              <select style={{ background: "rgba(255,255,255,0.06)", border: "1px solid var(--border)", borderRadius: 6, padding: "0.25rem 0.5rem", fontSize: "0.72rem", color: "var(--text-secondary)", cursor: "pointer", outline: "none" }}>
                <option>Last 12 months</option>
                <option>Last 6 months</option>
                <option>Last 30 days</option>
              </select>
            </div>
            {/* Mini stats row like reference */}
            <div style={{ display: "flex", gap: "1.5rem", marginBottom: "1rem" }}>
              {[
                { label: "Avg Score", val: "58.4", up: false },
                { label: "Peak Score", val: "88", up: false },
                { label: "Flagged", val: stats?.high_flag_count ?? "—", up: true },
              ].map(s => (
                <div key={s.label}>
                  <p style={{ fontSize: "0.68rem", color: "var(--text-muted)" }}>{s.label}</p>
                  <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                    <span style={{ fontSize: "0.95rem", fontWeight: 700, color: "var(--text-primary)" }}>{s.val}</span>
                    <span style={{ fontSize: "0.65rem", color: s.up ? "#4ade80" : "#f87171" }}>↑ 3.5%</span>
                  </div>
                </div>
              ))}
            </div>
            <FraudTrendChart />
          </motion.div>

          {/* Risk Distribution — like "Traffic Source" in reference */}
          <motion.div className="card" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }}>
            <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: "1rem" }}>
              <div>
                <p className="section-title">Risk Distribution</p>
                <p className="section-sub">Tenders by risk level</p>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                {[{ label: "High", color: "#ef4444" }, { label: "Medium", color: "#f59e0b" }, { label: "Low", color: "#22c55e" }].map(l => (
                  <div key={l.label} style={{ display: "flex", alignItems: "center", gap: 4 }}>
                    <div style={{ width: 7, height: 7, borderRadius: "50%", background: l.color }} />
                    <span style={{ fontSize: "0.68rem", color: "var(--text-muted)" }}>{l.label}</span>
                  </div>
                ))}
              </div>
            </div>
            <div style={{ marginBottom: "0.75rem" }}>
              <p style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--text-primary)", letterSpacing: "-0.02em" }}>
                {statsLoading ? "—" : stats?.total_tenders?.toLocaleString() ?? "—"}
              </p>
              <p style={{ fontSize: "0.68rem", color: "var(--text-muted)" }}>Total tenders analysed</p>
            </div>
            <RiskDistributionChart
              high={stats?.high_risk_count}
              medium={stats ? Math.round(stats.total_tenders * 0.27) : undefined}
              low={stats ? Math.max(0, stats.total_tenders - stats.high_risk_count - Math.round(stats.total_tenders * 0.27)) : undefined}
            />
          </motion.div>
        </div>

        {/* Tender feed */}
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.75rem", flexWrap: "wrap", gap: "0.5rem" }}>
            <div>
              <p className="section-title">Tender Intelligence Feed</p>
              <p className="section-sub">{totalCount > 0 ? `${totalCount.toLocaleString()} tenders` : "Loading…"}</p>
            </div>
            <button onClick={() => setShowFilters(!showFilters)} className="ts-btn ts-btn-ghost" style={{ fontSize: "0.75rem" }}>
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/>
              </svg>
              {showFilters ? "Hide Filters" : "Filters"}
            </button>
          </div>

          <div style={{ display: "flex", gap: "0.75rem", alignItems: "flex-start" }}>
            {showFilters && (
              <motion.div initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} style={{ width: 220, flexShrink: 0 }}>
                <FilterPanel filters={filters} onFilterChange={handleFilterChange} />
              </motion.div>
            )}
            <div style={{ flex: 1, minWidth: 0 }}>
              {error ? (
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0.75rem 1rem", borderRadius: 10, background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.2)", fontSize: "0.8rem", color: "#f87171" }}>
                  <span>{error}</span>
                  <button onClick={() => fetchTenders(filters)} className="ts-btn ts-btn-ghost" style={{ fontSize: "0.72rem", color: "#f87171" }}>Retry</button>
                </div>
              ) : (
                <TenderTable tenders={tenders} loading={loading} totalCount={totalCount}
                  currentPage={filters.page ?? 1} totalPages={totalPages}
                  ordering={filters.ordering ?? "-score"}
                  onPageChange={handlePageChange} onSortChange={handleSortChange} />
              )}
            </div>
          </div>
        </motion.div>

      </div>
    </Layout>
  );
}
