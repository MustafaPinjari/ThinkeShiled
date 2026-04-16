You are a senior frontend architect and UI/UX engineer with 10+ years of experience building enterprise dashboards for fintech, cybersecurity, and government intelligence systems.

Your task is to completely RESTYLE and REDESIGN my existing project: "TenderShield – AI-powered Fraud Detection Dashboard".

IMPORTANT:
This project is a DASHBOARD-ONLY system. There is NO landing page.

You MUST preserve:

* All backend logic
* All API contracts
* All data flow
* All features (fraud scoring, SHAP explainability, red flags, graph, alerts, audit logs)

Do NOT modify any backend functionality.

---

### 🎯 OBJECTIVE

Transform the UI into a **modern, high-end, production-grade fraud intelligence dashboard** that looks like software used by government auditors and financial investigators.

---

### ⚠️ STRICT UI LIBRARY RULES (MANDATORY)

You MUST use ALL of the following libraries with strict separation:

1. Magic UI (https://magicui.design/)

* Use for:

  * Micro-interactions
  * Button effects
  * Hover states
  * Loading states
  * Subtle animations (cards, alerts, badges)

2. HeroUI (https://heroui.com/)

* PRIMARY UI SYSTEM:

  * Sidebar
  * Navbar
  * Layout
  * Cards
  * Tables
  * Forms
  * Modals

3. Chakra UI (https://www.chakra-ui.com/docs/charts/installation)

* Use ONLY for:

  * Charts (line, bar, pie, area)
  * Data visualization (fraud trends, risk distribution)

4. Aceternity UI (https://ui.aceternity.com/)

* Use VERY LIMITED inside dashboard:

  * Background effects (subtle grid / glow)
  * Section highlights (NOT full components)
* DO NOT use for layout, tables, or forms

---

### 🎨 DESIGN SYSTEM

Theme:

* Dark mode (default)
* Cyber intelligence + fintech style

Color System:

* Primary: Indigo / Blue
* High Risk: Red
* Medium Risk: Yellow
* Safe: Green

UI Principles:

* Clean and readable
* Data-first design
* Minimal but powerful animations
* Consistent spacing (8px grid)
* Soft rounded corners (lg/xl)
* Subtle glow effects for important elements

---

### 📊 PAGE STRUCTURE (MANDATORY REDESIGN)

1. Dashboard (/dashboard)

* Layout:

  * HeroUI Sidebar + Topbar
* Components:

  * KPI Cards:

    * Total Tenders
    * High Risk Tenders
    * Active Red Flags
    * Collusion Rings
  * Charts (Chakra):

    * Fraud trend (line chart)
    * Risk distribution (pie chart)
  * Tender Table:

    * Sortable
    * Filterable
    * Color-coded fraud score badges
* Enhancements:

  * Magic UI hover animations
  * Smooth transitions

---

2. Tender Detail (/tenders/[id])

* Components:

  * ScoreCard (large fraud score with color band)
  * SHAP Explanation Chart (Chakra bar chart)
  * Red Flag List (highlight severity)
  * Plain-language explanation section
  * Bid Table (structured + readable)

---

3. Company Profile (/companies/[id])

* Components:

  * Metrics Grid (win rate, risk status, deviation)
  * Historical activity timeline
  * Associated red flags

---

4. Collusion Graph (/graph)

* Improve container UI using HeroUI
* Add filter panel (edge types)
* Highlight high-risk nodes visually
* Maintain existing graph logic

---

5. Alerts (/alerts)

* Alert cards:

  * Fraud score
  * Top red flags
  * Timestamp
* Use Magic UI for highlight animations

---

6. Audit Log (/audit)

* Clean table UI
* Date filters
* Export button

---

### 🧱 COMPONENT ARCHITECTURE

/components
/core        → HeroUI-based components
/charts      → Chakra charts
/effects     → Magic UI + Aceternity effects
/features    → domain-specific components

---

### ⚙️ TECHNICAL REQUIREMENTS

* Next.js (App Router)
* TypeScript
* Tailwind CSS
* Fully responsive
* Optimized performance:

  * Lazy load charts
  * Avoid heavy animations
  * Efficient rendering for large tables

---

### 🔥 OUTPUT REQUIRED

1. Full redesigned UI structure
2. Updated layout for all pages
3. Reusable component system
4. Design consistency rules
5. Example code for:

   * Dashboard page
   * Tender detail page

---

### ❌ DO NOT

* Do NOT mix multiple libraries for same component
* Do NOT use Aceternity UI excessively
* Do NOT change backend logic
* Do NOT break existing features

---

### 🧠 CONTEXT

This system is used for:

* Fraud detection
* Audit investigations
* Government decision-making

UI must feel:

* Trustworthy
* Analytical
* Professional
* Clear and explainable

---

FINAL GOAL:
Deliver a world-class fraud detection dashboard UI that looks like enterprise-grade software used by real auditors and intelligence teams.
