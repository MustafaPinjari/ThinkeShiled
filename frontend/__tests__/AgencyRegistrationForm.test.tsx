/**
 * Unit tests for AgencyRegistrationForm (frontend/app/agency/register/page.tsx).
 * Validates:
 *   Requirement 1.5 — duplicate GSTIN server error
 *   Requirement 1.6 — duplicate email server error
 *   Requirement 1.7 — field-level validation errors for missing required fields
 */
import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

// ── Module mocks ──────────────────────────────────────────────────────────────

// Mock next/navigation before importing the page
jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: jest.fn() }),
}));

// Mock the registerAgency service
jest.mock("@/services/agencies", () => ({
  registerAgency: jest.fn(),
}));

import AgencyRegistrationPage from "@/app/agency/register/page";
import { registerAgency } from "@/services/agencies";

const mockRegisterAgency = registerAgency as jest.MockedFunction<
  typeof registerAgency
>;

// ── Helpers ───────────────────────────────────────────────────────────────────

/** Fill in all required fields with valid values. */
async function fillValidForm(overrides: Partial<Record<string, string>> = {}) {
  const fields = {
    legal_name: "National Highways Authority of India",
    gstin: "07AAACN0081N1ZC",
    ministry: "Ministry of Road Transport",
    contact_name: "John Doe",
    contact_email: "john@agency.gov.in",
    password: "SecurePass1",
    ...overrides,
  };

  fireEvent.change(screen.getByLabelText(/legal name/i), {
    target: { value: fields.legal_name },
  });
  fireEvent.change(screen.getByLabelText(/gstin/i), {
    target: { value: fields.gstin },
  });
  fireEvent.change(screen.getByLabelText(/ministry/i), {
    target: { value: fields.ministry },
  });
  fireEvent.change(screen.getByLabelText(/contact name/i), {
    target: { value: fields.contact_name },
  });
  fireEvent.change(screen.getByLabelText(/official email/i), {
    target: { value: fields.contact_email },
  });
  // Use placeholder text to avoid ambiguity with "Show password" button
  fireEvent.change(screen.getByPlaceholderText(/minimum 8 characters/i), {
    target: { value: fields.password },
  });
}

function submitForm() {
  fireEvent.click(screen.getByRole("button", { name: /register agency/i }));
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("AgencyRegistrationForm — field-level validation (Requirement 1.7)", () => {
  beforeEach(() => {
    mockRegisterAgency.mockReset();
    render(<AgencyRegistrationPage />);
  });

  it("shows error for missing legal name", async () => {
    // Leave legal_name empty, fill everything else
    await fillValidForm({ legal_name: "" });
    submitForm();
    await waitFor(() => {
      expect(screen.getByText(/legal name is required/i)).toBeInTheDocument();
    });
  });

  it("shows error for missing GSTIN", async () => {
    await fillValidForm({ gstin: "" });
    submitForm();
    await waitFor(() => {
      expect(screen.getByText(/gstin is required/i)).toBeInTheDocument();
    });
  });

  it("shows error for invalid GSTIN format", async () => {
    await fillValidForm({ gstin: "INVALID" });
    submitForm();
    await waitFor(() => {
      expect(screen.getByText(/invalid gstin format/i)).toBeInTheDocument();
    });
  });

  it("shows error for missing ministry", async () => {
    await fillValidForm({ ministry: "" });
    submitForm();
    await waitFor(() => {
      expect(
        screen.getByText(/ministry \/ department is required/i)
      ).toBeInTheDocument();
    });
  });

  it("shows error for missing contact name", async () => {
    await fillValidForm({ contact_name: "" });
    submitForm();
    await waitFor(() => {
      expect(screen.getByText(/contact name is required/i)).toBeInTheDocument();
    });
  });

  it("shows error for missing official email", async () => {
    await fillValidForm({ contact_email: "" });
    submitForm();
    await waitFor(() => {
      expect(
        screen.getByText(/official email is required/i)
      ).toBeInTheDocument();
    });
  });

  it("shows error for invalid email format", async () => {
    await fillValidForm({ contact_email: "not-an-email" });
    submitForm();
    await waitFor(() => {
      expect(
        screen.getByText(/enter a valid email address/i)
      ).toBeInTheDocument();
    });
  });

  it("shows error for missing password", async () => {
    await fillValidForm({ password: "" });
    submitForm();
    await waitFor(() => {
      expect(screen.getByText(/password is required/i)).toBeInTheDocument();
    });
  });

  it("shows error for password shorter than 8 characters", async () => {
    await fillValidForm({ password: "short" });
    submitForm();
    await waitFor(() => {
      expect(
        screen.getByText(/password must be at least 8 characters/i)
      ).toBeInTheDocument();
    });
  });

  it("shows multiple field errors simultaneously when several fields are empty", async () => {
    // Submit with all fields empty
    submitForm();
    await waitFor(() => {
      expect(screen.getByText(/legal name is required/i)).toBeInTheDocument();
      expect(screen.getByText(/gstin is required/i)).toBeInTheDocument();
      expect(
        screen.getByText(/ministry \/ department is required/i)
      ).toBeInTheDocument();
      expect(screen.getByText(/contact name is required/i)).toBeInTheDocument();
      expect(
        screen.getByText(/official email is required/i)
      ).toBeInTheDocument();
      expect(screen.getByText(/password is required/i)).toBeInTheDocument();
    });
  });

  it("does not call registerAgency when client-side validation fails", async () => {
    submitForm();
    await waitFor(() => {
      expect(screen.getByText(/legal name is required/i)).toBeInTheDocument();
    });
    expect(mockRegisterAgency).not.toHaveBeenCalled();
  });

  it("clears a field error when the user starts typing in that field", async () => {
    // Trigger validation errors
    submitForm();
    await waitFor(() => {
      expect(screen.getByText(/legal name is required/i)).toBeInTheDocument();
    });

    // Start typing in legal_name
    fireEvent.change(screen.getByLabelText(/legal name/i), {
      target: { value: "A" },
    });

    await waitFor(() => {
      expect(
        screen.queryByText(/legal name is required/i)
      ).not.toBeInTheDocument();
    });
  });
});

describe("AgencyRegistrationForm — server error display", () => {
  beforeEach(() => {
    mockRegisterAgency.mockReset();
    render(<AgencyRegistrationPage />);
  });

  it("displays field-level error for duplicate GSTIN (Requirement 1.5)", async () => {
    mockRegisterAgency.mockRejectedValueOnce({
      response: {
        status: 400,
        data: {
          gstin: ["Agency with this GSTIN is already registered."],
        },
      },
    });

    await fillValidForm();
    submitForm();

    await waitFor(() => {
      expect(
        screen.getByText(/agency with this gstin is already registered/i)
      ).toBeInTheDocument();
    });
  });

  it("displays field-level error for duplicate email (Requirement 1.6)", async () => {
    mockRegisterAgency.mockRejectedValueOnce({
      response: {
        status: 400,
        data: {
          contact_email: [
            "This email address is already associated with an account.",
          ],
        },
      },
    });

    await fillValidForm();
    submitForm();

    await waitFor(() => {
      expect(
        screen.getByText(
          /this email address is already associated with an account/i
        )
      ).toBeInTheDocument();
    });
  });

  it("displays server error as a string (non-array) for duplicate GSTIN", async () => {
    mockRegisterAgency.mockRejectedValueOnce({
      response: {
        status: 400,
        data: {
          gstin: "Agency with this GSTIN is already registered.",
        },
      },
    });

    await fillValidForm();
    submitForm();

    await waitFor(() => {
      expect(
        screen.getByText(/agency with this gstin is already registered/i)
      ).toBeInTheDocument();
    });
  });

  it("displays a generic server error banner when detail is returned", async () => {
    mockRegisterAgency.mockRejectedValueOnce({
      response: {
        status: 500,
        data: {
          detail: "Internal server error. Please try again later.",
        },
      },
    });

    await fillValidForm();
    submitForm();

    await waitFor(() => {
      expect(
        screen.getByText(/internal server error/i)
      ).toBeInTheDocument();
    });
  });

  it("displays a fallback error message when no response data is available", async () => {
    mockRegisterAgency.mockRejectedValueOnce(new Error("Network Error"));

    await fillValidForm();
    submitForm();

    await waitFor(() => {
      expect(screen.getByText(/unable to connect/i)).toBeInTheDocument();
    });
  });

  it("clears server error when user modifies a field after a server error", async () => {
    mockRegisterAgency.mockRejectedValueOnce({
      response: {
        status: 400,
        data: {
          gstin: ["Agency with this GSTIN is already registered."],
        },
      },
    });

    await fillValidForm();
    submitForm();

    await waitFor(() => {
      expect(
        screen.getByText(/agency with this gstin is already registered/i)
      ).toBeInTheDocument();
    });

    // Modify the GSTIN field — error should clear
    fireEvent.change(screen.getByLabelText(/gstin/i), {
      target: { value: "07AAACN0081N1ZD" },
    });

    await waitFor(() => {
      expect(
        screen.queryByText(/agency with this gstin is already registered/i)
      ).not.toBeInTheDocument();
    });
  });
});
