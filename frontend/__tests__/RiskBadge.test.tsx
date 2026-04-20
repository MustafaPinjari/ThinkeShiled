/**
 * Unit tests for RiskBadge component.
 * Validates: Requirement 5.4 — colour-coded risk badge based on fraud risk score.
 */
import React from "react";
import { render, screen } from "@testing-library/react";
import RiskBadge from "@/components/ui/RiskBadge";

describe("RiskBadge", () => {
  // ── Null / pending ──────────────────────────────────────────────────────────

  it("renders badge-gray with 'Pending' text when score is null", () => {
    const { container } = render(<RiskBadge score={null} />);
    const badge = container.querySelector(".badge");
    expect(badge).toHaveClass("badge-gray");
    expect(screen.getByText("Pending")).toBeInTheDocument();
  });

  it("has correct aria-label when score is null", () => {
    render(<RiskBadge score={null} />);
    expect(
      screen.getByLabelText("Risk score not yet computed")
    ).toBeInTheDocument();
  });

  // ── Low risk: score < 40 ────────────────────────────────────────────────────

  it("renders badge-green for score 0 (low risk)", () => {
    const { container } = render(<RiskBadge score={0} />);
    expect(container.querySelector(".badge")).toHaveClass("badge-green");
  });

  it("renders badge-green for score 20 (low risk)", () => {
    const { container } = render(<RiskBadge score={20} />);
    expect(container.querySelector(".badge")).toHaveClass("badge-green");
  });

  it("renders badge-green for score 39 (boundary: still low risk)", () => {
    const { container } = render(<RiskBadge score={39} />);
    expect(container.querySelector(".badge")).toHaveClass("badge-green");
  });

  it("shows the numeric score for low-risk badge when showScore=true (default)", () => {
    render(<RiskBadge score={25} />);
    expect(screen.getByText("25")).toBeInTheDocument();
  });

  it("has correct aria-label for low-risk score", () => {
    render(<RiskBadge score={25} />);
    expect(screen.getByLabelText("Low risk, score 25")).toBeInTheDocument();
  });

  // ── Medium risk: score 40–69 ────────────────────────────────────────────────

  it("renders badge-amber for score 40 (boundary: first medium risk)", () => {
    const { container } = render(<RiskBadge score={40} />);
    expect(container.querySelector(".badge")).toHaveClass("badge-amber");
  });

  it("renders badge-amber for score 55 (medium risk)", () => {
    const { container } = render(<RiskBadge score={55} />);
    expect(container.querySelector(".badge")).toHaveClass("badge-amber");
  });

  it("renders badge-amber for score 69 (boundary: last medium risk)", () => {
    const { container } = render(<RiskBadge score={69} />);
    expect(container.querySelector(".badge")).toHaveClass("badge-amber");
  });

  it("shows the numeric score for medium-risk badge when showScore=true (default)", () => {
    render(<RiskBadge score={55} />);
    expect(screen.getByText("55")).toBeInTheDocument();
  });

  it("has correct aria-label for medium-risk score", () => {
    render(<RiskBadge score={55} />);
    expect(screen.getByLabelText("Medium risk, score 55")).toBeInTheDocument();
  });

  // ── High risk: score ≥ 70 ───────────────────────────────────────────────────

  it("renders badge-red for score 70 (boundary: first high risk)", () => {
    const { container } = render(<RiskBadge score={70} />);
    expect(container.querySelector(".badge")).toHaveClass("badge-red");
  });

  it("renders badge-red for score 85 (high risk)", () => {
    const { container } = render(<RiskBadge score={85} />);
    expect(container.querySelector(".badge")).toHaveClass("badge-red");
  });

  it("renders badge-red for score 100 (maximum high risk)", () => {
    const { container } = render(<RiskBadge score={100} />);
    expect(container.querySelector(".badge")).toHaveClass("badge-red");
  });

  it("shows the numeric score for high-risk badge when showScore=true (default)", () => {
    render(<RiskBadge score={85} />);
    expect(screen.getByText("85")).toBeInTheDocument();
  });

  it("has correct aria-label for high-risk score", () => {
    render(<RiskBadge score={85} />);
    expect(screen.getByLabelText("High risk, score 85")).toBeInTheDocument();
  });

  // ── showScore=false ─────────────────────────────────────────────────────────

  it("shows 'Low' text instead of score when showScore=false for low risk", () => {
    render(<RiskBadge score={20} showScore={false} />);
    expect(screen.getByText("Low")).toBeInTheDocument();
    expect(screen.queryByText("20")).not.toBeInTheDocument();
  });

  it("shows 'Medium' text instead of score when showScore=false for medium risk", () => {
    render(<RiskBadge score={55} showScore={false} />);
    expect(screen.getByText("Medium")).toBeInTheDocument();
    expect(screen.queryByText("55")).not.toBeInTheDocument();
  });

  it("shows 'High' text instead of score when showScore=false for high risk", () => {
    render(<RiskBadge score={85} showScore={false} />);
    expect(screen.getByText("High")).toBeInTheDocument();
    expect(screen.queryByText("85")).not.toBeInTheDocument();
  });

  // ── Mutual exclusivity ──────────────────────────────────────────────────────

  it("does not apply badge-amber or badge-red for low-risk score", () => {
    const { container } = render(<RiskBadge score={20} />);
    const badge = container.querySelector(".badge");
    expect(badge).not.toHaveClass("badge-amber");
    expect(badge).not.toHaveClass("badge-red");
  });

  it("does not apply badge-green or badge-red for medium-risk score", () => {
    const { container } = render(<RiskBadge score={55} />);
    const badge = container.querySelector(".badge");
    expect(badge).not.toHaveClass("badge-green");
    expect(badge).not.toHaveClass("badge-red");
  });

  it("does not apply badge-green or badge-amber for high-risk score", () => {
    const { container } = render(<RiskBadge score={85} />);
    const badge = container.querySelector(".badge");
    expect(badge).not.toHaveClass("badge-green");
    expect(badge).not.toHaveClass("badge-amber");
  });
});
