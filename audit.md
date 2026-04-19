TenderShield — Complete Codebase Audit
🧠 Phase 1: Codebase Understanding
What it is: An AI-powered government procurement fraud detection platform targeting Indian public tenders (GeM/CPPP). It ingests tender + bid data, runs 6 rule-based detectors + ML models (Isolation Forest + Random Forest), visualizes bidder collusion networks, and dispatches alerts.

Architecture: Modular Django monolith (11 apps) + Next.js SPA. Not microservices — it's a well-structured monolith with Celery for async work. This is appropriate for the scale.

Data flow: Tender/Bid ingestion → Rule engine → ML scoring (Celery) → SHAP explanation → Alert dispatch → Audit log. Clean and traceable.

Verdict on architecture: Solid foundation. The separation of concerns across Django apps is good. The main structural weakness is that the ML worker lives outside the Django app tree, creating an implicit coupling that's not enforced by the framework.

🔍 Phase 2: Deep Code Review
What's genuinely good
Immutable AuditLog with PermissionDenied on save()/delete() — this is production-grade thinking
bleach sanitization on all string inputs in serializers
AuditingJWTAuthentication that logs invalid key events — rare to see this level of care
BehavioralTracker never downgrades HIGH_RISK — correct business logic
CollusionGraph normalizes edge direction (A→B) and (B→A) as the same edge — subtle but correct
ScoringWeights.from_dict() with safe defaults — defensive programming done right
Dynamic chart loading with next/dynamic + skeleton fallbacks — good UX pattern
Bad practices
1. seed_demo_data.py — seed_graph() is never called

# handle() creates bidders, tenders, bids, red flags, scores, company profiles
# but seed_graph() is defined as a method and NEVER invoked from handle()
# The graph will be empty after seeding
The graph page will show nothing after running the seed command. This is a demo-killer bug.

2. Dashboard KPI "change" values are hardcoded

<KpiCard label="Total Tenders" value={stats?.total_tenders ?? null} change="3.5%" changeUp />
<KpiCard label="High Risk" value={stats?.high_risk_count ?? null} change="3.5%" changeUp={false} />
Every card shows "↑ 3.5%" or "↓ 3.5%" regardless of actual data. This is fake data presented as real analytics — a credibility killer in a demo.

3. Risk Distribution chart uses a hardcoded 27% estimate for "medium"

medium={stats ? Math.round(stats.total_tenders * 0.27) : undefined}
The backend doesn't return medium-risk count. The frontend invents it. This is misleading.

4. _rule_repeat_winner has an N+1 query inside a loop

for bidder_id in bidder_ids:
    for t in category_tenders:  # iterates all tenders in category
        lowest = Bid.objects.filter(tender=t).order_by("bid_amount").first()  # DB hit per tender
For a category with 500 tenders and 10 bidders, this is 5,000 DB queries per rule evaluation. This will time out in production.

5. _compute_avg_bid_deviation in BehavioralTracker loads all bids into Python memory

for bid in bids_qs.select_related("tender"):  # no limit
    deviations.append(...)
return sum(deviations) / len(deviations)
A bidder with 10,000 bids loads all of them. Use aggregate() instead.

6. LogoutView requires the refresh token in the request body but the frontend doesn't send it

# backend/authentication/views.py
refresh_token = request.data.get("refresh", "")
token = RefreshToken(refresh_token)
token.blacklist()
// frontend/contexts/AuthContext.tsx
await api.post("/auth/logout/");  // no body — refresh token not sent
Logout will always return 400. The token is never blacklisted. This is a security bug.

7. TenderStatusChangeView accepts lowercase statuses but the model uses uppercase

VALID_STATUSES = {"open", "closed", "awarded", "cancelled"}  # lowercase
# but TenderStatus choices are: ACTIVE, CLOSED, AWARDED, CANCELLED
tender.status = new_status  # saves "open" not "ACTIVE"
Status filtering will break because the DB stores "open" but queries filter on "ACTIVE".

8. globals.css reimplements Tailwind utilities manually The file has 200+ lines of hand-written utility classes (.flex, .gap-4, .p-3, etc.) that duplicate Tailwind. Since Tailwind v4 is installed, these are redundant and create maintenance confusion.

9. No useQuery / React Query used for data fetching despite being installed @tanstack/react-query is in package.json but every page uses raw useState + useEffect + useCallback for data fetching. This means no caching, no deduplication, no background refetch, no stale-while-revalidate. The library is dead weight.

10. CollusionRing membership check is O(n) Python loop

for ring in CollusionRing.objects.filter(member_count=len(sorted_ids), is_active=True):
    if sorted(ring.member_ids) == sorted_ids:  # loads ALL rings into memory
With thousands of rings this becomes a full table scan in Python.

🚨 Phase 3: Bug & Logic Detection
Bug 1 — Logout never blacklists the token (HIGH)
Why: Frontend sends POST /auth/logout/ with no body. Backend expects refresh in body, gets empty string, RefreshToken("") raises TokenError, returns 400. Fix:

// AuthContext.tsx
const logout = useCallback(async () => {
  try {
    const refresh = localStorage.getItem("refresh_token");
    await api.post("/auth/logout/", { refresh });  // send the token
  } catch { /* best-effort */ }
  // ... clear localStorage
}, []);
Bug 2 — seed_graph() never called (HIGH)
Why: seed_graph() is defined as an instance method but handle() never calls self.seed_graph(...). The graph page will be empty. Fix: Add at the end of handle():

self.seed_graph(b1, b2, b3, b4, b5, t1, t3, t4, t5, t6, t7, t8, now)
Bug 3 — Status mismatch (MEDIUM)
Why: VALID_STATUSES = {"open", "closed", ...} but TenderStatus uses "ACTIVE", "CLOSED". Saving "open" to the DB breaks all status-based queries. Fix:

VALID_STATUSES = {
    TenderStatus.ACTIVE, TenderStatus.CLOSED,
    TenderStatus.AWARDED, TenderStatus.CANCELLED
}
Bug 4 — Race condition in AlertSystem.check_and_alert (MEDIUM)
Two Celery workers can simultaneously evaluate the same tender and create duplicate alerts for the same user. There's no unique_together on (tender, user, alert_type) and no select_for_update. Fix: Add a unique constraint:

class Meta:
    unique_together = [("tender", "user", "alert_type")]
Or use get_or_create with a deduplication key.

Bug 5 — _rule_price_anomaly uses bids.first() (lowest bid) as "winning bid" (MEDIUM)
winning_bid = bids.first()  # ordered by bid_amount ascending — lowest bid
The lowest bid is not necessarily the winner. It should use bids.filter(is_winner=True).first(). If no winner is marked, the rule fires incorrectly.

Bug 6 — AuditLog.save() check uses self.pk is not None but MySQL auto-increment assigns pk before save (LOW)
Django's save() for new objects: self.pk is None before the first save. This check is correct for Django's default behavior, but if pk is explicitly set (e.g., in fixtures or bulk operations), the immutability check will incorrectly block the initial insert.

Bug 7 — DataGovClient API key exposed in query params (MEDIUM)
params = {"api-key": self.api_key, ...}
requests.get(self.url, params=params)
The API key appears in the URL query string, which gets logged by web servers, proxies, and Django's request logging. Use a header instead:

headers = {"api-key": self.api_key}
requests.get(self.url, params=params, headers=headers, timeout=30)
🔐 Phase 4: Security Audit
CRITICAL — JWT fallback to SECRET_KEY in production
"SIGNING_KEY": _jwt_private_key or SECRET_KEY,  # fallback to SECRET_KEY in dev
If JWT_PRIVATE_KEY is not set in production (misconfiguration, missing env var), the system silently falls back to signing JWTs with the Django SECRET_KEY using HS256 semantics. An attacker who obtains the SECRET_KEY (e.g., via a .env leak) can forge arbitrary JWTs. Severity: CRITICAL Fix: Fail hard if keys are missing in non-DEBUG mode:

if not DEBUG and not _jwt_private_key:
    raise ImproperlyConfigured("JWT_PRIVATE_KEY must be set in production")
HIGH — Tokens stored in localStorage (XSS-accessible)
localStorage.setItem("access_token", data.access);
localStorage.setItem("refresh_token", data.refresh);
Any XSS vulnerability (in a dependency, a third-party script, or a future bug) can steal both tokens. The refresh token has a 7-day lifetime. Severity: HIGH Fix: Store tokens in httpOnly cookies. The backend already has CORS_ALLOW_CREDENTIALS = True. Switch to cookie-based token delivery:

response.set_cookie("access_token", str(access), httponly=True, secure=True, samesite="Strict")
HIGH — HTTP_X_FORWARDED_FOR IP extraction is naive
def _get_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
X-Forwarded-For is user-controlled. An attacker can spoof their IP in audit logs and bypass IP-based rate limiting by sending X-Forwarded-For: 127.0.0.1. Use Django's SECURE_PROXY_SSL_HEADER and a proper IP extraction library, or trust only the last IP in the chain (the one added by your trusted proxy).

MEDIUM — Rate limiting silently disabled when Redis is unavailable
SILENCED_SYSTEM_CHECKS = ["django_ratelimit.W001", "django_ratelimit.E003"]
When Redis is down, django-ratelimit silently allows all requests through. The login endpoint (10/m rate limit) becomes unprotected. This is a brute-force window. Fix: Fail closed — if Redis is unavailable, reject requests to rate-limited endpoints rather than allowing them.

MEDIUM — spec_text stored as plaintext in the DB
The spec_text field can contain up to 100,000 characters of tender specification text. This is sensitive government procurement data. It's stored unencrypted. Consider field-level encryption for sensitive fields.

LOW — Django Admin exposed without additional protection
path("admin/", admin.site.urls) is accessible at /admin/. In production this should be behind IP allowlisting or moved to a non-guessable path.

LOW — ROTATE_REFRESH_TOKENS = False
Refresh tokens are not rotated on use. A stolen refresh token remains valid for 7 days with no way to detect reuse. Fix: Set ROTATE_REFRESH_TOKENS = True and BLACKLIST_AFTER_ROTATION = True.

⚡ Phase 5: Performance Optimization
Issue 1 — N+1 in _rule_repeat_winner (CRITICAL for scale)
As described above. Fix with a single aggregation query:

from django.db.models import Count, Q

# Get win counts per bidder in one query
win_counts = (
    Bid.objects.filter(
        tender__in=category_tenders,
        bidder_id__in=bidder_ids,
        is_winner=True,
    )
    .values("bidder_id")
    .annotate(wins=Count("id"))
)
Issue 2 — TenderStatsView runs 4 separate DB queries
total_tenders = qs.count()       # query 1
high_risk_count = qs.filter(...) # query 2
high_flag_count = Tender.objects.filter(...).count()  # query 3
collusion_ring_count = CollusionRing.objects.filter(...).count()  # query 4
These can't easily be combined, but they should be cached (Redis, 60s TTL) since the dashboard polls this on every load.

Issue 3 — CollusionGraph.detect_collusion_rings() makes 4+ DB queries and loads all edges into Python
For large datasets this will be slow. The union-find algorithm is correct but the data loading is not batched. Add select_related and consider running this as a background task only, not on every bid ingestion.

Issue 4 — No database connection pooling configured
MySQL connections are created per-request with no pooling. Under load this will exhaust MySQL's connection limit. Add django-db-geventpool or configure CONN_MAX_AGE:

DATABASES["default"]["CONN_MAX_AGE"] = 60
Issue 5 — Frontend fetches tender list AND stats on every dashboard mount
Both fetchTenders and fetchStats fire on mount with no caching. With React Query already installed, this is a missed optimization. Add a 30-second stale time.

🎨 Phase 6: UI/UX Critique
What works well
The dark theme design system is cohesive and professional
Skeleton loading states are implemented correctly
Framer Motion animations are subtle and appropriate
The login page is clean and well-structured
Score badges (red/amber/green) provide instant visual hierarchy
What's broken or cheap
1. Hardcoded fake KPI changes destroy credibility The "↑ 3.5%" on every KPI card is the first thing a judge or investor will notice. It signals the data isn't real. Either compute real period-over-period changes from the API or remove the change indicators entirely.

2. No dark/light mode toggle The entire app is hardcoded dark. Government procurement auditors often work in bright office environments. No accessibility consideration for users who need light mode.

3. No empty states When there are no tenders, no alerts, no graph nodes — the UI shows nothing or a loading spinner that never resolves. Every list view needs a proper empty state with a call to action.

4. The collusion graph page has no loading state for the vis-network canvas The graph can take 2-5 seconds to render. There's no skeleton or progress indicator during this time.

5. Mobile responsiveness is incomplete The dashboard's 2-column chart grid (gridTemplateColumns: "1fr 1fr") has no responsive breakpoint. On a 375px screen the charts are crushed to ~170px wide and unreadable. Fix:

style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))", gap: "0.75rem" }}
6. The filter panel is hidden on mobile behind a button but the button is only shown on xl:hidden

<button onClick={() => setShowFilters(!showFilters)} className="ts-btn ts-btn-ghost xl:hidden">
On desktop the filter panel is always visible. On mobile it's toggled. But the toggle button uses Tailwind's xl:hidden while the panel uses hidden xl:block. This logic is correct but the CSS class mixing (Tailwind + custom) is fragile.

7. Typography scale is too small Body text at 14px, labels at 0.68rem (≈10.9px), muted text at 0.72rem (≈11.5px). WCAG AA requires minimum 4.5:1 contrast ratio for text under 18px. The --text-muted: #52525b on #1a1a1a background fails contrast requirements.

8. No keyboard navigation for tables The tender table rows are clickable but have no tabIndex, no onKeyDown handler, and no focus styles. Keyboard-only users cannot navigate the table.

9. globals.css reimplements Tailwind 200+ lines of manual utility classes that duplicate Tailwind v4. This creates two sources of truth for spacing, colors, and layout. Pick one system.

10. No toast/notification system Success and error states are shown inline. There's no global notification system for async operations (rescore triggered, export queued, etc.). Users have no feedback for background operations.

🧪 Phase 7: Testing & Reliability
What exists
15 test files covering auth, rules, scoring, alerts, audit, behavioral tracking, graph, ML, NLP, XAI, security, and integration. This is a strong test suite for a hackathon project.

Critical gaps
1. No test for the logout token blacklist bug The most critical security bug (logout not blacklisting tokens) has no test.

2. No test for the seed_graph() not being called The demo data bug would be caught immediately by an integration test that checks graph node count after seeding.

3. test_rules.py likely doesn't test the N+1 query Performance regressions in rule evaluation won't be caught.

4. No frontend tests for auth flow The AuthContext has no unit tests. The token refresh interceptor in api.ts has no tests. These are the most critical frontend paths.

5. No E2E test for the full fraud detection pipeline Tender ingestion → rule evaluation → score computation → alert dispatch should have an E2E test. The test_integration.py may cover this but it's worth verifying.

6. Property-based tests exist (test_nlp_score_property.py) — this is excellent The use of Hypothesis for property-based testing of the NLP scoring is genuinely impressive and rare. Keep this.

🚀 Phase 8: Product Thinking
Is this solving a real problem?
Yes. Government procurement fraud costs India an estimated ₹1-3 lakh crore annually (CVC estimates). The problem is real, the market is large, and the regulatory environment (CVC, CAG, RTI) creates demand for audit tools.

What makes it unique
NLP spec analysis (tailoring, copy-paste detection) is genuinely novel — most fraud detection tools don't analyze the tender specification text itself
The collusion graph visualization is a strong differentiator
SHAP explanations make the AI decisions auditable — critical for government adoption
Immutable audit log with 7-year retention shows regulatory awareness
Why judges would care
The combination of rule-based + ML + NLP + graph analysis in one platform is technically impressive. The domain (government procurement fraud) has clear social impact.

Weaknesses in the idea
No real-time data pipeline — the system is batch-oriented. Real fraud detection needs streaming ingestion
No case management — when a fraud is detected, there's no workflow for investigators to track, assign, and resolve cases
No feedback loop — investigators can't mark a detection as "false positive" to improve the model
Single-tenant — the system is designed for one organization. Multi-tenancy would 10x the addressable market
No API for external systems — procurement systems (GeM, CPPP) can't push data in real-time
🏆 Phase 9: Hackathon Winning Edge
Features that impress judges instantly
1. Live fraud detection demo Seed the demo data, show a tender being ingested in real-time, watch the score jump from 0 to 91, see the alert fire, see the graph update. This is a 60-second demo that wins rooms.

2. Natural language query interface Add a simple chat interface: "Show me all tenders in Roads & Highways with score above 70 in the last 30 days." Use the existing LLM integration to translate to API calls. This is a 2-hour feature that looks like magic.

3. Fraud pattern similarity search "This tender looks 87% similar to a previously confirmed fraud case." The NLP vector store is already there — surface it in the UI.

4. One-click PDF investigation report The audit export exists. Make it generate a beautiful PDF report for a specific tender: score, SHAP chart, red flags, bid table, collusion graph screenshot, timeline. This is what investigators actually need.

5. Real-time alert badge in the nav Show a live unread alert count in the sidebar. Poll every 30 seconds. This makes the platform feel alive during a demo.

📊 Final Output
🔴 Critical Issues (must fix before demo)
seed_graph() never called — graph page is empty after seeding
Logout doesn't blacklist tokens — frontend doesn't send refresh token in body
JWT falls back to SECRET_KEY — silent security failure in production misconfiguration
Hardcoded "3.5%" KPI changes — fake data destroys credibility
N+1 query in _rule_repeat_winner — will time out on real data
🟡 Important Improvements
Fix TenderStatusChangeView status case mismatch (lowercase vs uppercase)
Fix _rule_price_anomaly to use is_winner=True instead of lowest bid
Add unique_together on Alert(tender, user, alert_type) to prevent duplicate alerts
Fix Risk Distribution chart — don't hardcode 27% medium estimate
Fix mobile chart grid responsiveness
Add CONN_MAX_AGE for MySQL connection reuse
Set ROTATE_REFRESH_TOKENS = True
Move tokens from localStorage to httpOnly cookies
Fix X-Forwarded-For IP extraction to use trusted proxy chain
🟢 Nice-to-have Enhancements
Replace manual useState/useEffect data fetching with React Query (already installed)
Add toast notification system for async operations
Add empty states for all list views
Add keyboard navigation to tables
Add dark/light mode toggle
Remove the 200+ lines of manual Tailwind duplicates from globals.css
Add a loading skeleton for the collusion graph canvas
Add real period-over-period KPI change computation
🔐 Security Fixes
Vulnerability	Severity	Fix
JWT falls back to SECRET_KEY	Critical	Fail hard if JWT_PRIVATE_KEY not set in production
Tokens in localStorage	High	Switch to httpOnly cookies
Logout doesn't blacklist	High	Send refresh token in logout request
Spoofable X-Forwarded-For	High	Trust only proxy-added IPs
Rate limiting fails open	Medium	Fail closed when Redis unavailable
API key in query params	Medium	Move to request header
Refresh tokens not rotated	Low	ROTATE_REFRESH_TOKENS = True
Django Admin exposed	Low	IP allowlist or obscure path
⚡ Performance Fixes
Rewrite _rule_repeat_winner with aggregation queries (eliminates N+1)
Cache TenderStatsView response in Redis (60s TTL)
Add CONN_MAX_AGE = 60 to database config
Replace _compute_avg_bid_deviation loop with aggregate()
Add React Query with 30s stale time for dashboard data
🎨 UI/UX Redesign Suggestions
Fix the fake KPI change percentages — either compute real ones or remove them
Fix mobile chart grid (use auto-fit minmax(300px, 1fr))
Increase minimum text size to 12px, fix --text-muted contrast ratio
Add keyboard navigation (tabIndex, onKeyDown) to table rows
Add a global toast system (use sonner — 1KB, zero config)
Add empty states with illustrations for all list views
Add a loading state for the graph canvas
Consider a light mode variant for government office environments
🚀 New Features to Add (ranked by impact/effort)
Case management — let investigators assign, track, and close fraud cases (HIGH impact, MEDIUM effort)
False positive feedback — "Mark as reviewed / not fraud" to improve model over time (HIGH impact, LOW effort)
Natural language query — chat interface over the tender database (HIGH impact, MEDIUM effort)
Real-time alert badge — unread count in sidebar nav (HIGH impact, LOW effort)
One-click investigation PDF — beautiful report for a single tender (HIGH impact, LOW effort)
Multi-tenancy — organization-scoped data isolation (HIGH impact, HIGH effort)
Streaming ingestion webhook — let GeM/CPPP push tenders in real-time (MEDIUM impact, MEDIUM effort)
🏆 Make it Award-Winning — Step-by-Step Roadmap
Day 1 (fix the broken things):

Fix seed_graph() call
Fix logout token blacklist
Fix hardcoded KPI percentages
Fix status case mismatch
Fix mobile responsiveness
Day 2 (make it impressive):

Add real-time alert badge in sidebar
Add empty states
Add toast notifications
Wire up React Query for caching
Add one-click investigation PDF
Day 3 (make it unforgettable):

Add "Mark as reviewed" feedback loop
Add natural language query interface (even a simple one)
Polish the demo flow: ingest → detect → alert → investigate → report
Record a 90-second demo video showing the full pipeline
Demo script: Start with the graph page showing the collusion ring. Click into the highest-risk tender. Show the SHAP explanation. Show the red flags. Trigger a manual rescore. Watch the alert fire. Export the PDF report. That's a winning demo.

Bottom line: This is a technically impressive project with a real-world use case, solid security thinking, and good architectural bones. The critical bugs (logout, seed_graph, fake KPIs) are all fixable in a few hours. Fix those, add the real-time alert badge and investigation PDF, and this is a strong hackathon contender. The NLP spec analysis and immutable audit log are genuinely differentiating features that most competitors won't have.