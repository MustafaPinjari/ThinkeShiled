/**
 * Unit tests for TenderSubmissionForm (frontend/app/agency/tenders/new/page.tsx).
 * Validates:
 *   Requirement 6.3 — past deadline rejection
 *   Requirement 6.4 — character limit enforcement on spec text
 */
import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

// ── Module mocks ──────────────────────────────────────────────────────────────

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: jest.fn() }),
}));

jest.mock("@/services/agencies", () => ({
  createTender: jest.fn(),
  submitTender: jest.fn(),
}));

// AgencyLayout just renders children in tests
jest.mock("@/components/AgencyLayout", () => ({
  __esModule: true,
  default: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
}));

import NewTenderPage from "@/app/agency/tenders/new/page";
import { createTender, submitTender } from "@/services/agencies";

const mockCreateTender = createTender as jest.MockedFunction<
  typeof createTender
>;
const mockSubmitTender = submitTender as jest.MockedFunction<
  typeof submitTender
>;

// ── Helpers ───────────────────────────────────────────────────────────────────

const SPEC_TEXT_MAX = 100_000;

/** Returns a datetime-local string that is in the future. */
function futureDatetime(offsetMs = 24 * 60 * 60 * 1000): string {
  const d = new Date(Date.now() + offsetMs);
  // datetime-local format: YYYY-MM-DDTHH:MM
  return d.toISOString().slice(0, 16);
}

/** Returns a datetime-local string that is in the past. */
function pastDatetime(offsetMs = 24 * 60 * 60 * 1000): string {
  const d = new Date(Date.now() - offsetMs);
  return d.toISOString().slice(0, 16);
}

/** Fill in all required fields with valid values. */
function fillValidForm(overrides: Partial<Record<string, string>> = {}) {
  const fields = {
    tender_ref: "NHAI/2024/001",
    title: "Construction of NH-48 Bypass",
    category: "Infrastructure",
    estimated_value: "50000000",
    submission_deadline: futureDatetime(),
    buyer_name: "Ministry of Road Transport",
    spec_text: "",
    ...overrides,
  };

  fireEvent.change(screen.getByLabelText(/tender reference number/i), {
    target: { value: fields.tender_ref },
  });
  fireEvent.change(screen.getByLabelText(/^title/i), {
    target: { value: fields.title },
  });

  // Category is a <select>
  fireEvent.change(screen.getByLabelText(/category/i), {
    target: { value: fields.category },
  });

  fireEvent.change(screen.getByLabelText(/estimated value/i), {
    target: { value: fields.estimated_value },
  });
  fireEvent.change(screen.getByLabelText(/submission deadline/i), {
    target: { value: fields.submission_deadline },
  });
  fireEvent.change(screen.getByLabelText(/buyer department name/i), {
    target: { value: fields.buyer_name },
  });

  if (fields.spec_text) {
    fireEvent.change(screen.getByLabelText(/specification text/i), {
      target: { value: fields.spec_text },
    });
  }
}

function clickSubmit() {
  fireEvent.click(
    screen.getByRole("button", { name: /submit for analysis/i })
  );
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("TenderSubmissionForm — past deadline rejection (Requirement 6.3)", () => {
  beforeEach(() => {
    mockCreateTender.mockReset();
    mockSubmitTender.mockReset();
    render(<NewTenderPage />);
  });

  it("shows a validation error when submission deadline is in the past", async () => {
    fillValidForm({ submission_deadline: pastDatetime() });
    clickSubmit();

    await waitFor(() => {
      expect(
        screen.getByText(/submission deadline must be in the future/i)
      ).toBeInTheDocument();
    });
  });

  it("does not call createTender when deadline is in the past", async () => {
    fillValidForm({ submission_deadline: pastDatetime() });
    clickSubmit();

    await waitFor(() => {
      expect(
        screen.getByText(/submission deadline must be in the future/i)
      ).toBeInTheDocument();
    });
    expect(mockCreateTender).not.toHaveBeenCalled();
  });

  it("shows a validation error when submission deadline is missing", async () => {
    fillValidForm({ submission_deadline: "" });
    clickSubmit();

    await waitFor(() => {
      expect(
        screen.getByText(/submission deadline is required/i)
      ).toBeInTheDocument();
    });
  });

  it("does not show a deadline error when deadline is in the future", async () => {
    mockCreateTender.mockResolvedValueOnce({
      id: 1,
      agency: "agency-1",
      submitted_by: null,
      tender_ref: "NHAI/2024/001",
      title: "Test",
      category: "Infrastructure",
      estimated_value: "50000000",
      submission_deadline: futureDatetime(),
      publication_date: null,
      buyer_name: "Ministry",
      spec_text: "",
      status: "DRAFT",
      review_note: "",
      fraud_risk_score: null,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });
    mockSubmitTender.mockResolvedValueOnce({
      message: "Submitted",
      status: "SUBMITTED",
    });

    fillValidForm({ submission_deadline: futureDatetime() });
    clickSubmit();

    await waitFor(() => {
      expect(
        screen.queryByText(/submission deadline must be in the future/i)
      ).not.toBeInTheDocument();
    });
  });
});

describe("TenderSubmissionForm — spec text character limit (Requirement 6.4)", () => {
  beforeEach(() => {
    mockCreateTender.mockReset();
    mockSubmitTender.mockReset();
    render(<NewTenderPage />);
  });

  it("shows a validation error when spec text exceeds 100,000 characters", async () => {
    const oversizedText = "a".repeat(SPEC_TEXT_MAX + 1);
    fillValidForm({ spec_text: oversizedText });
    clickSubmit();

    await waitFor(() => {
      expect(
        screen.getByText(/specification text must not exceed/i)
      ).toBeInTheDocument();
    });
  });

  it("does not call createTender when spec text exceeds the limit", async () => {
    const oversizedText = "a".repeat(SPEC_TEXT_MAX + 1);
    fillValidForm({ spec_text: oversizedText });
    clickSubmit();

    await waitFor(() => {
      expect(
        screen.getByText(/specification text must not exceed/i)
      ).toBeInTheDocument();
    });
    expect(mockCreateTender).not.toHaveBeenCalled();
  });

  it("does not show a spec text error when text is exactly at the limit (100,000 chars)", async () => {
    const exactText = "a".repeat(SPEC_TEXT_MAX);

    mockCreateTender.mockResolvedValueOnce({
      id: 1,
      agency: "agency-1",
      submitted_by: null,
      tender_ref: "NHAI/2024/001",
      title: "Test",
      category: "Infrastructure",
      estimated_value: "50000000",
      submission_deadline: futureDatetime(),
      publication_date: null,
      buyer_name: "Ministry",
      spec_text: exactText,
      status: "DRAFT",
      review_note: "",
      fraud_risk_score: null,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });
    mockSubmitTender.mockResolvedValueOnce({
      message: "Submitted",
      status: "SUBMITTED",
    });

    fillValidForm({
      spec_text: exactText,
      submission_deadline: futureDatetime(),
    });
    clickSubmit();

    await waitFor(() => {
      expect(
        screen.queryByText(/specification text must not exceed/i)
      ).not.toBeInTheDocument();
    });
  });

  it("does not show a spec text error when spec text is empty", async () => {
    mockCreateTender.mockResolvedValueOnce({
      id: 1,
      agency: "agency-1",
      submitted_by: null,
      tender_ref: "NHAI/2024/001",
      title: "Test",
      category: "Infrastructure",
      estimated_value: "50000000",
      submission_deadline: futureDatetime(),
      publication_date: null,
      buyer_name: "Ministry",
      spec_text: "",
      status: "DRAFT",
      review_note: "",
      fraud_risk_score: null,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });
    mockSubmitTender.mockResolvedValueOnce({
      message: "Submitted",
      status: "SUBMITTED",
    });

    fillValidForm({ spec_text: "", submission_deadline: futureDatetime() });
    clickSubmit();

    await waitFor(() => {
      expect(
        screen.queryByText(/specification text must not exceed/i)
      ).not.toBeInTheDocument();
    });
  });

  it("displays a character counter showing current length vs max", () => {
    // The counter shows "0 / <max> characters" — match locale-agnostic
    const counters = screen.getAllByText((content) =>
      /^0\s*\//.test(content) && /characters/.test(content)
    );
    expect(counters.length).toBeGreaterThan(0);
  });

  it("updates the character counter as the user types in spec text", async () => {
    const textarea = screen.getByLabelText(/specification text/i);
    fireEvent.change(textarea, { target: { value: "Hello" } });

    await waitFor(() => {
      // Match "5 / <any number> characters" locale-agnostically
      const counter = screen.getByText((content) =>
        /^5\s*\//.test(content) && /characters/.test(content)
      );
      expect(counter).toBeInTheDocument();
    });
  });
});

describe("TenderSubmissionForm — combined validation", () => {
  beforeEach(() => {
    mockCreateTender.mockReset();
    mockSubmitTender.mockReset();
    render(<NewTenderPage />);
  });

  it("shows both past deadline and spec text errors simultaneously", async () => {
    const oversizedText = "a".repeat(SPEC_TEXT_MAX + 1);
    fillValidForm({
      submission_deadline: pastDatetime(),
      spec_text: oversizedText,
    });
    clickSubmit();

    await waitFor(() => {
      expect(
        screen.getByText(/submission deadline must be in the future/i)
      ).toBeInTheDocument();
      expect(
        screen.getByText(/specification text must not exceed/i)
      ).toBeInTheDocument();
    });
  });
});
