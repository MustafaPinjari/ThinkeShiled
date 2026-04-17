"use client";

import React from "react";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";

const DATA = [
  { month: "01", score: 32 }, { month: "02", score: 48 }, { month: "03", score: 28 },
  { month: "04", score: 55 }, { month: "05", score: 42 }, { month: "06", score: 38 },
  { month: "07", score: 61 }, { month: "08", score: 45 }, { month: "09", score: 52 },
  { month: "10", score: 35 }, { month: "11", score: 58 }, { month: "12", score: 44 },
];

const CustomTooltip = ({ active, payload, label }: { active?: boolean; payload?: Array<{ value: number }>; label?: string }) => {
  if (!active || !payload?.length) return null;
  return (
    <div style={{ background: "var(--bg-elevated, #222)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 8, padding: "8px 12px" }}>
      <p style={{ color: "var(--text-muted)", fontSize: "0.68rem", marginBottom: 2 }}>Month {label}</p>
      <p style={{ color: "#60a5fa", fontSize: "0.85rem", fontWeight: 600 }}>Score: {payload[0]?.value}</p>
    </div>
  );
};

export default function FraudTrendChart({ data = DATA }: { data?: typeof DATA }) {
  return (
    <ResponsiveContainer width="100%" height={180}>
      <BarChart data={data} margin={{ top: 4, right: 4, left: -28, bottom: 0 }} barSize={14}>
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" vertical={false} />
        <XAxis dataKey="month" tick={{ fill: "#52525b", fontSize: 11 }} axisLine={false} tickLine={false} />
        <YAxis domain={[0, 100]} tick={{ fill: "#52525b", fontSize: 11 }} axisLine={false} tickLine={false} />
        <Tooltip content={<CustomTooltip />} cursor={{ fill: "rgba(255,255,255,0.04)" }} />
        <Bar dataKey="score" fill="#3b82f6" radius={[4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}
