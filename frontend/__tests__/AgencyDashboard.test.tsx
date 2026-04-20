/**
 * Unit tests for AgencyDashboard filter and sort logic.
 * Validates:
 *   Requirement 5.6 — filter by status, category, date range
 *   Requirement 5.7 — sort by submission date, estimated value, fraud risk score
 */
import React from "react";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";

// ── Module mocks ──────────────────────────────────────────────────────────────

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: jest.fn() }),
}));

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({
    children,
    href,
  }: {
    children: React.ReactNode;
    href: string;
  }) => <a href={href}>{children}</a>,
}));

jest.mock("@/contexts/AuthContext", () => ({
  useAuth: jest.fn(),
}));

jest.mock("@/services/agencies", () => ({
  getTenders: jest.fn(),
}));

jest.mock("@/lib/api", () => ({
  __esModule: true,
  default: {
    get: jest.fn().mockResolvedValue({ data: { results: [], count: 0 } }),
    post: jest.fn().mockResolvedValue({}),
  },
}));

jest.mock("@/components/AgencyLayout", () => ({
  __esModule: true,
  default: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
}));

// framer-motion: render children without animation
jest.mock("framer-motion", () => ({
  motion: {
    div: ({
      children,
      ...props
    }: React.HTMLAttributes<HTMLDivElement> & { children?: React.ReactNode }) => (
      <div {...props}>{children}</div>
    ),
  },
}));

import AgencyDashboardPage from "@/app/agency/dashboard/page";
import { useAuth } from "@/contexts/AuthContext";
import { getTenders } from "@/services/agencies";
import type { TenderFilters } from "@/services/agencies";

const mockUseAuth = useAuth as jest.MockedFunction<typeof useAuth>;
const mockGetTenders = getTenders as jest.MockedFunction<typeof getTenders>;

// ── Shared setup ──────────────────────────────────────────────────────────────

const emptyPaginatedResponse = {
  results: [],
  count: 0,
  next: null,
  previous: null,
};

function setupAuth(role = "AGENCY_ADMIN") {
  mockUseAuth.mockReturnValue({
    role: role as ReturnType<typeof useAuth>["role"],
    agencyId: "agency-1",
    accessToken: "token",
    isAuthenticated: true,
    isLoading: false,
    login: jest.fn(),
    logout: jest.fn(),
  });
}

/**
 * The dashboard labels don't use htmlFor, so we can't use getByLabelText.
 * Instead we find the filter container and query selects/inputs by their
 * option text or placeholder.
 */
function getStatusSelect(): HTMLSelectElement {
  // The status select has "All statuses" as first option
  const selects = screen.getAllByRole("combobox") as HTMLSelectElement[];
  return selects.find((s) =>
    Array.from(s.options).some((o) => o.text === "All statuses")
  )!;
}

function getCategorySelect(): HTMLSelectElement {
  const selects = screen.getAllByRole("combobox") as HTMLSelectElement[];
  return selects.find((s) =>
    Array.from(s.options).some((o) => o.text === "All categories")
  )!;
}

function getSortSelect(): HTMLSelectElement {
  const selects = screen.getAllByRole("combobox") as HTMLSelectElement[];
  return selects.find((s) =>
    Array.from(s.options).some((o) => o.value === "-created_at")
  )!;
}

function getDateInputs(): HTMLInputElement[] {
  return screen
    .getAllByRole("textbox", { hidden: true })
    .filter((el) => (el as HTMLInputElement).type === "date") as HTMLInputElement[];
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("AgencyDashboard — filter controls (Requirement 5.6)", () => {
  beforeEach(() => {
    setupAuth();
    mockGetTenders.mockResolvedValue(emptyPaginatedResponse);
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  it("renders the status filter dropdown", async () => {
    render(<AgencyDashboardPage />);
    await waitFor(() => {
      expect(getStatusSelect()).toBeInTheDocument();
    });
  });

  it("renders the category filter dropdown", async () => {
    render(<AgencyDashboardPage />);
    await waitFor(() => {
      expect(getCategorySelect()).toBeInTheDocument();
    });
  });

  it("renders the date range inputs (from and to)", async () => {
    render(<AgencyDashboardPage />);
    await waitFor(() => {
      // Find date inputs by querying all inputs of type date
      const container = document.body;
      const dateInputs = container.querySelectorAll('input[type="date"]');
      expect(dateInputs.length).toBeGreaterThanOrEqual(2);
    });
  });

  it("calls getTenders with status filter when status is changed", async () => {
    render(<AgencyDashboardPage />);
    await waitFor(() => {
      expect(getStatusSelect()).toBeInTheDocument();
    });

    mockGetTenders.mockClear();
    mockGetTenders.mockResolvedValue(emptyPaginatedResponse);

    fireEvent.change(getStatusSelect(), { target: { value: "FLAGGED" } });

    await waitFor(() => {
      const calls = mockGetTenders.mock.calls;
      const lastCall = calls[calls.length - 1][0] as TenderFilters;
      expect(lastCall.status).toBe("FLAGGED");
    });
  });

  it("calls getTenders with category filter when category is changed", async () => {
    render(<AgencyDashboardPage />);
    await waitFor(() => {
      expect(getCategorySelect()).toBeInTheDocument();
    });

    mockGetTenders.mockClear();
    mockGetTenders.mockResolvedValue(emptyPaginatedResponse);

    fireEvent.change(getCategorySelect(), { target: { value: "IT" } });

    await waitFor(() => {
      const calls = mockGetTenders.mock.calls;
      const lastCall = calls[calls.length - 1][0] as TenderFilters;
      expect(lastCall.category).toBe("IT");
    });
  });

  it("calls getTenders with date_from filter when from-date is changed", async () => {
    render(<AgencyDashboardPage />);
    await waitFor(() => {
      const dateInputs = document.body.querySelectorAll('input[type="date"]');
      expect(dateInputs.length).toBeGreaterThanOrEqual(1);
    });

    mockGetTenders.mockClear();
    mockGetTenders.mockResolvedValue(emptyPaginatedResponse);

    const dateInputs = document.body.querySelectorAll('input[type="date"]');
    fireEvent.change(dateInputs[0], { target: { value: "2024-01-01" } });

    await waitFor(() => {
      const calls = mockGetTenders.mock.calls;
      const lastCall = calls[calls.length - 1][0] as TenderFilters;
      expect(lastCall.date_from).toBe("2024-01-01");
    });
  });

  it("calls getTenders with date_to filter when to-date is changed", async () => {
    render(<AgencyDashboardPage />);
    await waitFor(() => {
      const dateInputs = document.body.querySelectorAll('input[type="date"]');
      expect(dateInputs.length).toBeGreaterThanOrEqual(2);
    });

    mockGetTenders.mockClear();
    mockGetTenders.mockResolvedValue(emptyPaginatedResponse);

    const dateInputs = document.body.querySelectorAll('input[type="date"]');
    fireEvent.change(dateInputs[1], { target: { value: "2024-12-31" } });

    await waitFor(() => {
      const calls = mockGetTenders.mock.calls;
      const lastCall = calls[calls.length - 1][0] as TenderFilters;
      expect(lastCall.date_to).toBe("2024-12-31");
    });
  });

  it("shows all status options in the status dropdown", async () => {
    render(<AgencyDashboardPage />);
    await waitFor(() => {
      expect(getStatusSelect()).toBeInTheDocument();
    });

    const select = getStatusSelect();
    const optionValues = Array.from(select.options).map((o) => o.value);

    expect(optionValues).toContain("DRAFT");
    expect(optionValues).toContain("SUBMITTED");
    expect(optionValues).toContain("UNDER_REVIEW");
    expect(optionValues).toContain("FLAGGED");
    expect(optionValues).toContain("CLEARED");
  });

  it("shows a 'Clear Filters' button when a filter is active", async () => {
    render(<AgencyDashboardPage />);
    await waitFor(() => {
      expect(getStatusSelect()).toBeInTheDocument();
    });

    // No clear button initially
    expect(screen.queryByText(/clear filters/i)).not.toBeInTheDocument();

    fireEvent.change(getStatusSelect(), { target: { value: "FLAGGED" } });

    await waitFor(() => {
      expect(screen.getByText(/clear filters/i)).toBeInTheDocument();
    });
  });

  it("resets filters and calls getTenders with empty filters on 'Clear Filters' click", async () => {
    render(<AgencyDashboardPage />);
    await waitFor(() => {
      expect(getStatusSelect()).toBeInTheDocument();
    });

    // Set a filter
    fireEvent.change(getStatusSelect(), { target: { value: "FLAGGED" } });

    await waitFor(() => {
      expect(screen.getByText(/clear filters/i)).toBeInTheDocument();
    });

    mockGetTenders.mockClear();
    mockGetTenders.mockResolvedValue(emptyPaginatedResponse);

    fireEvent.click(screen.getByText(/clear filters/i));

    await waitFor(() => {
      const calls = mockGetTenders.mock.calls;
      const lastCall = calls[calls.length - 1][0] as TenderFilters;
      // status should be cleared (undefined)
      expect(lastCall.status).toBeUndefined();
    });
  });

  it("resets page to 1 when a filter is changed", async () => {
    render(<AgencyDashboardPage />);
    await waitFor(() => {
      expect(getStatusSelect()).toBeInTheDocument();
    });

    mockGetTenders.mockClear();
    mockGetTenders.mockResolvedValue(emptyPaginatedResponse);

    fireEvent.change(getStatusSelect(), { target: { value: "SUBMITTED" } });

    await waitFor(() => {
      const calls = mockGetTenders.mock.calls;
      const lastCall = calls[calls.length - 1][0] as TenderFilters;
      expect(lastCall.page).toBe(1);
    });
  });
});

describe("AgencyDashboard — sort controls (Requirement 5.7)", () => {
  beforeEach(() => {
    setupAuth();
    mockGetTenders.mockResolvedValue(emptyPaginatedResponse);
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  it("renders the sort dropdown", async () => {
    render(<AgencyDashboardPage />);
    await waitFor(() => {
      expect(getSortSelect()).toBeInTheDocument();
    });
  });

  it("defaults to sorting by submission date descending (-created_at)", async () => {
    render(<AgencyDashboardPage />);
    await waitFor(() => {
      expect(getSortSelect()).toBeInTheDocument();
    });

    expect(getSortSelect().value).toBe("-created_at");
  });

  it("shows all sort options in the sort dropdown", async () => {
    render(<AgencyDashboardPage />);
    await waitFor(() => {
      expect(getSortSelect()).toBeInTheDocument();
    });

    const select = getSortSelect();
    const optionValues = Array.from(select.options).map((o) => o.value);

    expect(optionValues).toContain("-created_at");
    expect(optionValues).toContain("created_at");
    expect(optionValues).toContain("-estimated_value");
    expect(optionValues).toContain("estimated_value");
    expect(optionValues).toContain("-fraud_risk_score");
    expect(optionValues).toContain("fraud_risk_score");
  });

  it("calls getTenders with ordering=-created_at by default", async () => {
    render(<AgencyDashboardPage />);

    await waitFor(() => {
      const calls = mockGetTenders.mock.calls;
      expect(calls.length).toBeGreaterThan(0);
      const firstCall = calls[0][0] as TenderFilters;
      expect(firstCall.ordering).toBe("-created_at");
    });
  });

  it("calls getTenders with updated ordering when sort is changed to estimated value descending", async () => {
    render(<AgencyDashboardPage />);
    await waitFor(() => {
      expect(getSortSelect()).toBeInTheDocument();
    });

    mockGetTenders.mockClear();
    mockGetTenders.mockResolvedValue(emptyPaginatedResponse);

    fireEvent.change(getSortSelect(), { target: { value: "-estimated_value" } });

    await waitFor(() => {
      const calls = mockGetTenders.mock.calls;
      const lastCall = calls[calls.length - 1][0] as TenderFilters;
      expect(lastCall.ordering).toBe("-estimated_value");
    });
  });

  it("calls getTenders with updated ordering when sort is changed to fraud risk score descending", async () => {
    render(<AgencyDashboardPage />);
    await waitFor(() => {
      expect(getSortSelect()).toBeInTheDocument();
    });

    mockGetTenders.mockClear();
    mockGetTenders.mockResolvedValue(emptyPaginatedResponse);

    fireEvent.change(getSortSelect(), { target: { value: "-fraud_risk_score" } });

    await waitFor(() => {
      const calls = mockGetTenders.mock.calls;
      const lastCall = calls[calls.length - 1][0] as TenderFilters;
      expect(lastCall.ordering).toBe("-fraud_risk_score");
    });
  });

  it("calls getTenders with updated ordering when sort is changed to submission date ascending", async () => {
    render(<AgencyDashboardPage />);
    await waitFor(() => {
      expect(getSortSelect()).toBeInTheDocument();
    });

    mockGetTenders.mockClear();
    mockGetTenders.mockResolvedValue(emptyPaginatedResponse);

    fireEvent.change(getSortSelect(), { target: { value: "created_at" } });

    await waitFor(() => {
      const calls = mockGetTenders.mock.calls;
      const lastCall = calls[calls.length - 1][0] as TenderFilters;
      expect(lastCall.ordering).toBe("created_at");
    });
  });

  it("resets page to 1 when sort order is changed", async () => {
    render(<AgencyDashboardPage />);
    await waitFor(() => {
      expect(getSortSelect()).toBeInTheDocument();
    });

    mockGetTenders.mockClear();
    mockGetTenders.mockResolvedValue(emptyPaginatedResponse);

    fireEvent.change(getSortSelect(), { target: { value: "estimated_value" } });

    await waitFor(() => {
      const calls = mockGetTenders.mock.calls;
      const lastCall = calls[calls.length - 1][0] as TenderFilters;
      expect(lastCall.page).toBe(1);
    });
  });
});

describe("AgencyDashboard — role-based UI (Requirement 5.8)", () => {
  afterEach(() => {
    jest.clearAllMocks();
  });

  it("shows 'Create Tender' button for AGENCY_ADMIN", async () => {
    setupAuth("AGENCY_ADMIN");
    mockGetTenders.mockResolvedValue(emptyPaginatedResponse);

    render(<AgencyDashboardPage />);
    await waitFor(() => {
      expect(
        screen.getByRole("link", { name: /create tender/i })
      ).toBeInTheDocument();
    });
  });

  it("shows 'Create Tender' button for AGENCY_OFFICER", async () => {
    setupAuth("AGENCY_OFFICER");
    mockGetTenders.mockResolvedValue(emptyPaginatedResponse);

    render(<AgencyDashboardPage />);
    await waitFor(() => {
      expect(
        screen.getByRole("link", { name: /create tender/i })
      ).toBeInTheDocument();
    });
  });

  it("hides 'Create Tender' button for REVIEWER", async () => {
    setupAuth("REVIEWER");
    mockGetTenders.mockResolvedValue(emptyPaginatedResponse);

    render(<AgencyDashboardPage />);
    await waitFor(() => {
      // Wait for the page to finish loading
      expect(screen.queryByText(/loading/i)).not.toBeInTheDocument();
    });

    expect(
      screen.queryByRole("link", { name: /create tender/i })
    ).not.toBeInTheDocument();
  });
});
