"use client";

import React, { useEffect, useRef } from "react";
import * as d3 from "d3";
import type { Explanation, SHAPFactor } from "@/types/tender";

// ── Constants ─────────────────────────────────────────────────────────────────

const MARGIN = { top: 16, right: 80, bottom: 32, left: 180 };
const BAR_HEIGHT = 28;
const BAR_GAP = 8;

// ── Helpers ───────────────────────────────────────────────────────────────────

/** Human-readable feature name mapping */
const FEATURE_LABELS: Record<string, string> = {
  cv_bids: "Bid CV (variation)",
  bid_spread_ratio: "Bid Spread Ratio",
  norm_winning_distance: "Winning Bid Distance",
  single_bidder_flag: "Single Bidder",
  price_deviation_pct: "Price Deviation %",
  deadline_days: "Deadline Days",
  repeat_winner_rate: "Repeat Winner Rate",
  bidder_count: "Bidder Count",
  winner_bid_rank: "Winner Bid Rank",
};

function featureLabel(key: string): string {
  return FEATURE_LABELS[key] ?? key.replace(/_/g, " ");
}

// ── D3 chart renderer ─────────────────────────────────────────────────────────

function renderChart(
  svgEl: SVGSVGElement,
  factors: SHAPFactor[],
  containerWidth: number
) {
  const innerWidth = containerWidth - MARGIN.left - MARGIN.right;
  const innerHeight =
    factors.length * (BAR_HEIGHT + BAR_GAP) - BAR_GAP;
  const totalHeight = innerHeight + MARGIN.top + MARGIN.bottom;

  const svg = d3.select(svgEl);
  svg.selectAll("*").remove();
  svg
    .attr("width", containerWidth)
    .attr("height", totalHeight)
    .attr("role", "img")
    .attr("aria-label", "SHAP feature attribution chart");

  const g = svg
    .append("g")
    .attr("transform", `translate(${MARGIN.left},${MARGIN.top})`);

  // X scale — symmetric around 0
  const maxAbs = d3.max(factors, (d) => Math.abs(d.shap_value)) ?? 1;
  const xScale = d3
    .scaleLinear()
    .domain([-maxAbs, maxAbs])
    .range([0, innerWidth])
    .nice();

  // Y scale — one band per factor
  const yScale = d3
    .scaleBand()
    .domain(factors.map((_, i) => String(i)))
    .range([0, innerHeight])
    .paddingInner(BAR_GAP / (BAR_HEIGHT + BAR_GAP));

  // Zero line
  g.append("line")
    .attr("x1", xScale(0))
    .attr("x2", xScale(0))
    .attr("y1", 0)
    .attr("y2", innerHeight)
    .attr("stroke", "rgba(99,130,201,0.3)")
    .attr("stroke-width", 1)
    .attr("stroke-dasharray", "4,3");

  // Bars
  g.selectAll<SVGRectElement, SHAPFactor>("rect.bar")
    .data(factors)
    .join("rect")
    .attr("class", "bar")
    .attr("x", (d) => (d.shap_value >= 0 ? xScale(0) : xScale(d.shap_value)))
    .attr("y", (_, i) => yScale(String(i)) ?? 0)
    .attr("width", (d) => Math.abs(xScale(d.shap_value) - xScale(0)))
    .attr("height", yScale.bandwidth())
    .attr("rx", 3)
    .attr("fill", (d) => (d.shap_value >= 0 ? "#ef4444" : "#3b82f6"))
    .attr("opacity", 0.85);

  // Value labels (right of bar)
  g.selectAll<SVGTextElement, SHAPFactor>("text.value")
    .data(factors)
    .join("text")
    .attr("class", "value")
    .attr("x", (d) =>
      d.shap_value >= 0
        ? xScale(d.shap_value) + 4
        : xScale(d.shap_value) - 4
    )
    .attr("y", (_, i) => (yScale(String(i)) ?? 0) + yScale.bandwidth() / 2)
    .attr("dy", "0.35em")
    .attr("text-anchor", (d) => (d.shap_value >= 0 ? "start" : "end"))
    .attr("font-size", 11)
    .attr("fill", "#94a3b8")
    .text((d) => d.shap_value.toFixed(3));

  // Y axis — feature labels
  g.selectAll<SVGTextElement, SHAPFactor>("text.label")
    .data(factors)
    .join("text")
    .attr("class", "label")
    .attr("x", -8)
    .attr("y", (_, i) => (yScale(String(i)) ?? 0) + yScale.bandwidth() / 2)
    .attr("dy", "0.35em")
    .attr("text-anchor", "end")
    .attr("font-size", 12)
    .attr("fill", "#94a3b8")
    .text((d) => featureLabel(d.feature));

  // X axis
  const xAxis = d3
    .axisBottom(xScale)
    .ticks(5)
    .tickFormat((v) => String(Number(v).toFixed(2)));

  g.append("g")
    .attr("transform", `translate(0,${innerHeight})`)
    .call(xAxis)
    .call((ax) => ax.select(".domain").attr("stroke", "rgba(99,130,201,0.2)"))
    .call((ax) =>
      ax
        .selectAll(".tick line")
        .attr("stroke", "rgba(99,130,201,0.1)")
        .attr("y1", -innerHeight)
    )
    .call((ax) =>
      ax.selectAll(".tick text").attr("font-size", 11).attr("fill", "#475569")
    );

  // Legend
  const legend = svg
    .append("g")
    .attr(
      "transform",
      `translate(${MARGIN.left},${totalHeight - MARGIN.bottom + 18})`
    );

  [
    { color: "#ef4444", label: "Increases risk" },
    { color: "#3b82f6", label: "Decreases risk" },
  ].forEach(({ color, label }, i) => {
    const x = i * 140;
    legend
      .append("rect")
      .attr("x", x)
      .attr("y", 0)
      .attr("width", 10)
      .attr("height", 10)
      .attr("rx", 2)
      .attr("fill", color)
      .attr("opacity", 0.85);
    legend
      .append("text")
      .attr("x", x + 14)
      .attr("y", 9)
      .attr("font-size", 11)
      .attr("fill", "#64748b")
      .text(label);
  });
}

// ── Component ─────────────────────────────────────────────────────────────────

interface SHAPChartProps {
  explanation: Explanation | null;
}

export default function SHAPChart({ explanation }: SHAPChartProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const factors = explanation?.top_factors ?? [];
  const hasSHAP = !explanation?.shap_failed && factors.length > 0;

  useEffect(() => {
    if (!hasSHAP || !svgRef.current || !containerRef.current) return;

    const containerWidth = containerRef.current.clientWidth || 600;
    renderChart(svgRef.current, factors, containerWidth);

    // Re-render on resize
    const observer = new ResizeObserver(() => {
      if (svgRef.current && containerRef.current) {
        renderChart(
          svgRef.current,
          factors,
          containerRef.current.clientWidth || 600
        );
      }
    });
    observer.observe(containerRef.current);
    return () => observer.disconnect();
  }, [factors, hasSHAP]);

  return (
    <section aria-labelledby="shap-heading">
      <h2 id="shap-heading" style={{ fontSize: "0.95rem", fontWeight: 600, color: "var(--text-primary)", marginBottom: "0.75rem" }}>
        Top Contributing Factors (SHAP)
      </h2>

      {!explanation ? (
        <div style={{ height: "8rem", display: "flex", alignItems: "center", justifyContent: "center", fontSize: "0.875rem", color: "var(--text-muted)" }}>
          No explanation data available.
        </div>
      ) : explanation.shap_failed ? (
        <div style={{ borderRadius: "0.5rem", border: "1px solid rgba(245,158,11,0.25)", background: "rgba(245,158,11,0.08)", padding: "0.625rem 0.875rem", fontSize: "0.8rem", color: "#fbbf24" }}>
          SHAP computation failed. Rule-based factors shown below.
        </div>
      ) : factors.length === 0 ? (
        <div style={{ height: "8rem", display: "flex", alignItems: "center", justifyContent: "center", fontSize: "0.875rem", color: "var(--text-muted)" }}>
          No SHAP factors — ML scores may be null (fewer than 3 bids).
        </div>
      ) : (
        <div ref={containerRef} className="w-full overflow-x-auto">
          <svg ref={svgRef} className="block" />
        </div>
      )}
    </section>
  );
}
