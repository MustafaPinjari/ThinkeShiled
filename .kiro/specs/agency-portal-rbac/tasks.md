# Implementation Plan: Agency Portal RBAC

## Overview

Implement multi-tenancy at the agency level, a four-role RBAC model, a public landing page, an agency dashboard, tender submission through the portal, and integration with the existing fraud detection pipeline. The backend is Django (DRF + SimpleJWT + Celery + MySQL); the frontend is Next.js.

## Tasks

- [x] 1. Backend: `agencies` Django App Scaffold
  - [x] 1.1 Create `agencies` Django app and register it in `INSTALLED_APPS`
    - App config exists at `backend/agencies/apps.py`
    - _Requirements: 1.1, 2.1_
  - [x] 1.2 Extend `UserRole` choices in `authentication/models.py` with `AGENCY_ADMIN`, `AGENCY_OFFICER`, `REVIEWER`, `GOVERNMENT_AUDITOR`
    - Note: `authentication/models.py` still only has `AUDITOR` and `ADMIN` — this migration is needed
    - _Requirements: 3.1_
  - [x] 1.3 Add `agency` FK and `email_verified` fields to `authentication.User` via migration
    - _Requirements: 2.2, 2.3, 9.2_
  - [x] 1.4 Create `Agency` model with `agency_id`, `legal_name`, `gstin`, `ministry`, `contact_name`, `contact_email`, `status`, `created_at`, `approved_at`
    - Implemented in `backend/agencies/models.py`
    - _Requirements: 2.1_
  - [x] 1.5 Create `Invitation` model with `token_hash`, `email`, `role`, `agency`, `invited_by`, `expires_at`, `consumed_at`, and `is_valid` property
    - Implemented in `backend/agencies/models.py`
    - _Requirements: 4.1, 4.5_
  - [x] 1.6 Create `EmailVerificationToken` model with `user`, `token_hash`, `expires_at`
    - Implemented in `backend/agencies/models.py`
    - _Requirements: 1.8, 1.9_
  - [x] 1.7 Create `TenderSubmission` model with all fields, `AgencyScopedManager`, `VALID_TRANSITIONS` dict, and `transition_to()` method
    - Implemented in `backend/agencies/models.py`
    - _Requirements: 6.1, 6.2, 7.1, 8.1_
  - [x] 1.8 Add new `EventType` choices to `audit/models.py`: `AGENCY_REGISTERED`, `AGENCY_STATUS_CHANGED`, `INVITATION_CREATED`, `INVITATION_ACCEPTED`, `MEMBER_DEACTIVATED`, `PERMISSION_DENIED`, `TENDER_SUBMITTED`, `TENDER_CLEARED`, `GOV_AUDITOR_ACCESS`
    - Current `audit/models.py` is missing all agency-specific event types
    - _Requirements: 2.6, 3.9, 4.9, 7.3, 9.3, 12.6_
  - [x] 1.9 Run and verify all migrations
    - `backend/agencies/migrations/0001_initial.py` exists and covers all new models
    - _Requirements: 2.1_

- [x] 2. Backend: RBAC Permission Layer
  - [x] 2.1 Create `agencies/permissions.py` with `IsAgencyRole`, `IsAgencyAdmin`, `IsAgencyOfficerOrAdmin`, `IsGovernmentAuditorOrAdmin`, `AgencyObjectPermission`, `PERMISSION_MATRIX`, and `has_permission()` function
    - Fully implemented in `backend/agencies/permissions.py`
    - _Requirements: 3.1–3.8_
  - [x] 2.2 Create `agencies/jwt_auth.py` with `AgencyAwareJWTAuthentication` that checks agency suspension on `get_user()`
    - Fully implemented in `backend/agencies/jwt_auth.py`
    - _Requirements: 2.5, 9.7_
  - [x] 2.3 Create `agencies/serializers.py` with `AgencyTokenObtainPairSerializer` injecting `agency_id` and `role` into JWT payload
    - File does not exist yet
    - _Requirements: 9.2_
  - [x] 2.4 Create `agencies/exceptions.py` with `agency_exception_handler` that writes `PERMISSION_DENIED` AuditLog entries on HTTP 403
    - File does not exist yet
    - _Requirements: 3.9_
  - [x] 2.5 Update `REST_FRAMEWORK` settings to use `AgencyAwareJWTAuthentication` as the default authentication class and register `agency_exception_handler` as the exception handler
    - _Requirements: 9.1, 3.9_
  - [x] 2.6 Create GSTIN validator function in `agencies/validators.py` matching pattern `[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}`
    - Fully implemented in `backend/agencies/validators.py`
    - _Requirements: 2.7_

- [x] 3. Backend: Agency Registration and Onboarding API
  - [x] 3.1 Implement `POST /api/v1/agencies/register/` view: validate all required fields, check GSTIN uniqueness (400 if duplicate), check email uniqueness (400 if duplicate), validate GSTIN format, create `Agency` (status=`PENDING_APPROVAL`) and `User` (role=`AGENCY_ADMIN`, `is_active=False`), create `EmailVerificationToken`, enqueue `send_verification_email` Celery task, write `AGENCY_REGISTERED` AuditLog entry
    - _Requirements: 1.4, 1.5, 1.6, 1.7, 1.8, 2.1, 2.2, 2.7_
  - [x] 3.2 Implement `GET /api/v1/agencies/verify-email/` view: look up `EmailVerificationToken` by hash, reject expired tokens, set `User.is_active=True`, `User.email_verified=True`, `Agency.status=ACTIVE`, set `Agency.approved_at`, write `AGENCY_STATUS_CHANGED` AuditLog entry
    - _Requirements: 1.9, 2.3_
  - [x] 3.3 Create Celery task `send_verification_email` in `agencies/tasks.py`: send verification email using existing `send_alert_email` pattern; retry up to 3 times; mark `EmailVerificationToken.delivery_failed=True` on permanent failure and raise internal `ADMIN` alert
    - _Requirements: 1.8_
  - [x] 3.4 Add login rate-limiting and account lockout to the agency login flow: enforce max 5 consecutive failed attempts per email, lock account for 15 minutes, write `USER_LOCKED` AuditLog entry on lockout
    - Reuse existing `failed_login_attempts` and `locked_until` fields on `User`
    - _Requirements: 9.5, 9.6_

- [x] 4. Backend: Agency Member Invitation API
  - [x] 4.1 Implement `POST /api/v1/agencies/me/invitations/` view (AGENCY_ADMIN only): validate target role is `AGENCY_OFFICER` or `REVIEWER` (403 otherwise), generate 32-byte `os.urandom` token, store SHA-256 hash, set `expires_at = now + 72h`, enqueue `send_invitation_email` task, write `INVITATION_CREATED` AuditLog entry
    - _Requirements: 4.1, 4.2, 4.6, 4.9_
  - [x] 4.2 Implement `GET /api/v1/agencies/me/invitations/accept/` view (public): look up invitation by token hash, return 410 if expired or consumed, return invitation details (email, role, agency name) for form pre-fill
    - _Requirements: 4.3, 4.5_
  - [x] 4.3 Implement `POST /api/v1/agencies/me/invitations/accept/` view (public): validate token, create `User` with invitation's role and agency, mark `Invitation.consumed_at = now`, write `INVITATION_ACCEPTED` AuditLog entry
    - _Requirements: 4.4, 4.9_
  - [x] 4.4 Create Celery task `send_invitation_email` in `agencies/tasks.py`: send invitation email with token link; retry up to 3 times on failure
    - _Requirements: 4.2_
  - [x] 4.5 Implement `GET /api/v1/agencies/me/members/` view (AGENCY_ADMIN only): return list of active members scoped to the admin's agency, including name, email, role, last login timestamp
    - _Requirements: 11.4_
  - [x] 4.6 Implement `PATCH /api/v1/agencies/me/members/<id>/deactivate/` view (AGENCY_ADMIN only): enforce same-agency constraint (403 if different agency), set `User.is_active=False`, blacklist all active JWT refresh tokens for that user, write `MEMBER_DEACTIVATED` AuditLog entry
    - _Requirements: 4.7, 4.8, 4.9_

- [x] 5. Backend: Agency Profile API
  - [x] 5.1 Implement `GET /api/v1/agencies/me/` view (all agency roles): return agency profile including `legal_name`, `gstin`, `ministry`, `contact_name`, `contact_email`, `status`, `created_at`
    - _Requirements: 11.1, 11.5_
  - [x] 5.2 Implement `PATCH /api/v1/agencies/me/` view (AGENCY_ADMIN only): allow updating `contact_name`, `contact_email`, `ministry`; reject GSTIN updates with HTTP 400; write `AGENCY_STATUS_CHANGED` AuditLog entry with field diffs (previous and new values for each changed field)
    - _Requirements: 11.1, 11.2, 11.3_

- [-] 6. Backend: Tender Submission API
  - [x] 6.1 Implement `GET /api/v1/agencies/me/tenders/` view (all agency roles): return paginated `TenderSubmission` list scoped to user's agency via `AgencyScopedManager.for_agency()`; support filters: `status`, `category`, `date_range`; support sort: `created_at` (default desc), `estimated_value`, `fraud_risk_score`; include fraud score and risk badge data in response
    - _Requirements: 5.1, 5.3, 5.6, 5.7, 8.2_
  - [x] 6.2 Implement `POST /api/v1/agencies/me/tenders/` view (AGENCY_ADMIN, AGENCY_OFFICER): validate all required fields present, validate `estimated_value` is positive decimal with ≤ 2 decimal places, validate `submission_deadline` is in the future, sanitise `title`/`spec_text`/`buyer_name` with `bleach_clean()`, create `TenderSubmission` with status `DRAFT` linked to user's agency, write `TENDER_SUBMITTED` AuditLog entry
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.11, 6.12_
  - [x] 6.3 Implement `GET /api/v1/agencies/me/tenders/<id>/` view (all agency roles): return tender detail with fraud score, red flag summary, and status; enforce agency scoping via `AgencyObjectPermission`
    - _Requirements: 5.3, 5.4, 8.2_
  - [x] 6.4 Implement `PATCH /api/v1/agencies/me/tenders/<id>/` view (AGENCY_ADMIN, AGENCY_OFFICER): enforce `DRAFT`-only editing (403 otherwise); enforce Agency_Officer can only edit their own tenders; sanitise text inputs; write AuditLog entry
    - _Requirements: 6.8, 6.9, 6.10, 6.11, 6.12_
  - [x] 6.5 Implement `DELETE /api/v1/agencies/me/tenders/<id>/` view (AGENCY_ADMIN, AGENCY_OFFICER): enforce `DRAFT`-only deletion (403 otherwise); enforce Agency_Officer can only delete their own tenders; write AuditLog entry
    - _Requirements: 6.8, 6.9, 6.10, 6.12_
  - [x] 6.6 Implement `POST /api/v1/agencies/me/tenders/<id>/submit/` view (AGENCY_ADMIN, AGENCY_OFFICER): call `submission.transition_to(SUBMITTED)`, create corresponding `tenders.Tender` record and link via `TenderSubmission.tender`, enqueue `score_agency_tender` Celery task within 5 seconds, write AuditLog entry
    - _Requirements: 6.5, 6.12, 10.1_
  - [x] 6.7 Implement `GET /api/v1/agencies/tenders/` view (GOVERNMENT_AUDITOR, ADMIN): return all `TenderSubmission` records across all agencies without agency scoping; include `agency_name` and `agency_id` in each record; write `GOV_AUDITOR_ACCESS` AuditLog entry per request
    - _Requirements: 12.1, 12.3, 12.5, 12.6_
  - [x] 6.8 Implement `PATCH /api/v1/agencies/tenders/<id>/clear/` view (GOVERNMENT_AUDITOR, ADMIN): call `submission.transition_to(CLEARED)`; require `review_note` of ≥ 10 characters (400 otherwise); write `TENDER_CLEARED` AuditLog entry with reviewer user ID and note
    - _Requirements: 7.5, 12.2_

- [x] 7. Backend: Fraud Detection Pipeline Integration
  - [x] 7.1 Create `score_agency_tender` Celery task in `agencies/tasks.py`: call existing `score_tender` pipeline on the linked `Tender` record, then update `TenderSubmission` status based on score (≥ 70 → `UNDER_REVIEW` via `transition_to`, < 40 → `CLEARED` via `transition_to`), create `Alert` records for all `AGENCY_ADMIN` and `AGENCY_OFFICER` users of the submitting agency if score ≥ 70, write AuditLog entry
    - _Requirements: 10.2, 10.3, 10.4, 10.5, 10.6_
  - [x] 7.2 Handle `score_agency_tender` permanent failure (after 3 retries with exponential backoff): keep `TenderSubmission.status` as `SUBMITTED`, create internal `Alert` for all `ADMIN` users with `alert_type=SCORING_FAILURE`, write AuditLog entry with error details
    - _Requirements: 10.7_
  - [x] 7.3 Add `UNDER_REVIEW → FLAGGED` transition trigger: when `RedFlag` records are created for a `TenderSubmission`, call `transition_to(FLAGGED)` and dispatch email to Agency_Admin within 5 minutes via a Celery task; write AuditLog entry
    - _Requirements: 7.4_
  - [x] 7.4 Verify existing `Tender` model and pipeline are unaffected by the new `TenderSubmission` wrapper
    - Confirmed: `TenderSubmission.tender` is a nullable `OneToOneField`; the pipeline operates on `tenders.Tender` directly
    - _Requirements: 10.8_

- [x] 8. Backend: JWT Token Lifetime Configuration
  - [x] 8.1 Update `SIMPLE_JWT` settings: set `ACCESS_TOKEN_LIFETIME` to 15 minutes and `REFRESH_TOKEN_LIFETIME` to 24 hours; make configurable via env vars `AGENCY_JWT_ACCESS_LIFETIME` and `AGENCY_JWT_REFRESH_LIFETIME`
    - _Requirements: 9.8_

- [x] 9. Backend: URL Routing
  - [x] 9.1 Create `agencies/urls.py` with all agency API routes
    - Fully implemented in `backend/agencies/urls.py`
    - _Requirements: all API endpoints_
  - [x] 9.2 Register `agencies/urls.py` under `api/v1/agencies/` in `config/urls.py`
    - _Requirements: all API endpoints_

- [x] 10. Backend: Property-Based and Unit Tests
  - [x] 10.1 Write Hypothesis property test for Property 1 (agency-scoped queryset never leaks cross-agency data): generate random multi-agency submission datasets, verify `for_agency()` returns only own-agency records
    - Implemented in `backend/agencies/tests/test_properties.py`
    - _Requirements: 8.1, 8.2, 3.2_
  - [x] 10.2 Write Hypothesis property test for Property 2 (RBAC permission denial is exhaustive): generate random (role, action) pairs not in the permission matrix, verify `has_permission()` returns False
    - Implemented in `backend/agencies/tests/test_properties.py`
    - _Requirements: 3.1, 3.2, 3.3, 3.6, 3.7, 3.8_
  - [x] 10.3 Write Hypothesis property test for Property 3 (status machine admits only valid transitions): generate random (current_status, target_status) pairs, verify `transition_to()` raises ValueError for invalid transitions and succeeds for valid ones
    - Implemented in `backend/agencies/tests/test_properties.py`
    - _Requirements: 7.1, 7.2_
  - [x] 10.4 Write Hypothesis property test for Property 4 (invitation token round-trip): generate random 32-byte tokens, verify SHA-256 hash lookup returns correct invitation
    - Implemented in `backend/agencies/tests/test_properties.py`
    - _Requirements: 4.1, 4.3, 4.4, 4.5_
  - [x] 10.5 Write Hypothesis property test for Property 5 (GSTIN validation): generate random strings from GSTIN alphabet and random invalid strings, verify validator accepts/rejects correctly
    - Implemented in `backend/agencies/tests/test_properties.py`
    - _Requirements: 2.7_
  - [x] 10.6 Write Hypothesis property test for Property 6 (suspended agency blocks all authentication): generate random users with suspended agencies, verify `AgencyAwareJWTAuthentication.get_user()` raises `AuthenticationFailed`
    - Implemented in `backend/agencies/tests/test_properties.py`
    - _Requirements: 2.5, 9.7_
  - [x] 10.7 Write Hypothesis property test for Property 7 (bleach sanitisation is idempotent on clean input): generate random strings without HTML special characters, verify `bleach_clean(s) == s`
    - Implemented in `backend/agencies/tests/test_properties.py`
    - _Requirements: 6.11_
  - [x] 10.8 Write unit tests for GSTIN validator with valid and invalid format examples
    - Test at least 5 valid GSTINs and 5 invalid strings (wrong length, lowercase, missing Z, etc.)
    - _Requirements: 2.7_
  - [x] 10.9 Write unit tests for `TenderSubmission.transition_to()` covering all valid transitions and all invalid transitions
    - _Requirements: 7.1, 7.2_
  - [x] 10.10 Write unit tests for `Invitation.is_valid` with expired and consumed invitations
    - _Requirements: 4.5_
  - [x] 10.11 Write integration tests for agency registration → email verification → login flow
    - _Requirements: 1.4–1.9, 2.1–2.3, 9.1–9.3_
  - [x] 10.12 Write integration tests for invitation send → accept → new user created with correct role and agency
    - _Requirements: 4.1–4.4_
  - [x] 10.13 Write integration tests for cross-agency access attempt returning HTTP 403
    - _Requirements: 3.6, 8.2_
  - [x] 10.14 Write integration tests for Government Auditor cross-agency read and write-block behaviour
    - _Requirements: 12.1, 12.2, 12.3, 12.4_

- [x] 11. Backend: Checkpoint — Ensure all backend tests pass
  - Run `pytest backend/agencies/tests/` and confirm all property-based and unit tests pass; ask the user if questions arise.

- [x] 12. Frontend: Auth Context and API Client Extension
  - [x] 12.1 Extend `UserRole` type in `AuthContext.tsx` to include `AGENCY_ADMIN`, `AGENCY_OFFICER`, `REVIEWER`, `GOVERNMENT_AUDITOR`
    - _Requirements: 3.1_
  - [x] 12.2 Add `agencyId: string | null` to `AuthState` interface; persist and rehydrate from `localStorage`
    - _Requirements: 9.2_
  - [x] 12.3 Update `login()` in `AuthContext.tsx` to extract and store `agency_id` and `role` from JWT response payload
    - _Requirements: 9.2, 9.3_
  - [x] 12.4 Create `frontend/services/agencies.ts` with typed API functions for all agency endpoints (register, verify-email, invitations, profile, members, tenders, cross-agency tenders)
    - _Requirements: all frontend-facing API endpoints_

- [x] 13. Frontend: Public Landing Page
  - [x] 13.1 Replace `frontend/app/page.tsx` redirect with a full `LandingPage` component
    - _Requirements: 1.1_
  - [x] 13.2 Implement `LandingPage` with TenderShield value propositions (fraud detection, rule engine, ML scoring, audit trail) and a prominent CTA button navigating to `/agency/register`
    - _Requirements: 1.2, 1.3_
  - [x] 13.3 Ensure landing page is responsive down to 320px viewport width
    - _Requirements: 1.10_

- [x] 14. Frontend: Agency Registration and Onboarding
  - [x] 14.1 Create `frontend/app/agency/register/page.tsx` with `AgencyRegistrationForm` collecting: legal name, GSTIN, ministry, contact name, official email, password
    - _Requirements: 1.4_
  - [x] 14.2 Implement client-side GSTIN format validation in the registration form
    - _Requirements: 1.4, 2.7_
  - [x] 14.3 Display field-level validation errors for missing required fields
    - _Requirements: 1.7_
  - [x] 14.4 Display server-side errors for duplicate GSTIN and duplicate email
    - _Requirements: 1.5, 1.6_
  - [x] 14.5 Create `frontend/app/agency/verify-email/page.tsx` that reads the token from the URL query param and calls the verification endpoint; show success/error state
    - _Requirements: 1.9_
  - [x] 14.6 Create `frontend/app/agency/invite/[token]/page.tsx` for invitation acceptance with pre-filled email and role display; show 410 error for expired/consumed tokens
    - _Requirements: 4.3, 4.5_

- [x] 15. Frontend: Agency Dashboard
  - [x] 15.1 Create `frontend/app/agency/dashboard/page.tsx` with route guard (redirect to `/login` if not authenticated with an agency role)
    - _Requirements: 5.1_
  - [x] 15.2 Implement KPI cards: total submissions, high-risk count (score ≥ 70), active alerts count, under-review count
    - _Requirements: 5.2_
  - [x] 15.3 Implement paginated tender list with columns: tender ID, title, category, estimated value (INR), status, fraud risk score, submission date
    - _Requirements: 5.3_
  - [x] 15.4 Create `RiskBadge` component: green for score < 40, amber for 40–69, red for ≥ 70
    - _Requirements: 5.4_
  - [x] 15.5 Implement filter controls: status dropdown, category dropdown, date range picker
    - _Requirements: 5.6_
  - [x] 15.6 Implement sort controls: submission date (default descending), estimated value, fraud risk score
    - _Requirements: 5.7_
  - [x] 15.7 Hide "Create Tender" action button for `REVIEWER` role
    - _Requirements: 5.8_
  - [x] 15.8 Implement alert notification display for Agency_Admin and Agency_Officer users: poll the alerts endpoint every 30 seconds and show new alerts within 60 seconds of them being raised
    - _Requirements: 5.5_

- [x] 16. Frontend: Tender Submission Form
  - [x] 16.1 Create `frontend/app/agency/tenders/new/page.tsx` with `TenderSubmissionForm`
    - _Requirements: 6.1_
  - [x] 16.2 Implement all form fields: tender reference number, title, category (predefined GeM/CPPP list), estimated value (INR), submission deadline, publication date, buyer department name, spec text (up to 100,000 characters with character counter)
    - _Requirements: 6.1_
  - [x] 16.3 Implement client-side validation: required fields present, estimated value is positive decimal, submission deadline is in the future
    - _Requirements: 6.3, 6.4_
  - [x] 16.4 Implement "Save as Draft" and "Submit" actions; show loading state during submission
    - _Requirements: 6.2, 6.5_
  - [x] 16.5 Create `frontend/app/agency/tenders/[id]/page.tsx` for tender detail view: display fraud score, `RiskBadge`, red flag summary, and current status
    - _Requirements: 5.3, 5.4_

- [x] 17. Frontend: Agency Profile Management
  - [x] 17.1 Create `frontend/app/agency/profile/page.tsx` with agency profile view showing all profile fields and current status
    - _Requirements: 11.1, 11.5_
  - [x] 17.2 Implement editable fields for Agency_Admin: contact name, contact email, ministry; show save confirmation on success
    - _Requirements: 11.1_
  - [x] 17.3 Display GSTIN as read-only with a tooltip explaining it cannot be changed after registration
    - _Requirements: 11.2_
  - [x] 17.4 Display agency status with a prominent suspension banner (including support contact email) when status is `SUSPENDED`
    - _Requirements: 11.6_
  - [x] 17.5 Implement member list table with columns: name, email, role, last login; include "Deactivate" action button for Agency_Admin (hidden for other roles)
    - _Requirements: 11.4_
  - [x] 17.6 Implement `InviteMemberModal` for Agency_Admin: email input, role selector (AGENCY_OFFICER or REVIEWER only), submit sends invitation
    - _Requirements: 4.1, 4.6_

- [x] 18. Frontend: Government Auditor Cross-Agency View
  - [x] 18.1 Create `frontend/app/agency/tenders/page.tsx` for GOVERNMENT_AUDITOR cross-agency tender list: reuse the dashboard tender list component with an additional `Agency Name` / `Agency ID` column
    - _Requirements: 12.1, 12.5_
  - [x] 18.2 Ensure all write actions (create, edit, delete, submit, clear) are hidden or disabled for `GOVERNMENT_AUDITOR` role; SHAP explanation link must not be rendered
    - _Requirements: 12.2, 12.4_

- [x] 19. Frontend: Tests
  - [x] 19.1 Write Jest unit tests for `RiskBadge` component: verify correct colour class for scores < 40, 40–69, ≥ 70
    - _Requirements: 5.4_
  - [x] 19.2 Write Jest unit tests for `AgencyRegistrationForm`: verify field-level errors for missing required fields and duplicate GSTIN/email server errors
    - _Requirements: 1.5, 1.6, 1.7_
  - [x] 19.3 Write Jest unit tests for `TenderSubmissionForm`: verify past deadline rejection and character limit enforcement on spec text
    - _Requirements: 6.3, 6.4_
  - [x] 19.4 Write Jest unit tests for `AgencyDashboard` filter and sort logic
    - _Requirements: 5.6, 5.7_

- [x] 20. Final Checkpoint — Ensure all tests pass
  - Run full test suite (`pytest backend/` and `jest frontend/`); confirm all property-based, unit, and integration tests pass; ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP
- Each task references specific requirements for traceability
- Checkpoints (tasks 11 and 20) ensure incremental validation
- Property tests (10.1–10.7) validate universal correctness properties from the design document
- Unit and integration tests validate specific examples and edge cases
- The `agencies` app is intentionally isolated — existing apps (`tenders`, `authentication`, `audit`, etc.) are modified only where strictly necessary (UserRole extension, EventType extension, User model FK)
