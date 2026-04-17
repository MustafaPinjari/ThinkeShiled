"use client";

import React from "react";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";

const DATA = [
  { month: "Jan", high: 8, medium: 14, low: 22 },
  { month: "Feb", high: 12, medium: 18, low: 19 },
  { month: "Mar", high: 7, medium: 11, low: 25 },
  { month: "Apr", high: 15, medium: 20, low: 18 },
  { month: "May", high: 11, medium: 16, low: 21 },
  { month: "Jun", high: 9, medium: 13, low: 24 },
  { month: "Jul", high: 18, medium: 22, low: 16 },
  { month: "Aug", high: 14, medium: 19, low: 20 },
  { month: "Sep", high: 16, medium: 21, low: 17 },
  { month: "Oct", high: 10, medium: 15, low: 23 },
  { month: "Nov", high: 20, medium: 24, low: 14 },
  { month: "Dec", high: 13, medium: 17, low: 22 },
];

const CustomTooltip = ({ active, payload, label }: { active?: boolean; payload?: Array<{ name: string; value: number; color: string }>; label?: string }) => {
  if (!active || !payload?.length) return null;
  return (
    <div style={{ background: "#222", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 8, padding: "8px 12px" }}>
      <p style={{ color: "var(--text-muted)", fontSize: "0.68rem", marginBottom: 4 }}>{label}</p>
      {payload.map(p => (
        <p key={p.name} style={{ color: p.color, fontSize: "0.78rem", fontWeight: 500 }}>{p.name}: {p.value}</p>
      ))}
    </div>
  );
};

export default function RiskDistributionChart({ high, medium, low }: { high?: number; medium?: number; low?: number }) {
  // Scale mock data if real stats provided
  const total = (high ?? 0) + (medium ?? 0) + (low ?? 0);
  const scale = total > 0 ? total / 100 : 1;
  const chartData = total > 0
    ? DATA.map(d => ({ ...d, high: Math.round(d.high * scale), medium: Math.round(d.medium * scale), low: Math.round(d.low * scale) }))
    : DATA;

  return (
    <ResponsiveContainer width="100%" height={180}>
      <LineChart data={chartData} margin={{ top: 4, right: 4, left: -28, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" vertical={false} />
        <XAxis dataKey="month" tick={{ fill: "#52525b", fontSize: 11 }} axisLine={false} tickLine={false} />
        <YAxis tick={{ fill: "#52525b", fontSize: 11 }} axisLine={false} tickLine={false} />
        <Tooltip content={<CustomTooltip />} />
        <Line type="monotone" dataKey="high" stroke="#ef4444" strokeWidth={2} dot={false} activeDot={{ r: 4, fill: "#ef4444" }} />
        <Line type="monotone" dataKey="medium" stroke="#f59e0b" strokeWidth={2} dot={false} activeDot={{ r: 4, fill: "#f59e0b" }} strokeDasharray="4 2" />
        <Line type="monotone" dataKey="low" stroke="#22c55e" strokeWidth={2} dot={false} activeDot={{ r: 4, fill: "#22c55e" }} />
      </LineChart>
    </ResponsiveContainer>
  );
}
