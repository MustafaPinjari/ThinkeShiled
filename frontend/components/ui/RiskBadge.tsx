"use client";

import React from "react";

interface RiskBadgeProps {
  score: number | null;
  showScore?: boolean;
}

/**
 * Colour-coded risk badge based on fraud risk score.
 * - Green: score < 40
 * - Amber: score 40–69
 * - Red: score ≥ 70
 */
export default function RiskBadge({ score, showScore = true }: RiskBadgeProps) {
  if (score === null || score === undefined) {
    return (
      <span className="badge badge-gray" aria-label="Risk score not yet computed">
        Pending
      </span>
    );
  }

  if (score >= 70) {
    return (
      <span className="badge badge-red" aria-label={`High risk, score ${score}`}>
        {showScore ? score : "High"}
      </span>
    );
  }

  if (score >= 40) {
    return (
      <span className="badge badge-amber" aria-label={`Medium risk, score ${score}`}>
        {showScore ? score : "Medium"}
      </span>
    );
  }

  return (
    <span className="badge badge-green" aria-label={`Low risk, score ${score}`}>
      {showScore ? score : "Low"}
    </span>
  );
}
