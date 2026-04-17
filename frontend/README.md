# TenderShield — Frontend

Next.js 16 (App Router) fraud intelligence dashboard.

## Tech Stack

| Library | Purpose |
|---|---|
| Next.js 16 | App Router, SSR, routing |
| TypeScript | Type safety |
| Tailwind CSS | Utility styling + design tokens |
| HeroUI v3 | UI components (sidebar, layout, cards) |
| framer-motion | Page transitions, card animations, micro-interactions |
| Recharts | Charts (fraud trend line, risk distribution donut) |
| Chakra UI v3 | Chart provider wrapper |
| D3 | SHAP bar chart (custom SVG rendering) |
| vis-network | Collusion graph canvas |
| Axios | API client with JWT refresh interceptor |
| date-fns | Date formatting |

---

## Getting Started

```bash
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000)

Make sure the backend is running at `http://localhost:8000` (set via `NEXT_PUBLIC_API_URL` in `.env`).

---

## Environment Variables

Create a `.env.local` file in this directory (or use the root `.env`):

```env
NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
```

---

## Project Structure

```
frontend/
├── app/
│   ├── layout.tsx              # Root layout — fonts, providers
│   ├── providers.tsx           # Chakra + Auth providers
│   ├── globals.css             # Design tokens, base styles, utilities
│   ├── login/page.tsx          # Login page
│   ├── dashboard/page.tsx      # Main dashboard — KPIs, charts, tender feed
│   ├── tenders/
│   │   ├── page.tsx            # Tender list with filters
│   │   └── [id]/page.tsx       # Tender detail — score, SHAP, red flags, bids
│   ├── companies/
│   │   ├── page.tsx            # Company list
│   │   └── [id]/page.tsx       # Company profile — metrics, timeline, flags
│   ├── graph/page.tsx          # Collusion network graph
│   ├── alerts/page.tsx         # Alert inbox
│   └── audit/page.tsx          # Audit log (Admin only)
│
├── components/
│   ├── Layout.tsx              # Sidebar + topbar shell (all authenticated pages)
│   ├── charts/
│   │   ├── FraudTrendChart.tsx # Recharts line chart — avg score over time
│   │   ├── RiskDistributionChart.tsx # Recharts donut — risk breakdown
│   │   ├── SHAPChart.tsx       # D3 horizontal bar — SHAP feature attribution
│   │   └── GraphCanvas.tsx     # vis-network collusion graph
│   ├── tables/
│   │   ├── TenderTable.tsx     # Sortable/paginated tender list
│   │   └── BidTable.tsx        # Bid details with screen metrics
│   └── ui/
│       ├── SummaryStats.tsx    # KPI cards with framer-motion animations
│       ├── ScoreCard.tsx       # SVG ring fraud score display
│       ├── RedFlagList.tsx     # Severity-coded flag list
│       ├── FilterPanel.tsx     # Tender filter sidebar
│       ├── AlertList.tsx       # Alert table with mark-read
│       ├── CollusionRingPanel.tsx # Ring list for graph page
│       ├── ThresholdSettings.tsx  # Admin alert threshold config
│       └── ExportPanel.tsx     # Audit log PDF export
│
├── contexts/
│   └── AuthContext.tsx         # JWT auth state, login/logout, token refresh
│
├── lib/
│   └── api.ts                  # Axios instance with Bearer token + refresh interceptor
│
└── types/
    ├── tender.ts               # Tender, Bid, FraudRiskScore, Explanation types
    ├── company.ts              # CompanyProfile, CompanyTender, CompanyRedFlag types
    └── graph.ts                # GraphNode, GraphEdge, CollusionRing types
```

---

## Design System

All design tokens are CSS variables defined in `globals.css`:

| Token | Value | Usage |
|---|---|---|
| `--bg-base` | `#080c14` | Page background |
| `--bg-card` | `#131d2e` | Card backgrounds |
| `--bg-surface` | `#0d1424` | Sidebar background |
| `--accent` | `#3b82f6` | Primary blue — links, active states |
| `--danger` | `#ef4444` | High risk indicators |
| `--warning` | `#f59e0b` | Medium risk indicators |
| `--success` | `#10b981` | Low risk / safe indicators |
| `--text-primary` | `#f1f5f9` | Main text |
| `--text-muted` | `#475569` | Labels, metadata |
| `--border` | `rgba(99,130,201,0.12)` | Card borders |

### Risk Score Color Bands

| Score | Color | Label |
|---|---|---|
| ≥ 70 | Red `#ef4444` | High Risk |
| 40–69 | Amber `#f59e0b` | Medium Risk |
| < 40 | Green `#10b981` | Low Risk |

### CSS Utility Classes

| Class | Purpose |
|---|---|
| `.ts-table` | Styled data table |
| `.ts-input` | Dark-themed form input |
| `.ts-btn` | Base button |
| `.ts-btn-primary` | Blue filled button |
| `.ts-btn-ghost` | Outlined button |
| `.badge` | Pill badge base |
| `.badge-red/amber/green/blue/gray` | Coloured badge variants |
| `.skeleton` | Shimmer loading placeholder |
| `.glass` | Glassmorphism card |
| `.gradient-text` | Blue-to-purple gradient text |

---

## Authentication Flow

1. User submits credentials at `/login`
2. `AuthContext.login()` calls `POST /auth/login/` → stores `access_token` + `refresh_token` in `localStorage`
3. Axios request interceptor attaches `Authorization: Bearer <token>` to every request
4. On 401 response, interceptor automatically calls `POST /auth/refresh/` and retries
5. On refresh failure → clears tokens → redirects to `/login`
6. `Layout.tsx` redirects unauthenticated users to `/login`

---

## Scripts

```bash
npm run dev      # Start dev server (hot reload)
npm run build    # Production build
npm run start    # Start production server
npm run lint     # ESLint
npm run test     # Jest unit tests
npm run test:e2e # Playwright end-to-end tests
```
