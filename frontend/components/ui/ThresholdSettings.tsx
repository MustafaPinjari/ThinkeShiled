"use client";

import React, { useCallback, useEffect, useState } from "react";
import { motion } from "framer-motion";
import api from "@/lib/api";

interface AlertSetting {
  id?: number;
  threshold: number;
  category: string;
  email_enabled: boolean;
}

interface CategoryRowProps {
  setting: AlertSetting;
  index: number;
  onChange: (index: number, patch: Partial<AlertSetting>) => void;
  onRemove: (index: number) => void;
}

function CategoryRow({ setting, index, onChange, onRemove }: CategoryRowProps) {
  return (
    <div className="flex items-center gap-3 py-2" style={{ borderBottom: "1px solid var(--border)" }}>
      <input
        type="text"
        placeholder="Category name"
        value={setting.category}
        onChange={(e) => onChange(index, { category: e.target.value })}
        className="ts-input flex-1"
        style={{ fontSize: "0.8rem" }}
        aria-label={`Category name for override ${index + 1}`}
      />
      <input
        type="number"
        min={0} max={100}
        value={setting.threshold}
        onChange={(e) => onChange(index, { threshold: Number(e.target.value) })}
        className="ts-input"
        style={{ width: "5rem", textAlign: "center", fontSize: "0.8rem" }}
        aria-label={`Threshold for category override ${index + 1}`}
      />
      <button
        type="button"
        onClick={() => onRemove(index)}
        style={{ color: "#f87171", background: "none", border: "none", cursor: "pointer", padding: "4px", fontSize: "0.875rem" }}
        aria-label={`Remove category override ${index + 1}`}
      >
        ✕
      </button>
    </div>
  );
}

export default function ThresholdSettings() {
  const [globalThreshold, setGlobalThreshold] = useState(70);
  const [globalEmailEnabled, setGlobalEmailEnabled] = useState(true);
  const [categoryOverrides, setCategoryOverrides] = useState<AlertSetting[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [feedback, setFeedback] = useState<{ type: "success" | "error"; message: string } | null>(null);

  const loadSettings = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get<AlertSetting[]>("/alerts/settings/");
      const global = data.find((s) => s.category === "");
      const overrides = data.filter((s) => s.category !== "");
      if (global) { setGlobalThreshold(global.threshold); setGlobalEmailEnabled(global.email_enabled); }
      setCategoryOverrides(overrides);
    } catch { setFeedback({ type: "error", message: "Failed to load alert settings." }); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { loadSettings(); }, [loadSettings]);

  function handleCategoryChange(index: number, patch: Partial<AlertSetting>) {
    setCategoryOverrides((prev) => prev.map((item, i) => (i === index ? { ...item, ...patch } : item)));
  }

  function handleCategoryRemove(index: number) {
    setCategoryOverrides((prev) => prev.filter((_, i) => i !== index));
  }

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true); setFeedback(null);
    const allSettings: AlertSetting[] = [
      { threshold: globalThreshold, category: "", email_enabled: globalEmailEnabled },
      ...categoryOverrides,
    ];
    try {
      await Promise.all(allSettings.map((s) => api.post("/alerts/settings/", { threshold: s.threshold, category: s.category, email_enabled: s.email_enabled })));
      setFeedback({ type: "success", message: "Settings saved successfully." });
    } catch { setFeedback({ type: "error", message: "Failed to save settings." }); }
    finally { setSaving(false); }
  }

  if (loading) {
    return (
      <div className="rounded-2xl p-6" style={{ background: "var(--bg-card)", border: "1px solid var(--border)" }}>
        <div className="space-y-3">
          <div className="skeleton h-5 w-48" />
          {[...Array(3)].map((_, i) => <div key={i} className="skeleton h-10 rounded-xl" />)}
        </div>
      </div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="rounded-2xl p-6"
      style={{ background: "var(--bg-card)", border: "1px solid var(--border)" }}
    >
      <h2 style={{ color: "var(--text-primary)", fontSize: "0.9rem", fontWeight: 600, marginBottom: "0.25rem" }}>
        Alert Threshold Settings
      </h2>
      <p style={{ color: "var(--text-muted)", fontSize: "0.78rem", marginBottom: "1.5rem" }}>
        Configure when alerts are triggered. Changes apply to all future alerts.
      </p>

      <form onSubmit={handleSave} className="space-y-6">
        {/* Global threshold */}
        <fieldset>
          <legend style={{ color: "var(--text-muted)", fontSize: "0.65rem", fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: "0.75rem" }}>
            Global Settings
          </legend>
          <div className="space-y-4">
            <div className="flex items-center justify-between gap-4">
              <div>
                <label htmlFor="global-threshold" style={{ color: "var(--text-primary)", fontSize: "0.875rem", fontWeight: 500, display: "block" }}>
                  Global threshold
                </label>
                <p style={{ color: "var(--text-muted)", fontSize: "0.72rem", marginTop: "2px" }}>
                  Alert fires when Fraud Risk Score ≥ this value (0–100)
                </p>
              </div>
              <input
                id="global-threshold"
                type="number" min={0} max={100}
                value={globalThreshold}
                onChange={(e) => setGlobalThreshold(Number(e.target.value))}
                className="ts-input"
                style={{ width: "5rem", textAlign: "center" }}
              />
            </div>

            <div className="flex items-center justify-between gap-4">
              <div>
                <label htmlFor="email-toggle" style={{ color: "var(--text-primary)", fontSize: "0.875rem", fontWeight: 500, display: "block" }}>
                  Email notifications
                </label>
                <p style={{ color: "var(--text-muted)", fontSize: "0.72rem", marginTop: "2px" }}>
                  Send email alerts when threshold is crossed
                </p>
              </div>
              <button
                id="email-toggle"
                type="button"
                role="switch"
                aria-checked={globalEmailEnabled}
                onClick={() => setGlobalEmailEnabled((v) => !v)}
                style={{
                  position: "relative", display: "inline-flex", height: "1.5rem", width: "2.75rem",
                  alignItems: "center", borderRadius: "999px", transition: "background 0.2s",
                  background: globalEmailEnabled ? "var(--accent)" : "rgba(255,255,255,0.1)",
                  border: "none", cursor: "pointer", flexShrink: 0,
                }}
              >
                <span style={{
                  display: "inline-block", height: "1rem", width: "1rem", borderRadius: "50%",
                  background: "#fff", boxShadow: "0 1px 3px rgba(0,0,0,0.3)",
                  transform: globalEmailEnabled ? "translateX(1.5rem)" : "translateX(0.25rem)",
                  transition: "transform 0.2s",
                }} />
              </button>
            </div>
          </div>
        </fieldset>

        {/* Per-category overrides */}
        <fieldset>
          <div className="flex items-center justify-between mb-3">
            <legend style={{ color: "var(--text-muted)", fontSize: "0.65rem", fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase" }}>
              Per-Category Overrides
            </legend>
            <button type="button" onClick={() => setCategoryOverrides((prev) => [...prev, { threshold: 70, category: "", email_enabled: true }])}
              style={{ fontSize: "0.75rem", color: "var(--accent)", background: "none", border: "none", cursor: "pointer" }}>
              + Add override
            </button>
          </div>

          {categoryOverrides.length === 0 ? (
            <p style={{ color: "var(--text-muted)", fontSize: "0.8rem", padding: "0.5rem 0" }}>
              No category overrides. Global threshold applies to all categories.
            </p>
          ) : (
            <div className="rounded-xl overflow-hidden" style={{ border: "1px solid var(--border)" }}>
              <div className="flex items-center gap-3 px-3 py-2" style={{ borderBottom: "1px solid var(--border)", background: "rgba(255,255,255,0.02)" }}>
                <span style={{ flex: 1, color: "var(--text-muted)", fontSize: "0.65rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.07em" }}>Category</span>
                <span style={{ width: "5rem", textAlign: "center", color: "var(--text-muted)", fontSize: "0.65rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.07em" }}>Threshold</span>
                <span style={{ width: "1.5rem" }} />
              </div>
              <div className="px-3">
                {categoryOverrides.map((override, idx) => (
                  <CategoryRow key={idx} setting={override} index={idx} onChange={handleCategoryChange} onRemove={handleCategoryRemove} />
                ))}
              </div>
            </div>
          )}
        </fieldset>

        {feedback && (
          <div role="alert" style={{
            borderRadius: "0.75rem", padding: "0.625rem 1rem", fontSize: "0.8rem",
            background: feedback.type === "success" ? "rgba(16,185,129,0.1)" : "rgba(239,68,68,0.1)",
            border: `1px solid ${feedback.type === "success" ? "rgba(16,185,129,0.25)" : "rgba(239,68,68,0.25)"}`,
            color: feedback.type === "success" ? "#6ee7b7" : "#fca5a5",
          }}>
            {feedback.message}
          </div>
        )}

        <div className="flex justify-end">
          <button type="submit" disabled={saving} className="ts-btn ts-btn-primary">
            {saving ? "Saving…" : "Save settings"}
          </button>
        </div>
      </form>
    </motion.div>
  );
}
