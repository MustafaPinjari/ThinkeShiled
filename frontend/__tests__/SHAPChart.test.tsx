/**
 * Unit tests for SHAPChart component.
 * Validates: Requirement 6.1–6.3 (SHAP display, fallback, top-5 factors).
 * D3 rendering is stubbed; visual correctness is covered by Playwright E2E.
 */
import React from "react";
import { render, screen } from "@testing-library/react";
import SHAPChart from "@/components/charts/SHAPChart";
import type { Explanation } from "@/types/tender";

const makeExplanation = (overrides: Partial<Explanation> = {}): Explanation => ({
  tender_id: 1,
  model_version: "v1.0",
  rule_engine_version: "1.0",
  shap_values: { cv_bids: 0.3, bid_spread_ratio: -0.1 },
  top_factors: [
    { feature: "cv_bids", shap_value: 0.3, plain_language: "Bid variation is low." },
    { feature: "bid_spread_ratio", shap_value: -0.1, plain_language: "Bid spread is normal." },
  ],
  shap_failed: false,
  red_flags: [],
  computed_at: "2024-03-01T10:00:00Z",
  ...overrides,
});

describe("SHAPChart", () => {
  it("renders section heading", () => {
    render(<SHAPChart explanation={makeExplanation()} />);
    expect(screen.getByText(/top contributing factors/i)).toBeInTheDocument();
  });

  it("renders 'No explanation data available' when explanation is null", () => {
    render(<SHAPChart explanation={null} />);
    expect(screen.getByText(/no explanation data available/i)).toBeInTheDocument();
  });

  it("renders SHAP fallback message when shap_failed=true", () => {
    render(<SHAPChart explanation={makeExplanation({ shap_failed: true, top_factors: [] })} />);
    expect(screen.getByText(/shap computation failed/i)).toBeInTheDocument();
  });

  it("renders 'No SHAP factors available' when top_factors is empty and not failed", () => {
    render(<SHAPChart explanation={makeExplanation({ top_factors: [] })} />);
    expect(screen.getByText(/no shap factors available/i)).toBeInTheDocument();
  });

  it("renders SVG container when factors are present", () => {
    const { container } = render(<SHAPChart explanation={makeExplanation()} />);
    // The container div wrapping the SVG should be present
    expect(container.querySelector("svg")).toBeInTheDocument();
  });

  it("renders aria-label on the section", () => {
    render(<SHAPChart explanation={makeExplanation()} />);
    expect(screen.getByRole("region", { name: /top contributing factors/i })).toBeInTheDocument();
  });
});
