"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import type { TenderFilters } from "@/types/tender";

const FLAG_TYPES = [
  { value: "", label: "All flag types" },
  { value: "SINGLE_BIDDER", label: "Single Bidder" },
  { value: "PRICE_ANOMALY", label: "Price Anomaly" },
  { value: "REPEAT_WINNER", label: "Repeat Winner" },
  { value: "SHORT_DEADLINE", label: "Short Deadline" },
  { value: "LINKED_ENTITIES", label: "Linked Entities" },
  { value: "COVER_BID_PATTERN", label: "Cover Bid Pattern" },
];

const inputStyle: React.CSSProperties = {
  width: "100%",
  background: "rgba(255,255,255,0.04)",
  border: "1px solid var(--border-strong)",
  borderRadius: "8px",
  padding: "0.5rem 0.75rem",
  color: "var(--text-primary)",
  fontSize: "0.8rem",
  outline: "none",
  colorScheme: "dark",
};

const labelStyle: React.CSSProperties = {
  display: "block",
  color: "var(--text-muted)",
  fontSize: "0.68rem",
  fontWeight: 600,
  letterSpacing: "0.06em",
  textTransform: "uppercase",
  marginBottom: "0.375rem",
};

interface FilterPanelProps {
  filters: TenderFilters;
  onFilterChange: (filters: Partial<TenderFilters>) => void;
}

export default function FilterPanel({ filters, onFilterChange }: FilterPanelProps) {
  const [scoreMin, setScoreMin] = useState(filters.score_min ?? "");
  const [scoreMax, setScoreMax] = useState(filters.score_max ?? "");
  const [category, setCategory] = useState(filters.category ?? "");
  const [buyerName, setBuyerName] = useState(filters.buyer_name ?? "");
  const [dateFrom, setDateFrom] = useState(filters.date_from ?? "");
  const [dateTo, setDateTo] = useState(filters.date_to ?? "");
  const [flagType, setFlagType] = useState(filters.flag_type ?? "");
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const emitDebounced = useCallback((patch: Partial<TenderFilters>) => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => onFilterChange(patch), 400);
  }, [onFilterChange]);

  const emitImmediate = useCallback((patch: Partial<TenderFilters>) => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    onFilterChange(patch);
  }, [onFilterChange]);

  useEffect(() => () => { if (debounceRef.current) clearTimeout(debounceRef.current); }, []);

  function handleReset() {
    setScoreMin(""); setScoreMax(""); setCategory(""); setBuyerName("");
    setDateFrom(""); setDateTo(""); setFlagType("");
    emitImmediate({ score_min: undefined, score_max: undefined, category: undefined,
      buyer_name: undefined, date_from: undefined, date_to: undefined, flag_type: undefined });
  }

  const hasActive = scoreMin || scoreMax || category || buyerName || dateFrom || dateTo || flagType;

  const focusStyle = (e: React.FocusEvent<HTMLInputElement | HTMLSelectElement>) => {
    (e.target as HTMLElement).style.borderColor = "var(--accent)";
    (e.target as HTMLElement).style.boxShadow = "0 0 0 3px var(--accent-glow)";
  };
  const blurStyle = (e: React.FocusEvent<HTMLInputElement | HTMLSelectElement>) => {
    (e.target as HTMLElement).style.borderColor = "var(--border-strong)";
    (e.target as HTMLElement).style.boxShadow = "none";
  };

  return (
    <div
      className="rounded-2xl p-4 space-y-5"
      style={{ background: "var(--bg-card)", border: "1px solid var(--border)" }}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ color: "var(--text-muted)" }}>
            <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/>
          </svg>
          <span style={{ color: "var(--text-primary)", fontSize: "0.8rem", fontWeight: 600 }}>Filters</span>
          {hasActive && (
            <span className="badge badge-blue" style={{ fontSize: "0.6rem", padding: "0.1rem 0.4rem" }}>Active</span>
          )}
        </div>
        {hasActive && (
          <button onClick={handleReset} style={{ color: "var(--accent)", fontSize: "0.72rem", background: "none", border: "none", cursor: "pointer" }}>
            Clear all
          </button>
        )}
      </div>

      {/* Score range */}
      <div>
        <label style={labelStyle}>Risk Score</label>
        <div className="flex items-center gap-2">
          <input type="number" min={0} max={100} placeholder="Min" value={scoreMin}
            onChange={(e) => { setScoreMin(e.target.value); emitDebounced({ score_min: e.target.value || undefined }); }}
            style={inputStyle} onFocus={focusStyle} onBlur={blurStyle} aria-label="Min score" />
          <span style={{ color: "var(--text-muted)", fontSize: "0.7rem" }}>–</span>
          <input type="number" min={0} max={100} placeholder="Max" value={scoreMax}
            onChange={(e) => { setScoreMax(e.target.value); emitDebounced({ score_max: e.target.value || undefined }); }}
            style={inputStyle} onFocus={focusStyle} onBlur={blurStyle} aria-label="Max score" />
        </div>
      </div>

      {/* Category */}
      <div>
        <label style={labelStyle}>Category</label>
        <input type="text" placeholder="e.g. Construction" value={category}
          onChange={(e) => { setCategory(e.target.value); emitDebounced({ category: e.target.value || undefined }); }}
          style={inputStyle} onFocus={focusStyle} onBlur={blurStyle} aria-label="Category" />
      </div>

      {/* Buyer */}
      <div>
        <label style={labelStyle}>Buyer Name</label>
        <input type="text" placeholder="Search buyer…" value={buyerName}
          onChange={(e) => { setBuyerName(e.target.value); emitDebounced({ buyer_name: e.target.value || undefined }); }}
          style={inputStyle} onFocus={focusStyle} onBlur={blurStyle} aria-label="Buyer name" />
      </div>

      {/* Date range */}
      <div>
        <label style={labelStyle}>Deadline Range</label>
        <div className="space-y-2">
          <input type="date" value={dateFrom}
            onChange={(e) => { setDateFrom(e.target.value); emitImmediate({ date_from: e.target.value || undefined }); }}
            style={inputStyle} onFocus={focusStyle} onBlur={blurStyle} aria-label="From date" />
          <input type="date" value={dateTo}
            onChange={(e) => { setDateTo(e.target.value); emitImmediate({ date_to: e.target.value || undefined }); }}
            style={inputStyle} onFocus={focusStyle} onBlur={blurStyle} aria-label="To date" />
        </div>
      </div>

      {/* Flag type */}
      <div>
        <label style={labelStyle}>Red Flag Type</label>
        <select value={flagType}
          onChange={(e) => { setFlagType(e.target.value); emitImmediate({ flag_type: e.target.value || undefined }); }}
          style={{ ...inputStyle, cursor: "pointer" }}
          onFocus={focusStyle} onBlur={blurStyle} aria-label="Flag type"
        >
          {FLAG_TYPES.map((ft) => (
            <option key={ft.value} value={ft.value} style={{ background: "var(--bg-elevated)" }}>
              {ft.label}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}
