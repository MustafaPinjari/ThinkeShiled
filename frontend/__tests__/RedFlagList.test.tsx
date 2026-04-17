/**
 * Unit tests for RedFlagList component.
 * Validates: Requirement 3 (red flag display), Requirement 6.4 (rule text + trigger data).
 */
import React from "react";
import { render, screen } from "@testing-library/react";
import RedFlagList from "@/components/ui/RedFlagList";
import type { RedFlag } from "@/types/tender";

const makeFlag = (overrides: Partial<RedFlag> = {}): RedFlag => ({
  id: 1,
  flag_type: "SINGLE_BIDDER",
  severity: "HIGH",
  rule_version: "1.0",
  trigger_data: { bid_count: 1 },
  is_active: true,
  raised_at: "2024-03-01T10:00:00Z",
  cleared_at: null,
  rule_description: "Only one bidder submitted a bid.",
  ...overrides,
});

describe("RedFlagList", () => {
  it("renders empty state when no flags", () => {
    render(<RedFlagList redFlags={[]} />);
    expect(screen.getByText(/no red flags detected/i)).toBeInTheDocument();
  });

  it("renders loading skeleton when loading=true", () => {
    const { container } = render(<RedFlagList redFlags={[]} loading />);
    expect(container.querySelector(".animate-pulse")).toBeInTheDocument();
  });

  it("renders flag type label", () => {
    render(<RedFlagList redFlags={[makeFlag()]} />);
    expect(screen.getByText("Single Bidder")).toBeInTheDocument();
  });

  it("renders severity badge", () => {
    render(<RedFlagList redFlags={[makeFlag({ severity: "HIGH" })]} />);
    expect(screen.getByText("HIGH")).toBeInTheDocument();
  });

  it("renders MEDIUM severity badge", () => {
    render(<RedFlagList redFlags={[makeFlag({ severity: "MEDIUM", flag_type: "PRICE_ANOMALY" })]} />);
    expect(screen.getByText("MEDIUM")).toBeInTheDocument();
  });

  it("renders rule description text", () => {
    render(<RedFlagList redFlags={[makeFlag()]} />);
    expect(screen.getByText("Only one bidder submitted a bid.")).toBeInTheDocument();
  });

  it("renders trigger data key-value pairs", () => {
    render(<RedFlagList redFlags={[makeFlag({ trigger_data: { bid_count: 1 } })]} />);
    expect(screen.getByText("bid count:")).toBeInTheDocument();
    expect(screen.getByText("1")).toBeInTheDocument();
  });

  it("shows 'Cleared' badge for inactive flags", () => {
    render(
      <RedFlagList
        redFlags={[makeFlag({ is_active: false, cleared_at: "2024-04-01T10:00:00Z" })]}
      />
    );
    expect(screen.getByText("Cleared")).toBeInTheDocument();
  });

  it("shows active count in header", () => {
    const flags = [
      makeFlag({ id: 1, is_active: true }),
      makeFlag({ id: 2, is_active: false, cleared_at: "2024-04-01T00:00:00Z" }),
    ];
    render(<RedFlagList redFlags={flags} />);
    expect(screen.getByText(/1 active/i)).toBeInTheDocument();
    expect(screen.getByText(/1 cleared/i)).toBeInTheDocument();
  });

  it("renders all known flag type labels", () => {
    const flagTypes = [
      "SINGLE_BIDDER",
      "PRICE_ANOMALY",
      "REPEAT_WINNER",
      "SHORT_DEADLINE",
      "LINKED_ENTITIES",
      "COVER_BID_PATTERN",
    ] as const;
    const flags = flagTypes.map((ft, i) =>
      makeFlag({ id: i, flag_type: ft })
    );
    render(<RedFlagList redFlags={flags} />);
    expect(screen.getByText("Single Bidder")).toBeInTheDocument();
    expect(screen.getByText("Price Anomaly")).toBeInTheDocument();
    expect(screen.getByText("Repeat Winner")).toBeInTheDocument();
    expect(screen.getByText("Short Deadline")).toBeInTheDocument();
    expect(screen.getByText("Linked Entities")).toBeInTheDocument();
    expect(screen.getByText("Cover Bid Pattern")).toBeInTheDocument();
  });

  it("renders raised_at timestamp", () => {
    render(<RedFlagList redFlags={[makeFlag()]} />);
    expect(screen.getByText(/01 Mar 2024/)).toBeInTheDocument();
  });
});
