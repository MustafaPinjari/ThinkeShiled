"use client";

import React, { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import api from "@/lib/api";

type ExportStatus = "idle" | "submitting" | "polling" | "ready" | "error";

interface ExportTaskResponse {
  task_id: string;
  status: "queued" | "processing" | "completed" | "failed";
  download_url?: string;
}

function toDateInputValue(d: Date): string {
  return d.toISOString().slice(0, 10);
}

function defaultRange(): { dateFrom: string; dateTo: string } {
  const now = new Date();
  const past = new Date(now);
  past.setDate(past.getDate() - 30);
  return { dateFrom: toDateInputValue(past), dateTo: toDateInputValue(now) };
}

const POLL_INTERVAL_MS = 3000;
const MAX_POLL_ATTEMPTS = 20;

export default function ExportPanel() {
  const { dateFrom: defaultFrom, dateTo: defaultTo } = defaultRange();
  const [dateFrom, setDateFrom] = useState(defaultFrom);
  const [dateTo, setDateTo] = useState(defaultTo);
  const [status, setStatus] = useState<ExportStatus>("idle");
  const [downloadUrl, setDownloadUrl] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pollAttemptsRef = useRef(0);
  const taskIdRef = useRef<string | null>(null);

  useEffect(() => () => { if (pollTimerRef.current) clearTimeout(pollTimerRef.current); }, []);

  function stopPolling() {
    if (pollTimerRef.current) { clearTimeout(pollTimerRef.current); pollTimerRef.current = null; }
  }

  async function pollStatus() {
    if (!taskIdRef.current) return;
    pollAttemptsRef.current += 1;
    if (pollAttemptsRef.current > MAX_POLL_ATTEMPTS) {
      stopPolling(); setStatus("error"); setErrorMsg("Export timed out. Please try again."); return;
    }
    try {
      const { data } = await api.get<ExportTaskResponse>(`/audit-log/export/${taskIdRef.current}/status/`);
      if (data.status === "completed" && data.download_url) {
        stopPolling(); setDownloadUrl(data.download_url); setStatus("ready");
      } else if (data.status === "failed") {
        stopPolling(); setStatus("error"); setErrorMsg("Export failed on the server.");
      } else {
        pollTimerRef.current = setTimeout(pollStatus, POLL_INTERVAL_MS);
      }
    } catch {
      stopPolling(); setStatus("error"); setErrorMsg("Failed to check export status.");
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!dateFrom || !dateTo) { setErrorMsg("Please select both dates."); return; }
    if (dateFrom > dateTo) { setErrorMsg("Start date must be before end date."); return; }
    setStatus("submitting"); setErrorMsg(null); setDownloadUrl(null);
    stopPolling(); pollAttemptsRef.current = 0; taskIdRef.current = null;
    try {
      const { data } = await api.post<ExportTaskResponse>("/audit-log/export/", { date_from: dateFrom, date_to: dateTo });
      taskIdRef.current = data.task_id;
      setStatus("polling");
      pollTimerRef.current = setTimeout(pollStatus, POLL_INTERVAL_MS);
    } catch { setStatus("error"); setErrorMsg("Failed to start export."); }
  }

  function handleReset() {
    stopPolling(); setStatus("idle"); setDownloadUrl(null); setErrorMsg(null);
    taskIdRef.current = null; pollAttemptsRef.current = 0;
  }

  const isLoading = status === "submitting" || status === "polling";

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="rounded-2xl p-6"
      style={{ background: "var(--bg-card)", border: "1px solid var(--border)" }}
    >
      <div className="flex items-center gap-3 mb-1">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ color: "var(--accent)" }}>
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
          <polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
        </svg>
        <h2 style={{ color: "var(--text-primary)", fontSize: "0.9rem", fontWeight: 600 }}>Export Audit Log</h2>
      </div>
      <p style={{ color: "var(--text-muted)", fontSize: "0.78rem", marginBottom: "1.5rem" }}>
        Generate a PDF report of all audit log entries for a date range. Reports are ready within 30 seconds.
      </p>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label htmlFor="export-date-from" style={{ display: "block", color: "var(--text-muted)", fontSize: "0.68rem", fontWeight: 700, letterSpacing: "0.07em", textTransform: "uppercase", marginBottom: "0.375rem" }}>
              From
            </label>
            <input id="export-date-from" type="date" value={dateFrom} max={dateTo || undefined}
              onChange={(e) => setDateFrom(e.target.value)} disabled={isLoading} required
              className="ts-input" />
          </div>
          <div>
            <label htmlFor="export-date-to" style={{ display: "block", color: "var(--text-muted)", fontSize: "0.68rem", fontWeight: 700, letterSpacing: "0.07em", textTransform: "uppercase", marginBottom: "0.375rem" }}>
              To
            </label>
            <input id="export-date-to" type="date" value={dateTo} min={dateFrom || undefined}
              onChange={(e) => setDateTo(e.target.value)} disabled={isLoading} required
              className="ts-input" />
          </div>
        </div>

        {errorMsg && (
          <div role="alert" style={{ borderRadius: "0.75rem", border: "1px solid rgba(239,68,68,0.25)", background: "rgba(239,68,68,0.1)", padding: "0.625rem 1rem", fontSize: "0.8rem", color: "#fca5a5" }}>
            {errorMsg}
          </div>
        )}

        {status === "polling" && (
          <div role="status" aria-live="polite" style={{ borderRadius: "0.75rem", border: "1px solid rgba(59,130,246,0.25)", background: "rgba(59,130,246,0.08)", padding: "0.625rem 1rem", fontSize: "0.8rem", color: "#93c5fd", display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <div className="w-4 h-4 rounded-full border-2 border-blue-400 border-t-transparent animate-spin flex-shrink-0" />
            Generating PDF report… this may take up to 30 seconds.
          </div>
        )}

        {status === "ready" && downloadUrl && (
          <div style={{ borderRadius: "0.75rem", border: "1px solid rgba(16,185,129,0.25)", background: "rgba(16,185,129,0.08)", padding: "0.625rem 1rem", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <span style={{ fontSize: "0.8rem", color: "#6ee7b7", fontWeight: 500 }}>✓ Report ready</span>
            <div className="flex items-center gap-3">
              <a href={downloadUrl} download
                className="ts-btn ts-btn-primary"
                style={{ fontSize: "0.8rem", padding: "0.375rem 0.875rem", background: "#10b981" }}>
                <svg width="13" height="13" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                  <polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
                </svg>
                Download PDF
              </a>
              <button type="button" onClick={handleReset} style={{ fontSize: "0.78rem", color: "var(--text-muted)", background: "none", border: "none", cursor: "pointer", textDecoration: "underline" }}>
                New export
              </button>
            </div>
          </div>
        )}

        {status !== "ready" && (
          <div className="flex items-center gap-3">
            <button type="submit" disabled={isLoading} className="ts-btn ts-btn-primary">
              {status === "submitting" ? "Starting…" : status === "polling" ? "Generating…" : "Generate PDF"}
            </button>
            {status === "error" && (
              <button type="button" onClick={handleReset} style={{ fontSize: "0.8rem", color: "var(--text-muted)", background: "none", border: "none", cursor: "pointer", textDecoration: "underline" }}>
                Reset
              </button>
            )}
          </div>
        )}
      </form>
    </motion.div>
  );
}
