"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import React, { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useAuth } from "@/contexts/AuthContext";

const NAV_ITEMS = [
  {
    href: "/dashboard", label: "Dashboard",
    icon: <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/></svg>,
  },
  {
    href: "/tenders", label: "Tenders",
    icon: <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>,
  },
  {
    href: "/companies", label: "Companies",
    icon: <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>,
  },
  {
    href: "/graph", label: "Collusion Graph",
    icon: <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/></svg>,
    badge: "Live",
  },
  {
    href: "/alerts", label: "Alerts",
    icon: <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>,
  },
  {
    href: "/audit", label: "Audit Log", adminOnly: true,
    icon: <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>,
  },
];

export default function Layout({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading, role, logout } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    if (!isLoading && !isAuthenticated) router.replace("/login");
  }, [isAuthenticated, isLoading, router]);

  useEffect(() => { setMobileOpen(false); }, [pathname]);

  if (isLoading) {
    return (
      <div style={{ display: "flex", minHeight: "100vh", alignItems: "center", justifyContent: "center", background: "var(--bg-base)" }}>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "1rem" }}>
          <div style={{ width: 32, height: 32, borderRadius: "50%", border: "2px solid #3b82f6", borderTopColor: "transparent", animation: "spin 1s linear infinite" }} />
          <p style={{ color: "var(--text-muted)", fontSize: "0.78rem" }}>Loading…</p>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) return null;

  const visibleItems = NAV_ITEMS.filter(i => !i.adminOnly || role === "ADMIN");

  return (
    <div style={{ display: "flex", minHeight: "100vh", background: "var(--bg-base)" }}>

      {/* Mobile overlay */}
      <AnimatePresence>
        {mobileOpen && (
          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            onClick={() => setMobileOpen(false)}
            style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", zIndex: 30, backdropFilter: "blur(4px)" }}
          />
        )}
      </AnimatePresence>

      {/* ── Sidebar ── */}
      <motion.aside
        initial={false}
        style={{
          position: "fixed", top: 0, left: 0, height: "100%", width: 200,
          background: "var(--bg-surface)", zIndex: 40,
          display: "flex", flexDirection: "column",
          borderRight: "1px solid var(--border)",
        }}
        animate={{ x: mobileOpen ? 0 : (typeof window !== "undefined" && window.innerWidth < 1024 ? -200 : 0) }}
        transition={{ type: "tween", duration: 0.25 }}
      >
        {/* User profile */}
        <div style={{ padding: "1.25rem 1rem 1rem", borderBottom: "1px solid var(--border)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.625rem" }}>
            <div style={{
              width: 36, height: 36, borderRadius: "50%", flexShrink: 0,
              background: "linear-gradient(135deg, #3b82f6, #8b5cf6)",
              display: "flex", alignItems: "center", justifyContent: "center",
              fontSize: "0.8rem", fontWeight: 700, color: "#fff",
            }}>
              {role === "ADMIN" ? "A" : "U"}
            </div>
            <div style={{ minWidth: 0 }}>
              <p style={{ fontSize: "0.82rem", fontWeight: 600, color: "var(--text-primary)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {role === "ADMIN" ? "Administrator" : "Auditor"}
              </p>
              <p style={{ fontSize: "0.68rem", color: "var(--text-muted)" }}>{role}</p>
            </div>
          </div>
        </div>

        {/* Nav */}
        <nav style={{ flex: 1, padding: "0.75rem 0.625rem", overflowY: "auto" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
            {visibleItems.map((item) => {
              const isActive = pathname === item.href || pathname.startsWith(item.href + "/");
              return (
                <Link key={item.href} href={item.href}
                  className={`nav-item${isActive ? " active" : ""}`}
                >
                  <span style={{ opacity: isActive ? 1 : 0.6, flexShrink: 0 }}>{item.icon}</span>
                  <span style={{ flex: 1 }}>{item.label}</span>
                  {item.badge && (
                    <span style={{ fontSize: "0.6rem", fontWeight: 700, padding: "1px 5px", borderRadius: 4, background: "rgba(59,130,246,0.2)", color: "#60a5fa" }}>
                      {item.badge}
                    </span>
                  )}
                </Link>
              );
            })}
          </div>
        </nav>

        {/* Bottom */}
        <div style={{ padding: "0.75rem 0.625rem", borderTop: "1px solid var(--border)", display: "flex", flexDirection: "column", gap: "2px" }}>
          <button
            onClick={logout}
            className="nav-item"
            style={{ width: "100%", background: "none", border: "none", textAlign: "left" }}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" style={{ opacity: 0.6, flexShrink: 0 }}>
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
              <polyline points="16 17 21 12 16 7"/>
              <line x1="21" y1="12" x2="9" y2="12"/>
            </svg>
            <span>Log out</span>
          </button>
        </div>
      </motion.aside>

      {/* ── Main ── */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", marginLeft: 200, minWidth: 0 }}>

        {/* Topbar */}
        <header style={{
          position: "sticky", top: 0, zIndex: 20,
          display: "flex", alignItems: "center", justifyContent: "space-between",
          padding: "0.75rem 1.5rem",
          background: "rgba(13,13,13,0.9)",
          backdropFilter: "blur(12px)",
          borderBottom: "1px solid var(--border)",
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
            {/* Mobile toggle */}
            <button onClick={() => setMobileOpen(!mobileOpen)}
              style={{ display: "none", background: "none", border: "none", cursor: "pointer", color: "var(--text-secondary)", padding: 4 }}
              className="mobile-menu-btn">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/>
              </svg>
            </button>

            {/* Breadcrumb */}
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
              <span style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>TenderShield</span>
              <span style={{ color: "var(--text-muted)", fontSize: "0.72rem" }}>/</span>
              <span style={{ fontSize: "0.72rem", color: "var(--text-secondary)", fontWeight: 500 }}>
                {NAV_ITEMS.find(n => pathname.startsWith(n.href))?.label ?? "Dashboard"}
              </span>
            </div>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
            {/* Online indicator */}
            <div style={{ display: "flex", alignItems: "center", gap: "0.375rem", padding: "0.25rem 0.625rem", borderRadius: 6, background: "rgba(34,197,94,0.1)" }}>
              <div className="pulse-dot" style={{ width: 6, height: 6, borderRadius: "50%", background: "#22c55e" }} />
              <span style={{ fontSize: "0.68rem", color: "#4ade80", fontWeight: 500 }}>Online</span>
            </div>
            {/* Advisory badge */}
            <div style={{ padding: "0.25rem 0.625rem", borderRadius: 6, background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.2)" }}>
              <span style={{ fontSize: "0.65rem", color: "#f87171", fontWeight: 600, letterSpacing: "0.04em" }}>ADVISORY ONLY</span>
            </div>
          </div>
        </header>

        {/* Page content */}
        <main style={{ flex: 1, padding: "1.5rem", overflowY: "auto" }}>
          <motion.div
            key={pathname}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.2, ease: "easeOut" }}
          >
            {children}
          </motion.div>
        </main>
      </div>
    </div>
  );
}
