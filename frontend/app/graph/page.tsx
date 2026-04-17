"use client";

import React, { useCallback, useEffect, useState } from "react";
import dynamic from "next/dynamic";
import { motion } from "framer-motion";
import Layout from "@/components/Layout";
import CollusionRingPanel from "@/components/ui/CollusionRingPanel";
import api from "@/lib/api";
import type { CollusionRing, EdgeType, GraphData } from "@/types/graph";

const GraphCanvas = dynamic(
  () => import("@/components/charts/GraphCanvas"),
  {
    ssr: false,
    loading: () => (
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "100%", gap: "1rem" }}>
        <div className="w-8 h-8 rounded-full border-2 border-blue-500 border-t-transparent animate-spin" />
        <p style={{ color: "var(--text-muted)", fontSize: "0.8rem" }}>Initialising graph engine…</p>
      </div>
    ),
  }
);

const EDGE_TYPE_META: { type: EdgeType; label: string; color: string; activeColor: string; dot: string }[] = [
  { type: "CO_BID", label: "Co-bid", color: "rgba(99,102,241,0.12)", activeColor: "#6366f1", dot: "#6366f1" },
  { type: "SHARED_DIRECTOR", label: "Shared Director", color: "rgba(245,158,11,0.12)", activeColor: "#f59e0b", dot: "#f59e0b" },
  { type: "SHARED_ADDRESS", label: "Shared Address", color: "rgba(16,185,129,0.12)", activeColor: "#10b981", dot: "#10b981" },
];

const ALL_EDGE_TYPES: EdgeType[] = ["CO_BID", "SHARED_DIRECTOR", "SHARED_ADDRESS"];

function EdgeTypeFilter({ active, onChange }: { active: EdgeType[]; onChange: (t: EdgeType[]) => void }) {
  const toggle = (type: EdgeType) => {
    if (active.includes(type)) {
      if (active.length > 1) onChange(active.filter((t) => t !== type));
    } else {
      onChange([...active, type]);
    }
  };

  return (
    <div className="flex flex-wrap gap-2 items-center">
      <span style={{ fontSize: "0.65rem", fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.08em" }}>
        Edge types:
      </span>
      {EDGE_TYPE_META.map(({ type, label, color, activeColor, dot }) => {
        const isActive = active.includes(type);
        return (
          <motion.button
            key={type}
            onClick={() => toggle(type)}
            aria-pressed={isActive}
            whileHover={{ scale: 1.03 }}
            whileTap={{ scale: 0.97 }}
            style={{
              display: "inline-flex", alignItems: "center", gap: "0.375rem",
              borderRadius: "999px", padding: "0.3rem 0.875rem", fontSize: "0.75rem", fontWeight: 500,
              border: `1px solid ${isActive ? activeColor : "var(--border-strong)"}`,
              background: isActive ? color : "transparent",
              color: isActive ? activeColor : "var(--text-muted)",
              cursor: "pointer", transition: "all 0.15s",
            }}
          >
            <span style={{ width: "0.5rem", height: "0.5rem", borderRadius: "50%", background: dot, display: "inline-block", boxShadow: isActive ? `0 0 6px ${dot}` : "none" }} />
            {label}
          </motion.button>
        );
      })}
    </div>
  );
}

export default function GraphPage() {
  const [graphData, setGraphData] = useState<GraphData>({ nodes: [], edges: [] });
  const [rings, setRings] = useState<CollusionRing[]>([]);
  const [activeEdgeTypes, setActiveEdgeTypes] = useState<EdgeType[]>(ALL_EDGE_TYPES);
  const [loading, setLoading] = useState(true);
  const [ringsLoading, setRingsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchGraph = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const { data } = await api.get<GraphData>("/graph/");
      setGraphData(data);
    } catch { setError("Failed to load graph data."); }
    finally { setLoading(false); }
  }, []);

  const fetchRings = useCallback(async () => {
    setRingsLoading(true);
    try {
      const { data } = await api.get<CollusionRing[]>("/graph/rings/");
      setRings(Array.isArray(data) ? data : []);
    } catch { /* non-critical */ }
    finally { setRingsLoading(false); }
  }, []);

  useEffect(() => { fetchGraph(); fetchRings(); }, [fetchGraph, fetchRings]);

  return (
    <Layout>
      <div className="space-y-4 h-full">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div>
            <h1 style={{ color: "var(--text-primary)", fontWeight: 700, fontSize: "1.2rem", letterSpacing: "-0.02em" }}>
              Collusion Network Graph
            </h1>
            <p style={{ color: "var(--text-muted)", fontSize: "0.78rem", marginTop: "2px" }}>
              {loading ? "Loading…" : `${graphData.nodes.length} entities · ${graphData.edges.length} connections`}
            </p>
          </div>
          <div className="flex items-center gap-3">
            {/* Legend */}
            <div className="flex items-center gap-3 px-3 py-2 rounded-xl" style={{ background: "var(--bg-card)", border: "1px solid var(--border)" }}>
              {[
                { label: "High Risk", color: "#ef4444" },
                { label: "Medium", color: "#f59e0b" },
                { label: "Low Risk", color: "#22c55e" },
              ].map(({ label, color }) => (
                <div key={label} className="flex items-center gap-1.5">
                  <div className="w-2.5 h-2.5 rounded-full" style={{ background: color, boxShadow: `0 0 6px ${color}` }} />
                  <span style={{ color: "var(--text-muted)", fontSize: "0.68rem" }}>{label}</span>
                </div>
              ))}
            </div>
            <button
              onClick={fetchGraph}
              className="ts-btn ts-btn-ghost"
              style={{ fontSize: "0.78rem", padding: "0.4rem 0.875rem" }}
            >
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/>
                <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
              </svg>
              Refresh
            </button>
          </div>
        </div>

        {/* Filter panel */}
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.25 }}
          className="rounded-xl px-4 py-3"
          style={{ background: "var(--bg-card)", border: "1px solid var(--border)" }}
        >
          <EdgeTypeFilter active={activeEdgeTypes} onChange={setActiveEdgeTypes} />
        </motion.div>

        {/* Main content — canvas + rings side by side */}
        <div style={{ display: "flex", gap: "0.75rem", alignItems: "flex-start" }}>
          {/* Graph canvas */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.4, delay: 0.1 }}
            style={{
              flex: 1, borderRadius: 16, overflow: "hidden", position: "relative",
              background: "var(--bg-card)", border: "1px solid var(--border)",
              height: "520px", minHeight: "520px",
            }}
          >
            {error ? (
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "100%", gap: "1rem" }}>
                <p style={{ color: "#f87171", fontSize: "0.875rem" }}>{error}</p>
                <button onClick={fetchGraph} className="ts-btn ts-btn-ghost" style={{ fontSize: "0.8rem" }}>Retry</button>
              </div>
            ) : loading ? (
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "100%", gap: "1rem" }}>
                <div style={{ width: 28, height: 28, borderRadius: "50%", border: "2px solid #3b82f6", borderTopColor: "transparent", animation: "spin 1s linear infinite" }} />
                <p style={{ color: "var(--text-muted)", fontSize: "0.8rem" }}>Loading graph data…</p>
              </div>
            ) : (
              <GraphCanvas data={graphData} activeEdgeTypes={activeEdgeTypes} />
            )}
          </motion.div>

          {/* Collusion rings panel */}
          <motion.div
            initial={{ opacity: 0, x: 12 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.3, delay: 0.2 }}
            style={{
              width: 260, flexShrink: 0, borderRadius: 16, padding: "1rem",
              background: "var(--bg-card)", border: "1px solid var(--border)",
              height: "520px", overflowY: "auto",
            }}
          >
            <CollusionRingPanel rings={rings} loading={ringsLoading} />
          </motion.div>
        </div>
      </div>
    </Layout>
  );
}
