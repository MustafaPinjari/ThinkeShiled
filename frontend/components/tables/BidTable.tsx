"use client";

import React, { useState } from "react";
import { format } from "date-fns";
import type { Bid } from "@/types/tender";

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmt(value: number | null | undefined, decimals = 3): string {
  if (value === null || value === undefined) return "—";
  return value.toFixed(decimals);
}

function fmtCurrency(value: string | number): string {
  const n = typeof value === "string" ? parseFloat(value) : value;
  if (isNaN(n)) return String(value);
  return n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function deviationClass(pct: number | null | undefined): string {
  if (pct === null || pct === undefined) return "text-gray-500";
  const abs = Math.abs(pct * 100);
  if (abs > 40) return "text-red-600 font-semibold";
  if (abs > 20) return "text-amber-600";
  return "text-green-600";
}

// ── Bid screen tooltip labels ─────────────────────────────────────────────────

const SCREEN_TOOLTIPS: Record<string, string> = {
  cv_bids: "Coefficient of variation of all bid amounts (low = suspiciously similar bids)",
  bid_spread_ratio: "Max bid / Min bid (low = cover bids not meaningfully different)",
  norm_winning_distance: "Normalized distance of winning bid from mean (large negative = winner far below market)",
  single_bidder_flag: "1 if only one bidder submitted",
  price_deviation_pct: "Winning bid deviation from estimated value",
  deadline_days: "Days between publication and submission deadline",
  repeat_winner_rate: "Bidder's win rate in this category over 12 months",
  bidder_count: "Total number of bids submitted",
  winner_bid_rank: "Rank of winning bid (1 = lowest)",
};

// ── Bid screens panel ─────────────────────────────────────────────────────────

function BidScreensPanel({ bid }: { bid: Bid }) {
  const s = bid.bid_screens;
  if (!s) {
    return (
      <td
        colSpan={3}
        className="px-4 py-2 text-xs text-gray-400 italic"
      >
        Bid screens not available (requires ≥ 3 bids)
      </td>
    );
  }

  return (
    <>
      <td className="px-4 py-2 text-xs text-center tabular-nums">
        <span title={SCREEN_TOOLTIPS.cv_bids}>{fmt(s.cv_bids)}</span>
      </td>
      <td className="px-4 py-2 text-xs text-center tabular-nums">
        <span title={SCREEN_TOOLTIPS.bid_spread_ratio}>{fmt(s.bid_spread_ratio)}</span>
      </td>
      <td className="px-4 py-2 text-xs text-center tabular-nums">
        <span title={SCREEN_TOOLTIPS.norm_winning_distance}>
          {fmt(s.norm_winning_distance)}
        </span>
      </td>
    </>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

interface BidTableProps {
  bids: Bid[];
  estimatedValue: number | null;
}

export default function BidTable({ bids, estimatedValue }: BidTableProps) {
  const [showScreens, setShowScreens] = useState(false);

  const hasScreens = bids.some((b) => b.bid_screens != null);

  // Sort bids by amount ascending (lowest first)
  const sorted = [...bids].sort(
    (a, b) => parseFloat(a.bid_amount) - parseFloat(b.bid_amount)
  );

  return (
    <section aria-labelledby="bids-heading">
      <div className="flex items-center justify-between mb-3">
        <h2
          id="bids-heading"
          className="text-base font-semibold text-gray-900"
        >
          Bids
          {bids.length > 0 && (
            <span className="ml-2 text-sm font-normal text-gray-500">
              ({bids.length})
            </span>
          )}
        </h2>
        {hasScreens && (
          <button
            onClick={() => setShowScreens((v) => !v)}
            className="text-xs text-blue-600 hover:underline"
          >
            {showScreens ? "Hide bid screens" : "Show bid screens"}
          </button>
        )}
      </div>

      {bids.length === 0 ? (
        <p className="text-sm text-gray-400 py-4">
          No bids recorded for this tender.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200 bg-gray-50 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">
                <th className="px-4 py-2 w-8">#</th>
                <th className="px-4 py-2">Bidder</th>
                <th className="px-4 py-2 text-right">Bid Amount</th>
                {estimatedValue !== null && (
                  <th className="px-4 py-2 text-right">vs Estimate</th>
                )}
                <th className="px-4 py-2 whitespace-nowrap">Submitted</th>
                {showScreens && (
                  <>
                    <th
                      className="px-4 py-2 text-center whitespace-nowrap"
                      title={SCREEN_TOOLTIPS.cv_bids}
                    >
                      CV Bids
                    </th>
                    <th
                      className="px-4 py-2 text-center whitespace-nowrap"
                      title={SCREEN_TOOLTIPS.bid_spread_ratio}
                    >
                      Spread Ratio
                    </th>
                    <th
                      className="px-4 py-2 text-center whitespace-nowrap"
                      title={SCREEN_TOOLTIPS.norm_winning_distance}
                    >
                      Norm Distance
                    </th>
                  </>
                )}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {sorted.map((bid, idx) => {
                const amount = parseFloat(bid.bid_amount);
                const deviationPct =
                  estimatedValue && estimatedValue > 0
                    ? (amount - estimatedValue) / estimatedValue
                    : null;
                const isLowest = idx === 0;

                return (
                  <tr
                    key={bid.id}
                    className={`hover:bg-gray-50 transition-colors ${isLowest ? "bg-green-50/40" : ""}`}
                  >
                    <td className="px-4 py-2 text-gray-400 text-xs">
                      {isLowest ? (
                        <span
                          className="inline-flex items-center justify-center h-5 w-5 rounded-full bg-green-100 text-green-700 text-xs font-bold"
                          title="Lowest bid (likely winner)"
                        >
                          ★
                        </span>
                      ) : (
                        idx + 1
                      )}
                    </td>
                    <td className="px-4 py-2 text-gray-900 max-w-[200px] truncate">
                      {bid.bidder_name}
                    </td>
                    <td className="px-4 py-2 text-right font-mono tabular-nums text-gray-900">
                      {fmtCurrency(bid.bid_amount)}
                    </td>
                    {estimatedValue !== null && (
                      <td
                        className={`px-4 py-2 text-right tabular-nums text-xs ${deviationClass(deviationPct)}`}
                      >
                        {deviationPct !== null
                          ? `${deviationPct >= 0 ? "+" : ""}${(deviationPct * 100).toFixed(1)}%`
                          : "—"}
                      </td>
                    )}
                    <td className="px-4 py-2 text-gray-500 text-xs whitespace-nowrap">
                      {bid.submission_timestamp
                        ? format(
                            new Date(bid.submission_timestamp),
                            "dd MMM yyyy HH:mm"
                          )
                        : "—"}
                    </td>
                    {showScreens && <BidScreensPanel bid={bid} />}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {bids.length > 0 && bids.length < 3 && (
        <p className="mt-2 text-xs text-amber-700 bg-amber-50 rounded px-3 py-1.5">
          Fewer than 3 bids — ML bid screens and anomaly scores are not
          computed for this tender.
        </p>
      )}
    </section>
  );
}
