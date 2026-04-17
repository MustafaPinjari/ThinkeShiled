/**
 * Unit tests for ScoreCard component.
 * Validates: Requirement 11.6 (advisory disclaimer), score color bands.
 */
import React from "react";
import { render, screen } from "@testing-library/react";
import ScoreCard from "@/components/ui/ScoreCard";

describe("ScoreCard", () => {
  it("renders the score value", () => {
    render(<ScoreCard score={55} />);
    expect(screen.getByText("55")).toBeInTheDocument();
  });

  it("shows '—' when score is null", () => {
    render(<ScoreCard score={null} />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("shows loading skeleton when loading=true", () => {
    const { container } = render(<ScoreCard score={null} loading />);
    expect(container.querySelector(".animate-pulse")).toBeInTheDocument();
  });

  it("labels score 0–39 as Low Risk", () => {
    render(<ScoreCard score={25} />);
    expect(screen.getByText("Low Risk")).toBeInTheDocument();
  });

  it("labels score 40–69 as Medium Risk", () => {
    render(<ScoreCard score={55} />);
    expect(screen.getByText("Medium Risk")).toBeInTheDocument();
  });

  it("labels score 70–100 as High Risk", () => {
    render(<ScoreCard score={82} />);
    expect(screen.getByText("High Risk")).toBeInTheDocument();
  });

  it("labels null score as N/A", () => {
    render(<ScoreCard score={null} />);
    expect(screen.getByText("N/A")).toBeInTheDocument();
  });

  it("renders advisory disclaimer (Requirement 11.6)", () => {
    render(<ScoreCard score={50} />);
    expect(
      screen.getByText(/advisory only/i)
    ).toBeInTheDocument();
    expect(
      screen.getByText(/human review required/i)
    ).toBeInTheDocument();
  });

  it("progress bar has correct aria attributes", () => {
    render(<ScoreCard score={70} />);
    const bar = screen.getByRole("progressbar");
    expect(bar).toHaveAttribute("aria-valuenow", "70");
    expect(bar).toHaveAttribute("aria-valuemin", "0");
    expect(bar).toHaveAttribute("aria-valuemax", "100");
  });

  it("boundary: score=39 is Low Risk", () => {
    render(<ScoreCard score={39} />);
    expect(screen.getByText("Low Risk")).toBeInTheDocument();
  });

  it("boundary: score=40 is Medium Risk", () => {
    render(<ScoreCard score={40} />);
    expect(screen.getByText("Medium Risk")).toBeInTheDocument();
  });

  it("boundary: score=69 is Medium Risk", () => {
    render(<ScoreCard score={69} />);
    expect(screen.getByText("Medium Risk")).toBeInTheDocument();
  });

  it("boundary: score=70 is High Risk", () => {
    render(<ScoreCard score={70} />);
    expect(screen.getByText("High Risk")).toBeInTheDocument();
  });
});
