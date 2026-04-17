"use client";

import React, { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { format } from "date-fns";
import Link from "next/link";
import Layout from "@/components/Layout";
import ScoreCard from "@/components/ui/ScoreCard";
import SHAPChart from "@/components/charts/SHAPChart";
import RedFlagList from "@/components/ui/RedFlagList";
import BidTable from "@/components/tables/BidTable";
import api from "@/lib/api";
import type { Bid, Explanation, FraudRiskScore, PaginatedResponse, TenderDetail } from "@/types/tender";

const card: React.CSSProperties = {
  background: "var(--bg-card)",
  border: "1px solid var(--border)",
  borderRadius: "1rem",
  padding: "1.25rem",
};

function SkeletonField({ wide }: { wide?: boolean }) {
  return <div className="skeleton h-4" style={{ width: wide ? "12rem" : "8rem" }} />;
}

function MetaRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex flex-col sm:flex-row sm:items-baseline gap-1 sm:gap-3">
      <dt style={{ fontSize: "0.68rem", fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.07em", width: "9rem", flexShrink: 0 }}>
        {label}
      </dt>
      <dd style={{ fontSize: "0.875rem", color: "var(--text-primary)" }}>{value}</dd>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  if (status === "ACTIVE") return <span className="badge badge-green">{status}</span>;
  if (status === "AWARDED") return <span className="badge badge-blue">{status}</span>;
  if (status === "CLOSED") return <span className="badge badge-gray">{status}</span>;
  return <span className="badge badge-amber">{status}</span>;
}

function PlainLanguageExplanation({ explanation }: { explanation: Explanation | null }) {
  if (!explanation) return null;
  const factors = explanation.top_factors ?? [];
  const isFallback = explanation.shap_failed || factors.length === 0;

  return (
    <section aria-labelledby="explanation-heading">
      <h2 id="explanation-heading" style={{ fontSize: "0.95rem", fontWeight: 600, color: "var(--text-primary)", marginBottom: "0.75rem" }}>
        Plain-Language Explanation
      </h2>
      {isFallback && (
        <div style={{ marginBottom: "0.75rem", borderRadius: "0.5rem", border: "1px solid rgba(245,158,11,0.25)", background: "rgba(245,158,11,0.08)", padding: "0.5rem 0.875rem", fontSize: "0.75rem", color: "#fbbf24" }}>
          ML explanation unavailable — showing rule-based factors only.
        </div>
      )}
      {factors.length > 0 ? (
        <ol className="space-y-3">
          {factors.map((f, i) => (
            <li key={i} className="flex items-start gap-3">
              <span style={{ marginTop: "0.125rem", display: "flex", alignItems: "center", justifyContent: "center", width: "1.25rem", height: "1.25rem", borderRadius: "50%", background: "rgba(59,130,246,0.2)", fontSize: "0.7rem", fontWeight: 700, color: "#60a5fa", flexShrink: 0 }}>
                {i + 1}
              </span>
              <p style={{ fontSize: "0.875rem", color: "var(--text-secondary)", lineHeight: 1.6 }}>{f.plain_language}</p>
            </li>
          ))}
        </ol>
      ) : (
        <p style={{ fontSize: "0.875rem", color: "var(--text-muted)" }}>No contributing factors available for this tender.</p>
      )}
      {explanation.model_version && (
        <p style={{ marginTop: "1rem", fontSize: "0.7rem", color: "var(--text-muted)" }}>
          Model: {explanation.model_version} · Rule engine: {explanation.rule_engine_version ?? "—"} · Computed:{" "}
          {explanation.computed_at ? format(new Date(explanation.computed_at), "dd MMM yyyy HH:mm") : "—"}
        </p>
      )}
    </section>
  );
}

export default function TenderDetailPage() {
  const params = useParams<{ id: string }>();
  const tenderId = params.id;

  const [tender, setTender] = useState<TenderDetail | null>(null);
  const [score, setScore] = useState<FraudRiskScore | null>(null);
  const [explanation, setExplanation] = useState<Explanation | null>(null);
  const [bids, setBids] = useState<Bid[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [tenderRes, scoreRes, explanationRes, bidsRes] = await Promise.all([
        api.get<TenderDetail>(`/tenders/${tenderId}/`),
        api.get<FraudRiskScore>(`/tenders/${tenderId}/score/`).catch(() => ({ data: null })),
        api.get<Explanation>(`/tenders/${tenderId}/explanation/`).catch(() => ({ data: null })),
        api.get<PaginatedResponse<Bid>>(`/bids/`, { params: { tender_id: tenderId, page_size: 200 } }).catch(() => ({ data: { results: [] } })),
      ]);
      setTender(tenderRes.data);
      setScore(scoreRes.data);
      setExplanation(explanationRes.data);
      setBids(bidsRes.data.results ?? []);
    } catch {
      setError("Failed to load tender details. Please try again.");
    } finally {
      setLoading(false);
    }
  }, [tenderId]);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  return (
    <Layout>
      <div className="space-y-5 max-w-5xl">
        {/* Back */}
        <Link href="/tenders" style={{ display: "inline-flex", alignItems: "center", gap: "0.25rem", fontSize: "0.8rem", color: "var(--accent)" }} className="hover:underline">
          ← Back to Tenders
        </Link>

        {error && (
          <div style={{ borderRadius: "0.75rem", border: "1px solid rgba(239,68,68,0.25)", background: "rgba(239,68,68,0.1)", padding: "0.75rem 1rem", fontSize: "0.875rem", color: "#fca5a5" }}>
            {error}{" "}
            <button onClick={fetchAll} style={{ textDecoration: "underline", background: "none", border: "none", color: "inherit", cursor: "pointer" }}>Retry</button>
          </div>
        )}

        {/* Header row */}
        <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-4">
          <div className="min-w-0 flex-1">
            {loading ? (
              <div className="space-y-2">
                <div className="skeleton h-6 w-80" />
                <div className="skeleton h-4 w-48" />
              </div>
            ) : (
              <>
                <h1 style={{ fontSize: "1.15rem", fontWeight: 700, color: "var(--text-primary)", letterSpacing: "-0.01em", lineHeight: 1.4 }}>
                  {tender?.title ?? "—"}
                </h1>
                <p style={{ marginTop: "0.25rem", fontFamily: "monospace", fontSize: "0.75rem", color: "var(--text-muted)" }}>
                  {tender?.tender_id}
                </p>
              </>
            )}
          </div>
          <div className="shrink-0">
            <ScoreCard score={score?.score ?? null} loading={loading} />
          </div>
        </div>

        {/* Tender metadata */}
        <div style={card}>
          <h2 style={{ fontSize: "0.875rem", fontWeight: 600, color: "var(--text-primary)", marginBottom: "1rem" }}>Tender Details</h2>
          {loading ? (
            <div className="space-y-3">{[...Array(6)].map((_, i) => <SkeletonField key={i} wide={i % 2 === 0} />)}</div>
          ) : (
            <dl className="space-y-3">
              <MetaRow label="Category" value={tender?.category ?? "—"} />
              <MetaRow label="Buyer" value={tender?.buyer_name ?? "—"} />
              <MetaRow label="Buyer ID" value={<span style={{ fontFamily: "monospace", fontSize: "0.8rem" }}>{tender?.buyer_id ?? "—"}</span>} />
              <MetaRow label="Estimated Value" value={tender ? `${tender.currency} ${Number(tender.estimated_value).toLocaleString("en-IN")}` : "—"} />
              <MetaRow label="Deadline" value={tender?.submission_deadline ? format(new Date(tender.submission_deadline), "dd MMM yyyy HH:mm") : "—"} />
              <MetaRow label="Status" value={tender ? <StatusBadge status={tender.status} /> : "—"} />
              <MetaRow label="Ingested" value={tender?.created_at ? format(new Date(tender.created_at), "dd MMM yyyy") : "—"} />
            </dl>
          )}
        </div>

        {/* SHAP + explanation */}
        <div style={card}>
          {loading ? (
            <div className="space-y-3">
              <div className="skeleton h-5 w-48" />
              <div className="skeleton h-40 w-full" />
            </div>
          ) : (
            <div className="space-y-6">
              <SHAPChart explanation={explanation} />
              <div style={{ borderTop: "1px solid var(--border)", paddingTop: "1.25rem" }}>
                <PlainLanguageExplanation explanation={explanation} />
              </div>
            </div>
          )}
        </div>

        {/* Red flags */}
        <div style={card}>
          {loading ? (
            <div className="space-y-2">
              <div className="skeleton h-5 w-32" />
              {[...Array(3)].map((_, i) => <div key={i} className="skeleton h-16 rounded-xl" />)}
            </div>
          ) : (
            <RedFlagList redFlags={explanation?.red_flags ?? []} loading={false} />
          )}
        </div>

        {/* Bids */}
        <div style={card}>
          {loading ? (
            <div className="space-y-2">
              <div className="skeleton h-5 w-24" />
              <div className="skeleton h-40 w-full" />
            </div>
          ) : (
            <BidTable bids={bids} estimatedValue={tender ? Number(tender.estimated_value) : null} />
          )}
        </div>
      </div>
    </Layout>
  );
}
