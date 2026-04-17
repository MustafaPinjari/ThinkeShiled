"use client";

import React from "react";
import Link from "next/link";
import { format } from "date-fns";
import { motion } from "framer-motion";
import type { CollusionRing } from "@/types/graph";

interface CollusionRingPanelProps {
  rings: CollusionRing[];
  loading?: boolean;
}

function SkeletonItem() {
  return (
    <div className="space-y-2 p-3 rounded-xl" style={{ background: "rgba(255,255,255,0.03)", border: "1px solid var(--border)" }}>
      <div className="skeleton h-3 w-3/4" />
      <div className="skeleton h-3 w-1/2" />
    </div>
  );
}

export default function CollusionRingPanel({ rings, loading }: CollusionRingPanelProps) {
  const activeRings = rings.filter((r) => r.is_active);

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between mb-4">
        <h2 style={{ color: "var(--text-primary)", fontSize: "0.875rem", fontWeight: 600 }}>
          Collusion Rings
        </h2>
        {!loading && (
          <span className="badge badge-red" style={{ fontSize: "0.62rem" }}>
            {activeRings.length} active
          </span>
        )}
      </div>

      <div className="flex-1 overflow-y-auto space-y-2 pr-1">
        {loading ? (
          <>
            <SkeletonItem />
            <SkeletonItem />
            <SkeletonItem />
          </>
        ) : rings.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-8 gap-2">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" style={{ color: "var(--text-muted)" }}>
              <circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/>
              <line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/>
              <line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/>
            </svg>
            <p style={{ color: "var(--text-muted)", fontSize: "0.78rem", textAlign: "center" }}>
              No collusion rings detected.
            </p>
          </div>
        ) : (
          rings.map((ring, i) => (
            <motion.div
              key={ring.ring_id}
              initial={{ opacity: 0, x: 8 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.2, delay: i * 0.05 }}
            >
              <Link
                href={`/graph/rings/${ring.ring_id}`}
                className="block p-3 rounded-xl transition-all duration-150"
                style={{
                  background: ring.is_active ? "rgba(239,68,68,0.06)" : "rgba(255,255,255,0.02)",
                  border: `1px solid ${ring.is_active ? "rgba(239,68,68,0.2)" : "var(--border)"}`,
                }}
                onMouseEnter={(e) => {
                  (e.currentTarget as HTMLElement).style.background = ring.is_active ? "rgba(239,68,68,0.1)" : "rgba(255,255,255,0.04)";
                }}
                onMouseLeave={(e) => {
                  (e.currentTarget as HTMLElement).style.background = ring.is_active ? "rgba(239,68,68,0.06)" : "rgba(255,255,255,0.02)";
                }}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p style={{ fontFamily: "monospace", fontSize: "0.68rem", color: "var(--text-muted)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {ring.ring_id}
                    </p>
                    <p style={{ fontSize: "0.8rem", fontWeight: 600, color: ring.is_active ? "#f87171" : "var(--text-secondary)", marginTop: "2px" }}>
                      {ring.member_count} member{ring.member_count !== 1 ? "s" : ""}
                    </p>
                  </div>
                  <div className="flex flex-col items-end gap-1 shrink-0">
                    {ring.is_active ? (
                      <span className="badge badge-red" style={{ fontSize: "0.58rem" }}>Active</span>
                    ) : (
                      <span className="badge badge-gray" style={{ fontSize: "0.58rem" }}>Inactive</span>
                    )}
                  </div>
                </div>
                {ring.detected_at && (
                  <p style={{ color: "var(--text-muted)", fontSize: "0.65rem", marginTop: "0.375rem" }}>
                    Detected: {format(new Date(ring.detected_at), "dd MMM yyyy")}
                  </p>
                )}
              </Link>
            </motion.div>
          ))
        )}
      </div>
    </div>
  );
}
