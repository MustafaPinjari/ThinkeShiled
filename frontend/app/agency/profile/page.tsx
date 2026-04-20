"use client";

import React, { useCallback, useEffect, useState } from "react";
import AgencyLayout from "@/components/AgencyLayout";
import { useAuth } from "@/contexts/AuthContext";
import {
  getAgencyProfile,
  updateAgencyProfile,
  getMembers,
  deactivateMember,
  sendInvitation,
  type AgencyProfile,
  type AgencyMember,
  type InvitableRole,
} from "@/services/agencies";

// ── Tooltip ───────────────────────────────────────────────────────────────────

function Tooltip({ text, children }: { text: string; children: React.ReactNode }) {
  const [visible, setVisible] = useState(false);
  return (
    <span
      style={{ position: "relative", display: "inline-flex", alignItems: "center" }}
      onMouseEnter={() => setVisible(true)}
      onMouseLeave={() => setVisible(false)}
      onFocus={() => setVisible(true)}
      onBlur={() => setVisible(false)}
    >
      {children}
      {visible && (
        <span
          role="tooltip"
          style={{
            position: "absolute", bottom: "calc(100% + 6px)", left: "50%",
            transform: "translateX(-50%)",
            background: "var(--bg-elevated)", border: "1px solid var(--border-strong)",
            borderRadius: 6, padding: "0.375rem 0.625rem",
            fontSize: "0.68rem", color: "var(--text-secondary)",
            whiteSpace: "nowrap", zIndex: 50,
            boxShadow: "0 4px 16px rgba(0,0,0,0.4)",
            pointerEvents: "none",
          }}
        >
          {text}
        </span>
      )}
    </span>
  );
}

// ── InviteMemberModal ─────────────────────────────────────────────────────────

interface InviteMemberModalProps {
  onClose: () => void;
  onSuccess: () => void;
}

function InviteMemberModal({ onClose, onSuccess }: InviteMemberModalProps) {
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<InvitableRole>("AGENCY_OFFICER");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [emailError, setEmailError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setEmailError(null);

    if (!email.trim()) {
      setEmailError("Email address is required.");
      return;
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) {
      setEmailError("Enter a valid email address.");
      return;
    }

    setSubmitting(true);
    try {
      await sendInvitation(email.trim().toLowerCase(), role);
      onSuccess();
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { detail?: string; email?: string | string[] } } };
      const data = axiosErr?.response?.data;
      if (data?.email) {
        setEmailError(Array.isArray(data.email) ? data.email.join(" ") : String(data.email));
      } else if (data?.detail) {
        setError(String(data.detail));
      } else {
        setError("Failed to send invitation. Please try again.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      style={{
        position: "fixed", inset: 0, zIndex: 60,
        display: "flex", alignItems: "center", justifyContent: "center",
        background: "rgba(0,0,0,0.7)", backdropFilter: "blur(4px)",
      }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div
        style={{
          background: "var(--bg-card)", borderRadius: 16,
          padding: "1.5rem", width: "100%", maxWidth: 420,
          boxShadow: "0 24px 64px rgba(0,0,0,0.6)",
          border: "1px solid var(--border-strong)",
        }}
        role="dialog"
        aria-modal="true"
        aria-labelledby="invite-modal-title"
      >
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1.25rem" }}>
          <h2 id="invite-modal-title" style={{ fontSize: "1rem", fontWeight: 700, color: "var(--text-primary)" }}>
            Invite Team Member
          </h2>
          <button
            onClick={onClose}
            style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-muted)", padding: 4 }}
            aria-label="Close modal"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        </div>

        {error && (
          <div role="alert" style={{ borderRadius: 8, border: "1px solid rgba(239,68,68,0.25)", background: "rgba(239,68,68,0.1)", padding: "0.5rem 0.75rem", fontSize: "0.78rem", color: "#f87171", marginBottom: "1rem" }}>
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
          <div>
            <label htmlFor="invite-email" style={{ display: "block", fontSize: "0.68rem", fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: "0.375rem" }}>
              Email Address *
            </label>
            <input
              id="invite-email"
              type="email"
              value={email}
              onChange={(e) => { setEmail(e.target.value); setEmailError(null); }}
              placeholder="colleague@agency.gov.in"
              disabled={submitting}
              aria-invalid={!!emailError}
              className="ts-input"
              style={{ borderColor: emailError ? "rgba(239,68,68,0.5)" : undefined }}
            />
            {emailError && (
              <p role="alert" style={{ fontSize: "0.72rem", color: "#f87171", marginTop: "0.3rem" }}>{emailError}</p>
            )}
          </div>

          <div>
            <label htmlFor="invite-role" style={{ display: "block", fontSize: "0.68rem", fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: "0.375rem" }}>
              Role *
            </label>
            <select
              id="invite-role"
              value={role}
              onChange={(e) => setRole(e.target.value as InvitableRole)}
              disabled={submitting}
              className="ts-input"
            >
              <option value="AGENCY_OFFICER">Agency Officer — can create and submit tenders</option>
              <option value="REVIEWER">Reviewer — can view tenders and fraud scores</option>
            </select>
          </div>

          <div style={{ display: "flex", gap: "0.75rem", justifyContent: "flex-end", marginTop: "0.25rem" }}>
            <button type="button" onClick={onClose} className="ts-btn ts-btn-ghost" disabled={submitting}>
              Cancel
            </button>
            <button type="submit" className="ts-btn ts-btn-primary" disabled={submitting}>
              {submitting ? (
                <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <div style={{ width: 12, height: 12, borderRadius: "50%", border: "2px solid rgba(255,255,255,0.3)", borderTopColor: "#fff", animation: "spin 1s linear infinite" }} />
                  Sending…
                </span>
              ) : (
                "Send Invitation"
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function AgencyProfilePage() {
  const { role } = useAuth();
  const isAdmin = role === "AGENCY_ADMIN";

  // Profile state
  const [profile, setProfile] = useState<AgencyProfile | null>(null);
  const [profileLoading, setProfileLoading] = useState(true);
  const [profileError, setProfileError] = useState<string | null>(null);

  // Edit state
  const [editing, setEditing] = useState(false);
  const [editValues, setEditValues] = useState({ contact_name: "", contact_email: "", ministry: "" });
  const [editErrors, setEditErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  // Members state
  const [members, setMembers] = useState<AgencyMember[]>([]);
  const [membersLoading, setMembersLoading] = useState(false);
  const [membersError, setMembersError] = useState<string | null>(null);
  const [deactivatingId, setDeactivatingId] = useState<number | null>(null);

  // Invite modal
  const [showInviteModal, setShowInviteModal] = useState(false);
  const [inviteSuccess, setInviteSuccess] = useState(false);

  // ── Fetch profile ──────────────────────────────────────────────────────────

  const fetchProfile = useCallback(async () => {
    setProfileLoading(true);
    setProfileError(null);
    try {
      const data = await getAgencyProfile();
      setProfile(data);
      setEditValues({
        contact_name: data.contact_name,
        contact_email: data.contact_email,
        ministry: data.ministry,
      });
    } catch {
      setProfileError("Failed to load agency profile.");
    } finally {
      setProfileLoading(false);
    }
  }, []);

  // ── Fetch members ──────────────────────────────────────────────────────────

  const fetchMembers = useCallback(async () => {
    if (!isAdmin) return;
    setMembersLoading(true);
    setMembersError(null);
    try {
      const data = await getMembers();
      setMembers(data);
    } catch {
      setMembersError("Failed to load team members.");
    } finally {
      setMembersLoading(false);
    }
  }, [isAdmin]);

  useEffect(() => {
    fetchProfile();
    fetchMembers();
  }, [fetchProfile, fetchMembers]);

  // ── Save profile ───────────────────────────────────────────────────────────

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    setSaveError(null);
    setSaveSuccess(false);

    const errors: Record<string, string> = {};
    if (!editValues.contact_name.trim()) errors.contact_name = "Contact name is required.";
    if (!editValues.contact_email.trim()) {
      errors.contact_email = "Contact email is required.";
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(editValues.contact_email)) {
      errors.contact_email = "Enter a valid email address.";
    }
    if (!editValues.ministry.trim()) errors.ministry = "Ministry is required.";

    if (Object.keys(errors).length > 0) {
      setEditErrors(errors);
      return;
    }

    setSaving(true);
    try {
      const updated = await updateAgencyProfile({
        contact_name: editValues.contact_name.trim(),
        contact_email: editValues.contact_email.trim().toLowerCase(),
        ministry: editValues.ministry.trim(),
      });
      setProfile(updated);
      setEditing(false);
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 4000);
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: Record<string, string | string[]> } };
      const data = axiosErr?.response?.data;
      if (data) {
        const newErrors: Record<string, string> = {};
        for (const key of ["contact_name", "contact_email", "ministry"]) {
          if (data[key]) {
            newErrors[key] = Array.isArray(data[key]) ? (data[key] as string[]).join(" ") : String(data[key]);
          }
        }
        if (Object.keys(newErrors).length > 0) {
          setEditErrors(newErrors);
        } else if (data.detail) {
          setSaveError(String(data.detail));
        } else {
          setSaveError("Failed to save profile. Please try again.");
        }
      } else {
        setSaveError("Unable to connect. Please try again.");
      }
    } finally {
      setSaving(false);
    }
  }

  // ── Deactivate member ──────────────────────────────────────────────────────

  async function handleDeactivate(memberId: number) {
    if (!confirm("Are you sure you want to deactivate this team member? They will lose access immediately.")) return;
    setDeactivatingId(memberId);
    try {
      await deactivateMember(memberId);
      setMembers(prev => prev.filter(m => m.id !== memberId));
    } catch {
      alert("Failed to deactivate member. Please try again.");
    } finally {
      setDeactivatingId(null);
    }
  }

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <AgencyLayout>
      <div style={{ maxWidth: 900, margin: "0 auto" }}>
        <div style={{ marginBottom: "1.5rem" }}>
          <h1 style={{ fontSize: "1.1rem", fontWeight: 700, color: "var(--text-primary)", letterSpacing: "-0.02em" }}>
            Agency Profile
          </h1>
          <p style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginTop: 2 }}>
            Manage your agency&apos;s profile information and team members
          </p>
        </div>

        {/* Suspension banner */}
        {profile?.status === "SUSPENDED" && (
          <div
            role="alert"
            style={{
              borderRadius: 12, border: "2px solid rgba(239,68,68,0.4)",
              background: "rgba(239,68,68,0.1)", padding: "1rem 1.25rem",
              marginBottom: "1.5rem",
              display: "flex", alignItems: "flex-start", gap: "0.875rem",
            }}
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#f87171" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0, marginTop: 1 }}>
              <circle cx="12" cy="12" r="10"/>
              <line x1="12" y1="8" x2="12" y2="12"/>
              <line x1="12" y1="16" x2="12.01" y2="16"/>
            </svg>
            <div>
              <p style={{ fontSize: "0.9rem", fontWeight: 700, color: "#f87171", marginBottom: "0.375rem" }}>
                Agency Account Suspended
              </p>
              <p style={{ fontSize: "0.8rem", color: "var(--text-secondary)", lineHeight: 1.6 }}>
                Your agency account has been suspended. All tender submissions and team access are currently restricted.
                To resolve this, please contact TenderShield support at{" "}
                <a href="mailto:support@tendershield.in" style={{ color: "#f87171", textDecoration: "underline" }}>
                  support@tendershield.in
                </a>
              </p>
            </div>
          </div>
        )}

        {/* Save success */}
        {saveSuccess && (
          <div
            role="status"
            style={{
              borderRadius: 8, border: "1px solid rgba(34,197,94,0.25)",
              background: "rgba(34,197,94,0.1)", padding: "0.625rem 0.875rem",
              fontSize: "0.8rem", color: "#4ade80", marginBottom: "1.25rem",
            }}
          >
            ✓ Profile updated successfully.
          </div>
        )}

        {/* Invite success */}
        {inviteSuccess && (
          <div
            role="status"
            style={{
              borderRadius: 8, border: "1px solid rgba(34,197,94,0.25)",
              background: "rgba(34,197,94,0.1)", padding: "0.625rem 0.875rem",
              fontSize: "0.8rem", color: "#4ade80", marginBottom: "1.25rem",
            }}
          >
            ✓ Invitation sent successfully.
          </div>
        )}

        <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
          {/* Profile card */}
          <div style={{ background: "var(--bg-card)", borderRadius: 12, padding: "1.25rem" }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1rem", paddingBottom: "0.75rem", borderBottom: "1px solid var(--border)" }}>
              <p style={{ fontSize: "0.68rem", fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.08em" }}>
                Agency Information
              </p>
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                {profile && (
                  <span className={`badge ${profile.status === "ACTIVE" ? "badge-green" : profile.status === "SUSPENDED" ? "badge-red" : "badge-amber"}`}>
                    {profile.status.replace("_", " ")}
                  </span>
                )}
                {isAdmin && !editing && (
                  <button
                    onClick={() => { setEditing(true); setSaveSuccess(false); setEditErrors({}); }}
                    className="ts-btn ts-btn-ghost"
                    style={{ fontSize: "0.72rem", height: "1.75rem" }}
                  >
                    Edit
                  </button>
                )}
              </div>
            </div>

            {profileLoading ? (
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "1rem" }}>
                {[...Array(6)].map((_, i) => (
                  <div key={i}>
                    <div className="skeleton" style={{ height: 10, width: "40%", marginBottom: 6 }} />
                    <div className="skeleton" style={{ height: 16, width: "70%" }} />
                  </div>
                ))}
              </div>
            ) : profileError ? (
              <p style={{ color: "#f87171", fontSize: "0.82rem" }}>{profileError}</p>
            ) : profile ? (
              editing ? (
                <form onSubmit={handleSave} style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
                  {saveError && (
                    <div role="alert" style={{ borderRadius: 8, border: "1px solid rgba(239,68,68,0.25)", background: "rgba(239,68,68,0.1)", padding: "0.5rem 0.75rem", fontSize: "0.78rem", color: "#f87171" }}>
                      {saveError}
                    </div>
                  )}

                  {/* Read-only fields */}
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "1rem" }}>
                    <div>
                      <p style={{ fontSize: "0.65rem", fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: "0.25rem" }}>
                        Legal Name
                      </p>
                      <p style={{ fontSize: "0.85rem", color: "var(--text-secondary)" }}>{profile.legal_name}</p>
                    </div>
                    <div>
                      <div style={{ display: "flex", alignItems: "center", gap: "0.375rem", marginBottom: "0.25rem" }}>
                        <p style={{ fontSize: "0.65rem", fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.06em" }}>
                          GSTIN
                        </p>
                        <Tooltip text="GSTIN cannot be changed after registration">
                          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="var(--text-muted)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ cursor: "help" }}>
                            <circle cx="12" cy="12" r="10"/>
                            <line x1="12" y1="16" x2="12" y2="12"/>
                            <line x1="12" y1="8" x2="12.01" y2="8"/>
                          </svg>
                        </Tooltip>
                      </div>
                      <p style={{ fontSize: "0.85rem", color: "var(--text-secondary)", fontFamily: "monospace" }}>{profile.gstin}</p>
                    </div>
                  </div>

                  {/* Editable fields */}
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "1rem" }}>
                    {[
                      { id: "contact_name", label: "Contact Name", key: "contact_name" as const },
                      { id: "contact_email", label: "Contact Email", key: "contact_email" as const },
                      { id: "ministry", label: "Ministry / Department", key: "ministry" as const },
                    ].map(({ id, label, key }) => (
                      <div key={id}>
                        <label htmlFor={id} style={{ display: "block", fontSize: "0.65rem", fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: "0.375rem" }}>
                          {label} *
                        </label>
                        <input
                          id={id}
                          type={key === "contact_email" ? "email" : "text"}
                          value={editValues[key]}
                          onChange={(e) => { setEditValues(prev => ({ ...prev, [key]: e.target.value })); setEditErrors(prev => ({ ...prev, [key]: "" })); }}
                          disabled={saving}
                          aria-invalid={!!editErrors[key]}
                          className="ts-input"
                          style={{ borderColor: editErrors[key] ? "rgba(239,68,68,0.5)" : undefined }}
                        />
                        {editErrors[key] && (
                          <p role="alert" style={{ fontSize: "0.72rem", color: "#f87171", marginTop: "0.3rem" }}>{editErrors[key]}</p>
                        )}
                      </div>
                    ))}
                  </div>

                  <div style={{ display: "flex", gap: "0.75rem", justifyContent: "flex-end" }}>
                    <button type="button" onClick={() => { setEditing(false); setEditErrors({}); setSaveError(null); }} className="ts-btn ts-btn-ghost" disabled={saving}>
                      Cancel
                    </button>
                    <button type="submit" className="ts-btn ts-btn-primary" disabled={saving}>
                      {saving ? (
                        <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                          <div style={{ width: 12, height: 12, borderRadius: "50%", border: "2px solid rgba(255,255,255,0.3)", borderTopColor: "#fff", animation: "spin 1s linear infinite" }} />
                          Saving…
                        </span>
                      ) : "Save Changes"}
                    </button>
                  </div>
                </form>
              ) : (
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "1rem" }}>
                  {[
                    { label: "Legal Name", value: profile.legal_name },
                    { label: "GSTIN", value: profile.gstin, mono: true, tooltip: "GSTIN cannot be changed after registration" },
                    { label: "Ministry / Department", value: profile.ministry },
                    { label: "Contact Name", value: profile.contact_name },
                    { label: "Contact Email", value: profile.contact_email },
                    { label: "Registered", value: new Date(profile.created_at).toLocaleDateString("en-IN", { dateStyle: "medium" }) },
                  ].map(({ label, value, mono, tooltip }) => (
                    <div key={label}>
                      <div style={{ display: "flex", alignItems: "center", gap: "0.375rem", marginBottom: "0.25rem" }}>
                        <p style={{ fontSize: "0.65rem", fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.06em" }}>
                          {label}
                        </p>
                        {tooltip && (
                          <Tooltip text={tooltip}>
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="var(--text-muted)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ cursor: "help" }}>
                              <circle cx="12" cy="12" r="10"/>
                              <line x1="12" y1="16" x2="12" y2="12"/>
                              <line x1="12" y1="8" x2="12.01" y2="8"/>
                            </svg>
                          </Tooltip>
                        )}
                      </div>
                      <p style={{ fontSize: "0.85rem", color: "var(--text-primary)", fontFamily: mono ? "monospace" : "inherit" }}>
                        {value}
                      </p>
                    </div>
                  ))}
                </div>
              )
            ) : null}
          </div>

          {/* Members table — AGENCY_ADMIN only */}
          {isAdmin && (
            <div style={{ background: "var(--bg-card)", borderRadius: 12, overflow: "hidden", border: "1px solid var(--border)" }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "1rem 1.25rem", borderBottom: "1px solid var(--border)" }}>
                <div>
                  <p style={{ fontSize: "0.68rem", fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.08em" }}>
                    Team Members
                  </p>
                  {!membersLoading && (
                    <p style={{ fontSize: "0.68rem", color: "var(--text-muted)", marginTop: 2 }}>
                      {members.length} member{members.length !== 1 ? "s" : ""}
                    </p>
                  )}
                </div>
                <button
                  onClick={() => { setShowInviteModal(true); setInviteSuccess(false); }}
                  className="ts-btn ts-btn-primary"
                  style={{ fontSize: "0.72rem", height: "2rem" }}
                >
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
                  </svg>
                  Invite Member
                </button>
              </div>

              {membersError ? (
                <div style={{ padding: "1.5rem", textAlign: "center" }}>
                  <p style={{ color: "#f87171", fontSize: "0.82rem" }}>{membersError}</p>
                </div>
              ) : (
                <div style={{ overflowX: "auto" }}>
                  <table className="ts-table">
                    <thead>
                      <tr>
                        <th>Name</th>
                        <th>Email</th>
                        <th>Role</th>
                        <th>Last Login</th>
                        <th>Status</th>
                        <th></th>
                      </tr>
                    </thead>
                    <tbody>
                      {membersLoading ? (
                        [...Array(4)].map((_, i) => (
                          <tr key={i}>
                            {[...Array(6)].map((__, j) => (
                              <td key={j}><div className="skeleton" style={{ height: 14, width: j === 0 ? "70%" : "50%" }} /></td>
                            ))}
                          </tr>
                        ))
                      ) : members.length === 0 ? (
                        <tr>
                          <td colSpan={6} style={{ padding: "2rem 1rem", textAlign: "center", color: "var(--text-muted)", fontSize: "0.82rem" }}>
                            No team members yet. Invite your first member above.
                          </td>
                        </tr>
                      ) : (
                        members.map((member) => (
                          <tr key={member.id}>
                            <td>
                              <div className="ts-member-cell">
                                <div className="ts-avatar" style={{ background: "linear-gradient(135deg, #3b82f6, #8b5cf6)", width: 28, height: 28, fontSize: "0.65rem" }}>
                                  {member.username.charAt(0).toUpperCase()}
                                </div>
                                <span className="ts-member-name" style={{ fontSize: "0.82rem" }}>{member.username}</span>
                              </div>
                            </td>
                            <td style={{ fontSize: "0.78rem" }}>{member.email}</td>
                            <td>
                              <span className="badge badge-blue" style={{ fontSize: "0.62rem" }}>
                                {member.role.replace("_", " ")}
                              </span>
                            </td>
                            <td style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                              {member.last_login
                                ? new Date(member.last_login).toLocaleDateString("en-IN", { dateStyle: "medium" })
                                : "Never"}
                            </td>
                            <td>
                              <span className={`badge ${member.is_active ? "badge-green" : "badge-gray"}`} style={{ fontSize: "0.62rem" }}>
                                {member.is_active ? "Active" : "Inactive"}
                              </span>
                            </td>
                            <td>
                              {member.is_active && (
                                <button
                                  onClick={() => handleDeactivate(member.id)}
                                  disabled={deactivatingId === member.id}
                                  className="ts-action-btn danger"
                                  aria-label={`Deactivate ${member.username}`}
                                  title="Deactivate member"
                                >
                                  {deactivatingId === member.id ? (
                                    <div style={{ width: 10, height: 10, borderRadius: "50%", border: "1.5px solid rgba(255,255,255,0.3)", borderTopColor: "#fff", animation: "spin 1s linear infinite" }} />
                                  ) : (
                                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                      <circle cx="12" cy="12" r="10"/>
                                      <line x1="15" y1="9" x2="9" y2="15"/>
                                      <line x1="9" y1="9" x2="15" y2="15"/>
                                    </svg>
                                  )}
                                </button>
                              )}
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Invite modal */}
      {showInviteModal && (
        <InviteMemberModal
          onClose={() => setShowInviteModal(false)}
          onSuccess={() => {
            setShowInviteModal(false);
            setInviteSuccess(true);
            fetchMembers();
            setTimeout(() => setInviteSuccess(false), 4000);
          }}
        />
      )}
    </AgencyLayout>
  );
}
