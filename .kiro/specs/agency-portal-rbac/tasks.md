# Tasks

## Task List

- [ ] 1. Backend: `agencies` Django App Scaffold
  - [ ] 1.1 Create `agencies` Django app and register it in `INSTALLED_APPS`
  - [ ] 1.2 Extend `UserRole` choices in `authentication/models.py` with `AGENCY_ADMIN`, `AGENCY_OFFICER`, `REVIEWER`, `GOVERNMENT_AUDITOR`
  - [ ] 1.3 Add `agency` FK and `email_verified` fields to `authentication.User` via migration
  - [ ] 1.4 Create `Agency` model with `agency_id`, `legal_name`, `gstin`, `ministry`, `contact_name`, `contact_email`, `status`, `created_at`, `approved_at`
  - [ ] 1.5 Create `Invitation` model with `token_hash`, `email`, `role`, `agency`, `invited_by`, `expires_at`, `consumed_at`
  - [ ] 1.6 Create `EmailVerificationToken` model with `user`, `token_hash`, `expires_at`
  - [ ] 1.7 Create `TenderSubmission` model with all fields, `AgencyScopedManager`, `VALID_TRANSITIONS` dict, and `transition_to()` method
  - [ ] 1.8 Add new `EventType` choices to `audit/models.py`: `AGENCY_REGISTERED`, `AGENCY_STATUS_CHANGED`, `INVITATION_CREATED`, `INVITATION_ACCEPTED`, `MEMBER_DEACTIVATED`, `PERMISSION_DENIED`, `TENDER_SUBMITTED`, `TENDER_CLEARED`, `GOV_AUDITOR_ACCESS`
  - [ ] 1.9 Run and verify all migrations

- [ ] 2. Backend: RBAC Permission Layer
  - [ ] 2.1 Create `agencies/permissions.py` with `IsAgencyRole`, `IsAgencyAdmin`, `IsAgencyOfficerOrAdmin`, `IsGovernmentAuditorOrAdmin`, `AgencyObjectPermission` classes
  - [ ] 2.2 Create `agencies/jwt_auth.py` with `AgencyAwareJWTAuthentication` that checks agency suspension on `get_user()`
  - [ ] 2.3 Create `agencies/serializers.py` with `AgencyTokenObtainPairSerializer` injecting `agency_id` and `role` into JWT payload
  - [ ] 2.4 Create `agencies/exceptions.py` with `agency_exception_handler` that writes `PERMISSION_DENIED` AuditLog entries on HTTP 403
  - [ ] 2.5 Update `REST_FRAMEWORK` settings to use `AgencyAwareJWTAuthentication` and `agency_exception_handler`
  - [ ] 2.6 Create GSTIN validator function matching pattern `[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}`

- [ ] 3. Backend: Agency Registration and Onboarding API
  - [ ] 3.1 Create `POST /api/v1/agencies/register/` view: validate fields, check GSTIN/email uniqueness, create `Agency` (PENDING_APPROVAL) and `User` (is_active=False, AGENCY_ADMIN), create `EmailVerificationToken`, enqueue verification email task
  - [ ] 3.2 Create `GET /api/v1/agencies/verify-email/` view: validate token, set `User.is_active=True`, `User.email_verified=True`, `Agency.status=ACTIVE`, write AuditLog
  - [ ] 3.3 Create Celery task `send_verification_email` in `agencies/tasks.py`
  - [ ] 3.4 Add `POST /api/v1/agencies/register/` and `GET /api/v1/agencies/verify-email/` to `agencies/urls.py`

- [ ] 4. Backend: Agency Member Invitation API
  - [ ] 4.1 Create `POST /api/v1/agencies/me/invitations/` view: validate role (AGENCY_OFFICER or REVIEWER only), generate 32-byte random token, store SHA-256 hash, set expiry 72h, enqueue invitation email task, write AuditLog
  - [ ] 4.2 Create `GET /api/v1/agencies/me/invitations/accept/` view: validate token hash, check expiry and consumed state (return 410 if invalid), return invitation details for pre-fill
  - [ ] 4.3 Create `POST /api/v1/agencies/me/invitations/accept/` view: complete registration, create `User` with invitation's role and agency, mark invitation consumed, write AuditLog
  - [ ] 4.4 Create Celery task `send_invitation_email` in `agencies/tasks.py`
  - [ ] 4.5 Create `GET /api/v1/agencies/me/members/` view: list active members scoped to admin's agency
  - [ ] 4.6 Create `PATCH /api/v1/agencies/me/members/:id/deactivate/` view: set `is_active=False`, blacklist all active refresh tokens for that user, write AuditLog; enforce same-agency constraint

- [ ] 5. Backend: Agency Profile API
  - [ ] 5.1 Create `GET /api/v1/agencies/me/` view: return agency profile for authenticated agency user
  - [ ] 5.2 Create `PATCH /api/v1/agencies/me/` view (AGENCY_ADMIN only): allow updating `contact_name`, `contact_email`, `ministry`; reject GSTIN updates with HTTP 400; write AuditLog with field diffs (previous and new values)

- [ ] 6. Backend: Tender Submission API
  - [ ] 6.1 Create `GET /api/v1/agencies/me/tenders/` view: return paginated, filtered, sorted `TenderSubmission` list scoped to user's agency; support filters: `status`, `category`, `date_range`; support sort: `created_at`, `estimated_value`, `fraud_risk_score`
  - [ ] 6.2 Create `POST /api/v1/agencies/me/tenders/` view (AGENCY_ADMIN, AGENCY_OFFICER): validate all required fields, validate `estimated_value` is positive decimal with ≤ 2 decimal places, validate `submission_deadline` is in the future, sanitise `title`/`spec_text`/`buyer_name` with bleach, create `TenderSubmission` with status DRAFT, write AuditLog
  - [ ] 6.3 Create `GET /api/v1/agencies/me/tenders/:id/` view: return tender detail with fraud score and red flags; enforce agency scoping
  - [ ] 6.4 Create `PATCH /api/v1/agencies/me/tenders/:id/` view: enforce DRAFT-only editing; enforce Agency_Officer can only edit own tenders; sanitise inputs; write AuditLog
  - [ ] 6.5 Create `DELETE /api/v1/agencies/me/tenders/:id/` view: enforce DRAFT-only deletion; enforce Agency_Officer can only delete own tenders; write AuditLog
  - [ ] 6.6 Create `POST /api/v1/agencies/me/tenders/:id/submit/` view: transition status DRAFT→SUBMITTED, create corresponding `Tender` record, enqueue `score_agency_tender` Celery task within 5 seconds, write AuditLog
  - [ ] 6.7 Create `GET /api/v1/agencies/tenders/` view (GOVERNMENT_AUDITOR, ADMIN): return all tenders across all agencies with agency name and ID
  - [ ] 6.8 Create `PATCH /api/v1/agencies/tenders/:id/clear/` view (GOVERNMENT_AUDITOR, ADMIN): transition FLAGGED→CLEARED; require `review_note` of ≥ 10 characters; write AuditLog with reviewer ID and note

- [ ] 7. Backend: Fraud Detection Pipeline Integration
  - [ ] 7.1 Create `score_agency_tender` Celery task in `agencies/tasks.py`: call existing `score_tender` task, then update `TenderSubmission.status` based on score (≥70 → UNDER_REVIEW, <40 → CLEARED), create `Alert` records for Agency_Admin and Agency_Officers if score ≥ 70, write AuditLog
  - [ ] 7.2 Handle `score_agency_tender` permanent failure (after 3 retries): keep `TenderSubmission.status` as SUBMITTED, create internal `Alert` for ADMIN users, write AuditLog with error details
  - [ ] 7.3 Add `UNDER_REVIEW→FLAGGED` transition trigger: when `RedFlag` records are created for a `TenderSubmission`, transition status to FLAGGED and send email to Agency_Admin within 5 minutes via Celery task
  - [x] 7.4 Verify existing `Tender` model and pipeline are unaffected by the new `TenderSubmission` wrapper

- [ ] 8. Backend: JWT Token Lifetime Configuration
  - [x] 8.1 Update `SIMPLE_JWT` settings: set `ACCESS_TOKEN_LIFETIME` to 15 minutes and `REFRESH_TOKEN_LIFETIME` to 24 hours for agency users (configurable via env vars `AGENCY_JWT_ACCESS_LIFETIME`, `AGENCY_JWT_REFRESH_LIFETIME`)

- [ ] 9. Backend: URL Routing
  - [x] 9.1 Create `agencies/urls.py` with all agency API routes
  - [x] 9.2 Register `agencies/urls.py` under `api/v1/agencies/` in `config/urls.py`

- [ ] 10. Backend: Property-Based and Unit Tests
  - [x] 10.1 Write Hypothesis property test for Property 1 (agency-scoped queryset never leaks cross-agency data): generate random multi-agency submission datasets, verify `for_agency()` returns only own-agency records
  - [x] 10.2 Write Hypothesis property test for Property 2 (RBAC permission denial is exhaustive): generate random (role, action) pairs not in the permission matrix, verify `has_permission()` returns False
  - [x] 10.3 Write Hypothesis property test for Property 3 (status machine admits only valid transitions): generate random (current_status, target_status) pairs, verify `transition_to()` raises ValueError for invalid transitions
  - [x] 10.4 Write Hypothesis property test for Property 4 (invitation token round-trip): generate random 32-byte tokens, verify SHA-256 hash lookup returns correct invitation
  - [x] 10.5 Write Hypothesis property test for Property 5 (GSTIN validation): generate random strings from GSTIN alphabet and random invalid strings, verify validator accepts/rejects correctly
  - [x] 10.6 Write Hypothesis property test for Property 6 (suspended agency blocks all authentication): generate random users with suspended agencies, verify `AgencyAwareJWTAuthentication.get_user()` raises AuthenticationFailed
  - [ ] 10.7 Write Hypothesis property test for Property 7 (bleach sanitisation is idempotent on clean input): generate random strings without HTML, verify `bleach_clean(s) == s`
  - [ ] 10.8 Write unit tests for GSTIN validator with valid and invalid format examples
  - [ ] 10.9 Write unit tests for `TenderSubmission.transition_to()` covering all valid transitions
  - [ ] 10.10 Write unit tests for `Invitation.is_valid` with expired and consumed invitations
  - [ ] 10.11 Write integration tests for agency registration → email verification → login flow
  - [ ] 10.12 Write integration tests for invitation send → accept → user created with correct role and agency
  - [ ] 10.13 Write integration tests for cross-agency access attempt returning HTTP 403
  - [ ] 10.14 Write integration tests for Government Auditor cross-agency read and write-block behavior

- [ ] 11. Frontend: Auth Context and API Client Extension
  - [ ] 11.1 Extend `UserRole` type in `AuthContext.tsx` to include `AGENCY_ADMIN`, `AGENCY_OFFICER`, `REVIEWER`, `GOVERNMENT_AUDITOR`
  - [ ] 11.2 Add `agencyId: string | null` to `AuthState` interface and persist/rehydrate from `localStorage`
  - [ ] 11.3 Update `login()` in `AuthContext.tsx` to extract and store `agency_id` from JWT response
  - [ ] 11.4 Create `frontend/services/agencies.ts` with typed API functions for all agency endpoints

- [ ] 12. Frontend: Public Landing Page
  - [ ] 12.1 Replace `frontend/app/page.tsx` redirect with a full landing page component
  - [ ] 12.2 Implement `LandingPage` with TenderShield value propositions (fraud detection, rule engine, ML scoring, audit trail) and a prominent CTA button navigating to `/agency/register`
  - [ ] 12.3 Ensure landing page is responsive down to 320px viewport width

- [ ] 13. Frontend: Agency Registration and Onboarding
  - [ ] 13.1 Create `frontend/app/agency/register/page.tsx` with `AgencyRegistrationForm` collecting all required fields
  - [ ] 13.2 Implement client-side GSTIN format validation in the registration form
  - [ ] 13.3 Display field-level validation errors for missing required fields
  - [ ] 13.4 Display server-side errors for duplicate GSTIN and duplicate email
  - [ ] 13.5 Create `frontend/app/agency/verify-email/page.tsx` that reads the token from the URL query param and calls the verification endpoint
  - [ ] 13.6 Create `frontend/app/agency/invite/[token]/page.tsx` for invitation acceptance with pre-filled email

- [ ] 14. Frontend: Agency Dashboard
  - [ ] 14.1 Create `frontend/app/agency/dashboard/page.tsx` with route guard (redirect to `/login` if not authenticated with an agency role)
  - [ ] 14.2 Implement KPI cards: total submissions, high-risk count (score ≥ 70), active alerts count, under-review count
  - [ ] 14.3 Implement paginated tender list with columns: tender ID, title, category, estimated value, status, fraud risk score, submission date
  - [ ] 14.4 Create `RiskBadge` component: green for score < 40, amber for 40–69, red for ≥ 70
  - [ ] 14.5 Implement filter controls: status dropdown, category dropdown, date range picker
  - [ ] 14.6 Implement sort controls: submission date (default desc), estimated value, fraud risk score
  - [ ] 14.7 Hide "Create Tender" button for `REVIEWER` role
  - [ ] 14.8 Implement real-time alert notification display (poll or WebSocket) for Agency_Admin and Agency_Officer users

- [ ] 15. Frontend: Tender Submission Form
  - [ ] 15.1 Create `frontend/app/agency/tenders/new/page.tsx` with `TenderSubmissionForm`
  - [ ] 15.2 Implement all form fields: tender reference number, title, category (predefined list), estimated value, submission deadline, publication date, buyer department name, spec text (up to 100,000 chars)
  - [ ] 15.3 Implement client-side validation: required fields, positive decimal estimated value, future submission deadline
  - [ ] 15.4 Implement save as draft and submit actions
  - [ ] 15.5 Create `frontend/app/agency/tenders/[id]/page.tsx` for tender detail view with fraud score, risk badge, and red flag summary

- [ ] 16. Frontend: Agency Profile Management
  - [ ] 16.1 Create `frontend/app/agency/profile/page.tsx` with agency profile view
  - [ ] 16.2 Implement editable fields for Agency_Admin: contact name, contact email, ministry
  - [ ] 16.3 Display GSTIN as read-only with a tooltip explaining it cannot be changed
  - [ ] 16.4 Display agency status with a suspension banner when status is SUSPENDED
  - [ ] 16.5 Implement member list table with name, email, role, last login; include deactivate action for Agency_Admin
  - [ ] 16.6 Implement `InviteMemberModal` for Agency_Admin to send invitations (role: AGENCY_OFFICER or REVIEWER)

- [ ] 17. Frontend: Government Auditor Cross-Agency View
  - [ ] 17.1 Create `frontend/app/agency/tenders/page.tsx` for GOVERNMENT_AUDITOR cross-agency tender list (reuse dashboard list component with agency name/ID column added)
  - [ ] 17.2 Ensure all write actions (create, edit, delete, submit) are hidden/disabled for GOVERNMENT_AUDITOR role

- [ ] 18. Frontend: Tests
  - [ ] 18.1 Write Jest unit tests for `RiskBadge` component: verify correct colour class for scores < 40, 40–69, ≥ 70
  - [ ] 18.2 Write Jest unit tests for `AgencyRegistrationForm`: verify field-level errors for missing required fields
  - [ ] 18.3 Write Jest unit tests for `TenderSubmissionForm`: verify past deadline rejection
  - [ ] 18.4 Write Jest unit tests for `AgencyDashboard` filter and sort logic
