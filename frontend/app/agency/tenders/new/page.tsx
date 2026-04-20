"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import AgencyLayout from "@/components/AgencyLayout";
import { createTender, submitTender, type CreateTenderPayload } from "@/services/agencies";

// ── Constants ─────────────────────────────────────────────────────────────────

const GEM_CATEGORIES = [
  "IT", "Infrastructure", "Healthcare", "Education", "Defence",
  "Agriculture", "Energy", "Transport", "Finance", "Other",
];

const SPEC_TEXT_MAX = 100_000;

// ── Form types ────────────────────────────────────────────────────────────────

interface FormValues {
  tender_ref: string;
  title: string;
  category: string;
  estimated_value: string;
  submission_deadline: string;
  publication_date: string;
  buyer_name: string;
  spec_text: string;
}

type FieldErrors = Partial<Record<keyof FormValues, string>>;

const INITIAL_VALUES: FormValues = {
  tender_ref: "",
  title: "",
  category: "",
  estimated_value: "",
  submission_deadline: "",
  publication_date: "",
  buyer_name: "",
  spec_text: "",
};

// ── Validation ────────────────────────────────────────────────────────────────

function validateForm(values: FormValues): FieldErrors {
  const errors: FieldErrors = {};

  if (!values.tender_ref.trim()) errors.tender_ref = "Tender reference number is required.";
  if (!values.title.trim()) errors.title = "Title is required.";
  if (!values.category) errors.category = "Category is required.";

  if (!values.estimated_value.trim()) {
    errors.estimated_value = "Estimated value is required.";
  } else {
    const val = parseFloat(values.estimated_value);
    if (isNaN(val) || val <= 0) {
      errors.estimated_value = "Estimated value must be a positive number.";
    } else if (!/^\d+(\.\d{1,2})?$/.test(values.estimated_value.trim())) {
      errors.estimated_value = "Estimated value must have at most 2 decimal places.";
    }
  }

  if (!values.submission_deadline) {
    errors.submission_deadline = "Submission deadline is required.";
  } else {
    const deadline = new Date(values.submission_deadline);
    if (deadline <= new Date()) {
      errors.submission_deadline = "Submission deadline must be in the future.";
    }
  }

  if (!values.buyer_name.trim()) errors.buyer_name = "Buyer department name is required.";

  if (values.spec_text.length > SPEC_TEXT_MAX) {
    errors.spec_text = `Specification text must not exceed ${SPEC_TEXT_MAX.toLocaleString()} characters.`;
  }

  return errors;
}

// ── Field component ───────────────────────────────────────────────────────────

interface FieldProps {
  id: string;
  label: string;
  type?: string;
  value: string;
  onChange: (v: string) => void;
  error?: string;
  placeholder?: string;
  required?: boolean;
  hint?: string;
  disabled?: boolean;
}

function Field({ id, label, type = "text", value, onChange, error, placeholder, required, hint, disabled }: FieldProps) {
  return (
    <div>
      <label
        htmlFor={id}
        style={{
          display: "block", fontSize: "0.68rem", fontWeight: 600,
          color: "var(--text-muted)", textTransform: "uppercase",
          letterSpacing: "0.06em", marginBottom: "0.375rem",
        }}
      >
        {label}{required && <span style={{ color: "#f87171", marginLeft: 2 }}>*</span>}
      </label>
      <input
        id={id}
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        disabled={disabled}
        aria-invalid={!!error}
        aria-describedby={error ? `${id}-error` : hint ? `${id}-hint` : undefined}
        className="ts-input"
        style={{ borderColor: error ? "rgba(239,68,68,0.5)" : undefined }}
      />
      {hint && !error && (
        <p id={`${id}-hint`} style={{ fontSize: "0.68rem", color: "var(--text-muted)", marginTop: "0.25rem" }}>{hint}</p>
      )}
      {error && (
        <p id={`${id}-error`} role="alert" style={{ fontSize: "0.72rem", color: "#f87171", marginTop: "0.3rem" }}>{error}</p>
      )}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function NewTenderPage() {
  const router = useRouter();
  const [values, setValues] = useState<FormValues>(INITIAL_VALUES);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [serverError, setServerError] = useState<string | null>(null);
  const [savingDraft, setSavingDraft] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  function set(field: keyof FormValues) {
    return (v: string) => {
      setValues(prev => ({ ...prev, [field]: v }));
      if (fieldErrors[field]) {
        setFieldErrors(prev => ({ ...prev, [field]: undefined }));
      }
      setServerError(null);
    };
  }

  function buildPayload(): CreateTenderPayload {
    return {
      tender_ref: values.tender_ref.trim(),
      title: values.title.trim(),
      category: values.category,
      estimated_value: values.estimated_value.trim(),
      submission_deadline: values.submission_deadline,
      publication_date: values.publication_date || undefined,
      buyer_name: values.buyer_name.trim(),
      spec_text: values.spec_text,
    };
  }

  async function handleSaveDraft(e: React.FormEvent) {
    e.preventDefault();
    setServerError(null);

    // Only validate required fields for draft (not deadline future check)
    const draftErrors: FieldErrors = {};
    if (!values.tender_ref.trim()) draftErrors.tender_ref = "Tender reference number is required.";
    if (!values.title.trim()) draftErrors.title = "Title is required.";
    if (!values.category) draftErrors.category = "Category is required.";
    if (!values.buyer_name.trim()) draftErrors.buyer_name = "Buyer department name is required.";
    if (values.spec_text.length > SPEC_TEXT_MAX) {
      draftErrors.spec_text = `Specification text must not exceed ${SPEC_TEXT_MAX.toLocaleString()} characters.`;
    }

    if (Object.keys(draftErrors).length > 0) {
      setFieldErrors(draftErrors);
      return;
    }

    setSavingDraft(true);
    try {
      const tender = await createTender(buildPayload());
      router.push(`/agency/tenders/${tender.id}`);
    } catch (err: unknown) {
      handleServerError(err);
    } finally {
      setSavingDraft(false);
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setServerError(null);

    const errors = validateForm(values);
    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors);
      const firstKey = Object.keys(errors)[0] as keyof FormValues;
      document.getElementById(firstKey)?.focus();
      return;
    }

    setSubmitting(true);
    try {
      const tender = await createTender(buildPayload());
      await submitTender(tender.id);
      router.push(`/agency/tenders/${tender.id}`);
    } catch (err: unknown) {
      handleServerError(err);
    } finally {
      setSubmitting(false);
    }
  }

  function handleServerError(err: unknown) {
    const axiosErr = err as { response?: { data?: Record<string, string | string[]> } };
    const data = axiosErr?.response?.data;
    if (data) {
      const fieldMap: Record<string, keyof FormValues> = {
        tender_ref: "tender_ref",
        title: "title",
        category: "category",
        estimated_value: "estimated_value",
        submission_deadline: "submission_deadline",
        publication_date: "publication_date",
        buyer_name: "buyer_name",
        spec_text: "spec_text",
      };
      const newFieldErrors: FieldErrors = {};
      let hasFieldError = false;
      for (const [key, fk] of Object.entries(fieldMap)) {
        if (data[key]) {
          newFieldErrors[fk] = Array.isArray(data[key]) ? (data[key] as string[]).join(" ") : String(data[key]);
          hasFieldError = true;
        }
      }
      if (hasFieldError) {
        setFieldErrors(newFieldErrors);
      } else if (data.detail) {
        setServerError(String(data.detail));
      } else {
        setServerError("Failed to save tender. Please check your details and try again.");
      }
    } else {
      setServerError("Unable to connect. Please try again.");
    }
  }

  const isLoading = savingDraft || submitting;
  const specCharsLeft = SPEC_TEXT_MAX - values.spec_text.length;

  return (
    <AgencyLayout>
      <div style={{ maxWidth: 800, margin: "0 auto" }}>
        {/* Header */}
        <div style={{ marginBottom: "1.5rem" }}>
          <button
            onClick={() => router.push("/agency/dashboard")}
            style={{
              display: "inline-flex", alignItems: "center", gap: "0.375rem",
              background: "none", border: "none", cursor: "pointer",
              color: "var(--text-muted)", fontSize: "0.78rem", padding: 0,
              marginBottom: "1rem",
            }}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M19 12H5M12 19l-7-7 7-7"/>
            </svg>
            Back to Dashboard
          </button>
          <h1 style={{ fontSize: "1.1rem", fontWeight: 700, color: "var(--text-primary)", letterSpacing: "-0.02em" }}>
            New Tender Submission
          </h1>
          <p style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginTop: 2 }}>
            Fill in the tender details. You can save as draft or submit directly for fraud analysis.
          </p>
        </div>

        {/* Server error */}
        {serverError && (
          <div
            role="alert"
            style={{
              borderRadius: 8, border: "1px solid rgba(239,68,68,0.25)",
              background: "rgba(239,68,68,0.1)", padding: "0.625rem 0.875rem",
              fontSize: "0.8rem", color: "#f87171", marginBottom: "1.25rem",
            }}
          >
            {serverError}
          </div>
        )}

        <form style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
          {/* Section: Tender Details */}
          <div style={{ background: "var(--bg-card)", borderRadius: 12, padding: "1.25rem" }}>
            <p style={{
              fontSize: "0.68rem", fontWeight: 600, color: "var(--text-muted)",
              textTransform: "uppercase", letterSpacing: "0.08em",
              marginBottom: "1rem", paddingBottom: "0.5rem",
              borderBottom: "1px solid var(--border)",
            }}>
              Tender Details
            </p>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: "1rem" }}>
              <Field
                id="tender_ref"
                label="Tender Reference Number"
                value={values.tender_ref}
                onChange={set("tender_ref")}
                error={fieldErrors.tender_ref}
                placeholder="e.g. NHAI/2024/001"
                required
                disabled={isLoading}
              />
              <Field
                id="title"
                label="Title"
                value={values.title}
                onChange={set("title")}
                error={fieldErrors.title}
                placeholder="e.g. Construction of NH-48 Bypass"
                required
                disabled={isLoading}
              />
              <div>
                <label
                  htmlFor="category"
                  style={{
                    display: "block", fontSize: "0.68rem", fontWeight: 600,
                    color: "var(--text-muted)", textTransform: "uppercase",
                    letterSpacing: "0.06em", marginBottom: "0.375rem",
                  }}
                >
                  Category<span style={{ color: "#f87171", marginLeft: 2 }}>*</span>
                </label>
                <select
                  id="category"
                  value={values.category}
                  onChange={(e) => set("category")(e.target.value)}
                  disabled={isLoading}
                  aria-invalid={!!fieldErrors.category}
                  className="ts-input"
                  style={{ borderColor: fieldErrors.category ? "rgba(239,68,68,0.5)" : undefined }}
                >
                  <option value="">Select a category</option>
                  {GEM_CATEGORIES.map(c => (
                    <option key={c} value={c}>{c}</option>
                  ))}
                </select>
                {fieldErrors.category && (
                  <p role="alert" style={{ fontSize: "0.72rem", color: "#f87171", marginTop: "0.3rem" }}>{fieldErrors.category}</p>
                )}
              </div>
              <Field
                id="estimated_value"
                label="Estimated Value (INR)"
                type="number"
                value={values.estimated_value}
                onChange={set("estimated_value")}
                error={fieldErrors.estimated_value}
                placeholder="e.g. 50000000"
                required
                hint="Enter amount in Indian Rupees (INR)"
                disabled={isLoading}
              />
              <Field
                id="submission_deadline"
                label="Submission Deadline"
                type="datetime-local"
                value={values.submission_deadline}
                onChange={set("submission_deadline")}
                error={fieldErrors.submission_deadline}
                required
                disabled={isLoading}
              />
              <Field
                id="publication_date"
                label="Publication Date"
                type="datetime-local"
                value={values.publication_date}
                onChange={set("publication_date")}
                error={fieldErrors.publication_date}
                disabled={isLoading}
              />
            </div>
          </div>

          {/* Section: Buyer Details */}
          <div style={{ background: "var(--bg-card)", borderRadius: 12, padding: "1.25rem" }}>
            <p style={{
              fontSize: "0.68rem", fontWeight: 600, color: "var(--text-muted)",
              textTransform: "uppercase", letterSpacing: "0.08em",
              marginBottom: "1rem", paddingBottom: "0.5rem",
              borderBottom: "1px solid var(--border)",
            }}>
              Buyer Details
            </p>
            <Field
              id="buyer_name"
              label="Buyer Department Name"
              value={values.buyer_name}
              onChange={set("buyer_name")}
              error={fieldErrors.buyer_name}
              placeholder="e.g. Ministry of Road Transport and Highways"
              required
              disabled={isLoading}
            />
          </div>

          {/* Section: Specification */}
          <div style={{ background: "var(--bg-card)", borderRadius: 12, padding: "1.25rem" }}>
            <p style={{
              fontSize: "0.68rem", fontWeight: 600, color: "var(--text-muted)",
              textTransform: "uppercase", letterSpacing: "0.08em",
              marginBottom: "1rem", paddingBottom: "0.5rem",
              borderBottom: "1px solid var(--border)",
            }}>
              Tender Specification
            </p>
            <div>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.375rem" }}>
                <label
                  htmlFor="spec_text"
                  style={{
                    fontSize: "0.68rem", fontWeight: 600, color: "var(--text-muted)",
                    textTransform: "uppercase", letterSpacing: "0.06em",
                  }}
                >
                  Specification Text
                </label>
                <span
                  style={{
                    fontSize: "0.65rem",
                    color: specCharsLeft < 1000 ? "#f87171" : specCharsLeft < 5000 ? "#fbbf24" : "var(--text-muted)",
                  }}
                >
                  {values.spec_text.length.toLocaleString()} / {SPEC_TEXT_MAX.toLocaleString()} characters
                </span>
              </div>
              <textarea
                id="spec_text"
                value={values.spec_text}
                onChange={(e) => set("spec_text")(e.target.value)}
                disabled={isLoading}
                aria-invalid={!!fieldErrors.spec_text}
                placeholder="Enter the full tender specification text…"
                rows={12}
                maxLength={SPEC_TEXT_MAX}
                className="ts-input"
                style={{
                  resize: "vertical",
                  minHeight: 200,
                  borderColor: fieldErrors.spec_text ? "rgba(239,68,68,0.5)" : undefined,
                  fontFamily: "inherit",
                  lineHeight: 1.6,
                }}
              />
              {fieldErrors.spec_text && (
                <p role="alert" style={{ fontSize: "0.72rem", color: "#f87171", marginTop: "0.3rem" }}>{fieldErrors.spec_text}</p>
              )}
            </div>
          </div>

          {/* Actions */}
          <div style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", gap: "0.75rem" }}>
            <button
              type="button"
              onClick={() => router.push("/agency/dashboard")}
              className="ts-btn ts-btn-ghost"
              disabled={isLoading}
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleSaveDraft}
              className="ts-btn ts-btn-ghost"
              disabled={isLoading}
              style={{ borderColor: "var(--border-strong)" }}
            >
              {savingDraft ? (
                <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <div style={{ width: 12, height: 12, borderRadius: "50%", border: "2px solid rgba(255,255,255,0.3)", borderTopColor: "#fff", animation: "spin 1s linear infinite" }} />
                  Saving…
                </span>
              ) : (
                "Save as Draft"
              )}
            </button>
            <button
              type="button"
              onClick={handleSubmit}
              className="ts-btn ts-btn-primary"
              disabled={isLoading}
            >
              {submitting ? (
                <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <div style={{ width: 12, height: 12, borderRadius: "50%", border: "2px solid rgba(255,255,255,0.3)", borderTopColor: "#fff", animation: "spin 1s linear infinite" }} />
                  Submitting…
                </span>
              ) : (
                "Submit for Analysis"
              )}
            </button>
          </div>
        </form>
      </div>
    </AgencyLayout>
  );
}
