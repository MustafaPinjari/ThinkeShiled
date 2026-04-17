/**
 * Unit tests for TenderTable component.
 * Validates: Requirement 9.1 (sortable columns), 9.5 (color-coded badges),
 *            11.6 (advisory disclaimer), pagination controls.
 */
import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import TenderTable from "@/components/tables/TenderTable";
import type { TenderListItem } from "@/types/tender";

// Next.js Link stub
jest.mock("next/link", () => {
  const MockLink = ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  );
  MockLink.displayName = "MockLink";
  return MockLink;
});

const makeTender = (overrides: Partial<TenderListItem> = {}): TenderListItem => ({
  id: 1,
  tender_id: "TND-001",
  title: "Road Construction Phase 1",
  category: "Construction",
  estimated_value: "1000000.00",
  currency: "INR",
  submission_deadline: "2024-06-15T00:00:00Z",
  buyer_id: "BUYER-1",
  buyer_name: "Ministry of Roads",
  status: "ACTIVE",
  created_at: "2024-01-01T00:00:00Z",
  latest_score: 75,
  active_red_flag_count: 2,
  ...overrides,
});

const defaultProps = {
  tenders: [makeTender()],
  loading: false,
  totalCount: 1,
  currentPage: 1,
  totalPages: 1,
  ordering: "-score",
  onPageChange: jest.fn(),
  onSortChange: jest.fn(),
};

describe("TenderTable", () => {
  it("renders advisory disclaimer (Requirement 11.6)", () => {
    render(<TenderTable {...defaultProps} />);
    // The disclaimer text is in a single element — use a partial match
    expect(
      screen.getByText(/advisory only\. human review is required/i)
    ).toBeInTheDocument();
  });

  it("renders tender_id as a link", () => {
    render(<TenderTable {...defaultProps} />);
    const link = screen.getByRole("link", { name: "TND-001" });
    expect(link).toHaveAttribute("href", "/tenders/1");
  });

  it("renders tender title", () => {
    render(<TenderTable {...defaultProps} />);
    expect(screen.getByText("Road Construction Phase 1")).toBeInTheDocument();
  });

  it("renders category and buyer name", () => {
    render(<TenderTable {...defaultProps} />);
    expect(screen.getByText("Construction")).toBeInTheDocument();
    expect(screen.getByText("Ministry of Roads")).toBeInTheDocument();
  });

  it("renders score badge with red color for score >= 70", () => {
    const { container } = render(<TenderTable {...defaultProps} />);
    const badge = container.querySelector(".bg-red-100");
    expect(badge).toBeInTheDocument();
    expect(badge?.textContent).toBe("75");
  });

  it("renders amber badge for score 40–69", () => {
    const { container } = render(
      <TenderTable {...defaultProps} tenders={[makeTender({ latest_score: 55 })]} />
    );
    expect(container.querySelector(".bg-amber-100")).toBeInTheDocument();
  });

  it("renders green badge for score 0–39", () => {
    const { container } = render(
      <TenderTable {...defaultProps} tenders={[makeTender({ latest_score: 20 })]} />
    );
    expect(container.querySelector(".bg-green-100")).toBeInTheDocument();
  });

  it("renders N/A badge when score is null", () => {
    render(
      <TenderTable {...defaultProps} tenders={[makeTender({ latest_score: null })]} />
    );
    expect(screen.getByText("N/A")).toBeInTheDocument();
  });

  it("renders active red flag count", () => {
    render(<TenderTable {...defaultProps} />);
    // flag count badge
    expect(screen.getByText("2")).toBeInTheDocument();
  });

  it("renders '—' when active_red_flag_count is 0", () => {
    render(
      <TenderTable
        {...defaultProps}
        tenders={[makeTender({ active_red_flag_count: 0 })]}
      />
    );
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("renders loading skeleton rows when loading=true", () => {
    const { container } = render(
      <TenderTable {...defaultProps} loading tenders={[]} />
    );
    expect(container.querySelectorAll(".animate-pulse").length).toBeGreaterThan(0);
  });

  it("renders empty state message when no tenders", () => {
    render(
      <TenderTable {...defaultProps} tenders={[]} totalCount={0} totalPages={0} />
    );
    expect(screen.getByText(/no tenders found/i)).toBeInTheDocument();
  });

  it("calls onSortChange when score column header is clicked", () => {
    const onSortChange = jest.fn();
    render(<TenderTable {...defaultProps} onSortChange={onSortChange} />);
    // Use columnheader role to avoid matching the disclaimer text
    fireEvent.click(screen.getByRole("columnheader", { name: /risk score/i }));
    expect(onSortChange).toHaveBeenCalledWith("score");
  });

  it("calls onSortChange with descending when same column clicked twice", () => {
    const onSortChange = jest.fn();
    render(
      <TenderTable {...defaultProps} ordering="score" onSortChange={onSortChange} />
    );
    fireEvent.click(screen.getByRole("columnheader", { name: /risk score/i }));
    expect(onSortChange).toHaveBeenCalledWith("-score");
  });

  it("calls onPageChange when next page button is clicked", () => {
    const onPageChange = jest.fn();
    render(
      <TenderTable
        {...defaultProps}
        totalCount={50}
        totalPages={2}
        onPageChange={onPageChange}
      />
    );
    fireEvent.click(screen.getByLabelText("Next page"));
    expect(onPageChange).toHaveBeenCalledWith(2);
  });

  it("disables previous page button on first page", () => {
    render(<TenderTable {...defaultProps} />);
    expect(screen.getByLabelText("Previous page")).toBeDisabled();
  });

  it("shows pagination count text", () => {
    render(
      <TenderTable {...defaultProps} totalCount={100} totalPages={4} />
    );
    expect(screen.getByText(/showing 1–25 of 100/i)).toBeInTheDocument();
  });
});
