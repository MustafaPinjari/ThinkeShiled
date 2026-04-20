"use client";

import React, { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import AgencyLayout from "@/components/AgencyLayout";
import RiskBadge from "@/components/ui/RiskBadge";
import { useAuth } from "@/contexts/AuthContext";
import { getTender, submitTender, type TenderSubmission, type SubmissionStatus } from "@/services/agencies";

// ── Status Badge ──────────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: SubmissionStatus }) {
  const map: Record<SubmissionStatus, string> = {
    DRAFT: "badge-gray",
    SUBMITTED: "badge-blue",
    UNDER_REVIEW: "badge-amber",
    FLAGGED: "badge-red",
    CLEARED: "badge-green",
  };
  return <span className={`badge ${map[status] ?? "badge-gray"}`}>{status.replace("_", " ")}</span>;
}

// ── Detail Row ────────────────────────────────────────────────────────────────

function DetailRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
      <p style={{ fontSize: "0.65rem", fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.06em" }}>
        {label}
      </p>
      <div style={{ fontSize: "0.85rem", color: "var(--text-primary)" }}>{value}</div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function TenderDetailPage() {
  const params = useParams();
  const router = useRouter();
  const { role } = useAuth();
  const tenderId = Number(params.id);

  const [tender, setTender] = useState<TenderSubmission | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitSuccess, setSubmitSuccess] = useState(false);

  const canEdit = role === "AGENCY_ADMIN" || role === "AGENCY_OFFICER";
  const canSubmit = canEdit && tender?.status === "DRAFT";

  useEffect(() => {
    if (!tenderId) return;
    setLoading(true);
    setError(null);
    getTender(tenderId)
      .then(setTender)
      .catch(() => setError("Failed to load tender details."))
      .finally(() => setLoading(false));
  }, [tenderId]);

  async function handleSubmit() {
    if (!tender) return;
    setSubmitting(true);
    setSubmitError(null);
    try {
      await submitTender(tender.id);
      setSubmitSuccess(true);
      // Refresh tender data
      const updated = await getTender(tender.id);
      setTender(updated);
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { detail?: string } } };
      setSubmitError(axiosErr?.response?.data?.detail ?? "Failed to submit tender.");
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) {
    return (
      <AgencyLayout>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "center", minHeight: 300 }}>
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "1rem" }}>
            <div style={{ width: 28, height: 28, borderRadius: "50%", border: "2px solid #3b82f6", borderTopColor: "transparent", animation: "spin 1s linear infinite" }} />
            <p style={{ color: "var(--text-muted)", fontSize: "0.78rem" }}>Loading tender…</p>
          </div>
        </div>
      </AgencyLayout>
    );
  }

  if (error || !tender) {
    return (
      <AgencyLayout>
        <div style={{ maxWidth: 600, margin: "2rem auto", textAlign: "center" }}>
          <p style={{ color: "#f87171", fontSize: "0.85rem", marginBottom: "1rem" }}>
            {error ?? "Tender not found."}
          </p>
          <button onClick={() => router.push("/agency/dashboard")} className="ts-btn ts-btn-ghost">
            Back to Dashboard
          </button>
        </div>
      </AgencyLayout>
    );
  }

  return (
    <AgencyLayout>
      <div style={{ maxWidth: 900, margin: "0 auto" }}>
        {/* Back */}
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

        {/* Header */}
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", flexWrap: "wrap", gap: "1rem", marginBottom: "1.5rem" }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap", marginBottom: "0.5rem" }}>
              <h1 style={{ fontSize: "1.1rem", fontWeight: 700, color: "var(--text-primary)", letterSpacing: "-0.02em" }}>
                {tender.title}
              </h1>
              <StatusBadge status={tender.status} />
            </div>
            <p style={{ fontSize: "0.72rem", color: "var(--text-muted)", fontFamily: "monospace" }}>
              Ref: {tender.tender_ref} · ID: #{tender.id}
            </p>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            {canEdit && tender.status === "DRAFT" && (
              <Link href={`/agency/tenders/${tender.id}/edit`} className="ts-btn ts-btn-ghost" style={{ fontSize: "0.75rem" }}>
                Edit Draft
              </Link>
            )}
            {canSubmit && (
              <button
                onClick={handleSubmit}
                disabled={submitting}
                className="ts-btn ts-btn-primary"
                style={{ fontSize: "0.75rem" }}
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
            )}
          </div>
        </div>

        {/* Submit success */}
        {submitSuccess && (
          <div
            role="status"
            style={{
              borderRadius: 8, border: "1px solid rgba(34,197,94,0.25)",
              background: "rgba(34,197,94,0.1)", padding: "0.625rem 0.875rem",
              fontSize: "0.8rem", color: "#4ade80", marginBottom: "1.25rem",
            }}
          >
            ✓ Tender submitted successfully. Fraud analysis has been queued.
          </div>
        )}

        {/* Submit error */}
        {submitError && (
          <div
            role="alert"
            style={{
              borderRadius: 8, border: "1px solid rgba(239,68,68,0.25)",
              background: "rgba(239,68,68,0.1)", padding: "0.625rem 0.875rem",
              fontSize: "0.8rem", color: "#f87171", marginBottom: "1.25rem",
            }}
          >
            {submitError}
          </div>
        )}

        <div style={{ display: "grid", gridTemplateColumns: "1fr 320px", gap: "1rem", alignItems: "start" }}>
          {/* Main details */}
          <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            {/* Core info */}
            <div style={{ background: "var(--bg-card)", borderRadius: 12, padding: "1.25rem" }}>
              <p style={{
                fontSize: "0.68rem", fontWeight: 600, color: "var(--text-muted)",
                textTransform: "uppercase", letterSpacing: "0.08em",
                marginBottom: "1rem", paddingBottom: "0.5rem",
                borderBottom: "1px solid var(--border)",
              }}>
                Tender Information
              </p>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "1rem" }}>
                <DetailRow label="Category" value={<span className="badge badge-gray">{tender.category}</span>} />
                <DetailRow
                  label="Estimated Value"
                  value={<span style={{ fontVariantNumeric: "tabular-nums" }}>₹{parseFloat(tender.estimated_value).toLocaleString("en-IN")}</span>}
                />
                <DetailRow
                  label="Submission Deadline"
                  value={new Date(tender.submission_deadline).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" })}
                />
                {tender.publication_date && (
                  <DetailRow
                    label="Publication Date"
                    value={new Date(tender.publication_date).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" })}
                  />
                )}
                <DetailRow label="Buyer Department" value={tender.buyer_name} />
                <DetailRow
                  label="Created"
                  value={new Date(tender.created_at).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" })}
                />
              </div>
            </div>

            {/* Specification */}
            {tender.spec_text && (
              <div style={{ background: "var(--bg-card)", borderRadius: 12, padding: "1.25rem" }}>
                <p style={{
                  fontSize: "0.68rem", fontWeight: 600, color: "var(--text-muted)",
                  textTransform: "uppercase", letterSpacing: "0.08em",
                  marginBottom: "1rem", paddingBottom: "0.5rem",
                  borderBottom: "1px solid var(--border)",
                }}>
                  Specification Text
                </p>
                <pre style={{
                  fontSize: "0.78rem", color: "var(--text-secondary)",
                  whiteSpace: "pre-wrap", wordBreak: "break-word",
                  lineHeight: 1.7, fontFamily: "inherit",
                }}>
                  {tender.spec_text}
                </pre>
              </div>
            )}

            {/* Review note */}
            {tender.review_note && (
              <div style={{ background: "var(--bg-card)", borderRadius: 12, padding: "1.25rem" }}>
                <p style={{
                  fontSize: "0.68rem", fontWeight: 600, color: "var(--text-muted)",
                  textTransform: "uppercase", letterSpacing: "0.08em",
                  marginBottom: "0.75rem",
                }}>
                  Review Note
                </p>
                <p style={{ fontSize: "0.82rem", color: "var(--text-secondary)", lineHeight: 1.6 }}>
                  {tender.review_note}
                </p>
              </div>
            )}
          </div>

          {/* Sidebar: Risk & Status */}
          <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            {/* Fraud Risk Score */}
            <div style={{ background: "var(--bg-card)", borderRadius: 12, padding: "1.25rem" }}>
              <p style={{
                fontSize: "0.68rem", fontWeight: 600, color: "var(--text-muted)",
                textTransform: "uppercase", letterSpacing: "0.08em",
                marginBottom: "1rem",
              }}>
                Fraud Risk Assessment
              </p>
              <div style={{ display: "flex", flexDirection: "column", gap: "0.875rem" }}>
                <div>
                  <p style={{ fontSize: "0.68rem", color: "var(--text-muted)", marginBottom: "0.375rem" }}>Risk Score</p>
                  {tender.fraud_risk_score !== null ? (
                    <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                      <span style={{
                        fontSize: "2rem", fontWeight: 700, letterSpacing: "-0.03em",
                        color: tender.fraud_risk_score >= 70 ? "#f87171" : tender.fraud_risk_score >= 40 ? "#fbbf24" : "#4ade80",
                      }}>
                        {tender.fraud_risk_score}
                      </span>
                      <RiskBadge score={tender.fraud_risk_score} showScore={false} />
                    </div>
                  ) : (
                    <div>
                      <span className="badge badge-gray">Pending Analysis</span>
                      {tender.status === "SUBMITTED" && (
                        <p style={{ fontSize: "0.68rem", color: "var(--text-muted)", marginTop: "0.375rem" }}>
                          Analysis in progress…
                        </p>
                      )}
                    </div>
                  )}
                </div>

                <div>
                  <p style={{ fontSize: "0.68rem", color: "var(--text-muted)", marginBottom: "0.375rem" }}>Current Status</p>
                  <StatusBadge status={tender.status} />
                </div>

                {tender.status === "FLAGGED" && (
                  <div style={{
                    borderRadius: 8, border: "1px solid rgba(239,68,68,0.25)",
                    background: "rgba(239,68,68,0.08)", padding: "0.625rem 0.75rem",
                  }}>
                    <p style={{ fontSize: "0.72rem", color: "#f87171", fontWeight: 600, marginBottom: "0.25rem" }}>
                      🚨 Flagged for Review
                    </p>
                    <p style={{ fontSize: "0.68rem", color: "var(--text-muted)" }}>
                      This tender has been flagged due to high fraud risk. A government auditor will review it.
                    </p>
                  </div>
                )}

                {tender.status === "CLEARED" && (
                  <div style={{
                    borderRadius: 8, border: "1px solid rgba(34,197,94,0.25)",
                    background: "rgba(34,197,94,0.08)", padding: "0.625rem 0.75rem",
                  }}>
                    <p style={{ fontSize: "0.72rem", color: "#4ade80", fontWeight: 600 }}>
                      ✓ Cleared
                    </p>
                  </div>
                )}
              </div>
            </div>

            {/* Timeline */}
            <div style={{ background: "var(--bg-card)", borderRadius: 12, padding: "1.25rem" }}>
              <p style={{
                fontSize: "0.68rem", fontWeight: 600, color: "var(--text-muted)",
                textTransform: "uppercase", letterSpacing: "0.08em",
                marginBottom: "1rem",
              }}>
                Timeline
              </p>
              <div style={{ display: "flex", flexDirection: "column", gap: "0.625rem" }}>
                {[
                  { label: "Created", date: tender.created_at, done: true },
                  { label: "Submitted", date: tender.status !== "DRAFT" ? tender.updated_at : null, done: tender.status !== "DRAFT" },
                  { label: "Analysis Complete", date: tender.fraud_risk_score !== null ? tender.updated_at : null, done: tender.fraud_risk_score !== null },
                  { label: "Cleared", date: tender.status === "CLEARED" ? tender.updated_at : null, done: tender.status === "CLEARED" },
                ].map(({ label, date, done }) => (
                  <div key={label} style={{ display: "flex", alignItems: "center", gap: "0.625rem" }}>
                    <div style={{
                      width: 8, height: 8, borderRadius: "50%", flexShrink: 0,
                      background: done ? "#4ade80" : "var(--border-strong)",
                    }} />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <p style={{ fontSize: "0.72rem", color: done ? "var(--text-secondary)" : "var(--text-muted)" }}>{label}</p>
                      {date && (
                        <p style={{ fontSize: "0.65rem", color: "var(--text-muted)" }}>
                          {new Date(date).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" })}
                        </p>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </AgencyLayout>
  );
}
