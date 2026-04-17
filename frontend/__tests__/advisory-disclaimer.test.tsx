/**
 * Unit tests: Advisory disclaimer presence on all components that display Fraud_Risk_Score.
 * Validates: Requirement 11.6 — disclaimer must appear on every page showing a score.
 *
 * Components verified:
 *   - ScoreCard (tender detail page)
 *   - TenderTable (dashboard)
 */
import React from "react";
import { render, screen } from "@testing-library/react";
import ScoreCard from "@/components/ui/ScoreCard";
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

const DISCLAIMER_REGEX = /advisory only/i;
const HUMAN_REVIEW_REGEX = /human review required/i;

const makeTender = (overrides: Partial<TenderListItem> = {}): TenderListItem => ({
  id: 1,
  tender_id: "TND-001",
  title: "Test Tender",
  category: "Construction",
  estimated_value: "500000.00",
  currency: "INR",
  submission_deadline: "2024-06-15T00:00:00Z",
  buyer_id: "B1",
  buyer_name: "Test Buyer",
  status: "ACTIVE",
  created_at: "2024-01-01T00:00:00Z",
  latest_score: 75,
  active_red_flag_count: 1,
  ...overrides,
});

const tableProps = {
  tenders: [makeTender()],
  loading: false,
  totalCount: 1,
  currentPage: 1,
  totalPages: 1,
  ordering: "-score",
  onPageChange: jest.fn(),
  onSortChange: jest.fn(),
};

describe("Advisory disclaimer — Requirement 11.6", () => {
  describe("ScoreCard", () => {
    it("shows advisory disclaimer when score is a number", () => {
      render(<ScoreCard score={75} />);
      expect(screen.getByText(DISCLAIMER_REGEX)).toBeInTheDocument();
      expect(screen.getByText(HUMAN_REVIEW_REGEX)).toBeInTheDocument();
    });

    it("shows advisory disclaimer when score is null", () => {
      render(<ScoreCard score={null} />);
      expect(screen.getByText(DISCLAIMER_REGEX)).toBeInTheDocument();
    });

    it("does NOT show disclaimer in loading state (skeleton only)", () => {
      render(<ScoreCard score={null} loading />);
      // Loading skeleton should not show disclaimer text
      expect(screen.queryByText(DISCLAIMER_REGEX)).not.toBeInTheDocument();
    });
  });

  describe("TenderTable", () => {
    it("shows advisory disclaimer banner", () => {
      render(<TenderTable {...tableProps} />);
      expect(screen.getByText(DISCLAIMER_REGEX)).toBeInTheDocument();
    });

    it("shows advisory disclaimer even when table is empty", () => {
      render(
        <TenderTable {...tableProps} tenders={[]} totalCount={0} totalPages={0} />
      );
      expect(screen.getByText(DISCLAIMER_REGEX)).toBeInTheDocument();
    });

    it("shows advisory disclaimer when loading", () => {
      render(<TenderTable {...tableProps} loading tenders={[]} />);
      expect(screen.getByText(DISCLAIMER_REGEX)).toBeInTheDocument();
    });
  });
});
