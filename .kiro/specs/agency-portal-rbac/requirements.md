# Requirements Document

## Introduction

This feature introduces an agency-facing portal for TenderShield — a government procurement fraud detection platform targeting Indian public tenders (GeM/CPPP). The portal enables procurement agencies to register, onboard, and submit tenders directly into TenderShield's fraud detection pipeline. It introduces multi-tenancy at the agency level (the existing system is single-tenant) and a Role-Based Access Control (RBAC) system with four roles: Agency Admin, Agency Officer, Reviewer, and Government Auditor.

The portal consists of:
1. A public landing page where agencies can learn about TenderShield and sign up.
2. An authenticated agency dashboard where agency users manage their tender submissions.
3. An RBAC layer that scopes all data access and actions to the user's agency and role.
4. Integration with the existing fraud detection pipeline (rule engine + ML scoring + alerts).

The existing system has two internal roles (AUDITOR, ADMIN). This feature extends the `User` model and introduces an `Agency` multi-tenancy boundary without breaking existing functionality.

---

## Glossary

- **Agency**: A government procurement body (e.g., NHAI, MCD, AIIMS) that registers on TenderShield to submit and monitor tenders.
- **Agency_Admin**: A user role with full administrative control over a single agency's account, members, and tender submissions.
- **Agency_Officer**: A user role that can create and submit tenders on behalf of an agency.
- **Reviewer**: A user role within an agency that can view tender submissions and fraud scores but cannot create or modify tenders.
- **Government_Auditor**: A cross-agency read-only role assigned by TenderShield administrators, with visibility into all agencies' submissions and fraud scores.
- **Portal**: The agency-facing web application built on the existing Next.js frontend.
- **Fraud_Detection_Pipeline**: The existing TenderShield backend pipeline comprising the rule engine, ML scoring (Isolation Forest + Random Forest), SHAP explanations, and alert dispatch.
- **Tender_Submission**: A tender record created by an Agency_Officer or Agency_Admin through the Portal and submitted into the Fraud_Detection_Pipeline.
- **Invitation**: A time-limited, single-use token sent by an Agency_Admin to invite a new user to join the agency.
- **JWT**: JSON Web Token used for stateless authentication, issued by the existing SimpleJWT-based auth system.
- **RBAC**: Role-Based Access Control — the permission model governing what each role can see and do.
- **Tenant**: An Agency instance; all data belonging to an agency is scoped to that tenant.
- **Landing_Page**: The public-facing marketing page at the root URL where agencies can learn about TenderShield and initiate registration.
- **GeM**: Government e-Marketplace — India's national public procurement portal.
- **CPPP**: Central Public Procurement Portal — India's central tender publication system.
- **AuditLog**: The existing immutable audit log that records all system actions with actor, timestamp, and IP address.

---

## Requirements

### Requirement 1: Public Landing Page

**User Story:** As a procurement agency representative, I want to visit a public landing page, so that I can understand TenderShield's capabilities and initiate agency registration.

#### Acceptance Criteria

1. THE Landing_Page SHALL be accessible at the root URL (`/`) without authentication.
2. THE Landing_Page SHALL display TenderShield's key value propositions: fraud detection, rule engine, ML scoring, and audit trail.
3. THE Landing_Page SHALL include a prominent call-to-action that navigates to the agency registration form.
4. WHEN a visitor submits the registration form, THE Portal SHALL collect the agency's legal name, GSTIN, ministry or department affiliation, primary contact name, official email address, and a password for the Agency_Admin account.
5. WHEN a visitor submits the registration form with a GSTIN that is already registered, THE Portal SHALL display an error message indicating the agency is already registered.
6. WHEN a visitor submits the registration form with an email address that is already in use, THE Portal SHALL display an error message indicating the email is already associated with an account.
7. IF the registration form is submitted with any required field missing, THEN THE Portal SHALL display a field-level validation error identifying each missing field.
8. WHEN a visitor successfully submits the registration form, THE Portal SHALL create an Agency record with status `PENDING_APPROVAL` and send a verification email to the provided official email address.
9. WHEN a visitor clicks the verification link in the email, THE Portal SHALL mark the Agency_Admin account as email-verified and set the agency status to `ACTIVE`.
10. THE Landing_Page SHALL be fully accessible on mobile viewports with a minimum width of 320px.

---

### Requirement 2: Agency Registration and Onboarding

**User Story:** As a TenderShield administrator, I want to review and approve agency registrations, so that only legitimate government procurement bodies gain access to the platform.

#### Acceptance Criteria

1. WHEN an agency registration is submitted, THE System SHALL create an `Agency` record with fields: `agency_id`, `legal_name`, `gstin`, `ministry`, `contact_name`, `contact_email`, `status` (`PENDING_APPROVAL` | `ACTIVE` | `SUSPENDED`), `created_at`, and `approved_at`.
2. WHEN an agency registration is submitted, THE System SHALL create a `User` record for the Agency_Admin with role `AGENCY_ADMIN`, linked to the new agency, and with `is_active = False` until email verification completes.
3. WHEN an Agency_Admin's email is verified, THE System SHALL set `User.is_active = True` and `Agency.status = ACTIVE`.
4. THE System SHALL enforce that each `Agency` record has exactly one Agency_Admin at all times.
5. WHEN an agency's `status` is `SUSPENDED`, THE System SHALL reject all authentication attempts by users belonging to that agency with HTTP 403 and a message indicating the account is suspended.
6. THE System SHALL record every agency status change in the AuditLog with the actor's user ID, timestamp, previous status, and new status.
7. WHEN a GSTIN is provided during registration, THE System SHALL validate that it conforms to the 15-character Indian GSTIN format (`[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}`).

---

### Requirement 3: Role-Based Access Control (RBAC)

**User Story:** As a TenderShield system designer, I want a well-defined RBAC model, so that each user can only access data and perform actions appropriate to their role and agency.

#### Acceptance Criteria

1. THE System SHALL support the following roles: `AGENCY_ADMIN`, `AGENCY_OFFICER`, `REVIEWER`, `GOVERNMENT_AUDITOR`, `AUDITOR` (existing), and `ADMIN` (existing).
2. THE System SHALL enforce that `AGENCY_ADMIN`, `AGENCY_OFFICER`, and `REVIEWER` roles are always scoped to exactly one Agency tenant; a user with these roles SHALL NOT access data belonging to a different agency.
3. THE System SHALL enforce that `GOVERNMENT_AUDITOR` users have read-only access to tender submissions and fraud scores across all agencies, with no ability to create, modify, or delete records.
4. THE System SHALL enforce that `ADMIN` users retain full access to all system resources, including agency management and user management.
5. THE System SHALL enforce that `AUDITOR` users retain their existing access to the internal fraud detection dashboard, with no access to agency management endpoints.
6. WHEN a user attempts to access a resource belonging to a different agency, THE System SHALL return HTTP 403.
7. WHEN a user attempts to perform an action not permitted by their role, THE System SHALL return HTTP 403.
8. THE System SHALL enforce role permissions at the API layer, not only at the UI layer.
9. THE System SHALL record every permission denial in the AuditLog with the user ID, attempted action, resource identifier, and timestamp.

#### Role Permission Matrix

| Action | AGENCY_ADMIN | AGENCY_OFFICER | REVIEWER | GOVERNMENT_AUDITOR | AUDITOR | ADMIN |
|---|---|---|---|---|---|---|
| View own agency's tenders | ✓ | ✓ | ✓ | ✓ | — | ✓ |
| Create tender submission | ✓ | ✓ | — | — | — | ✓ |
| Edit draft tender | ✓ | ✓ (own) | — | — | — | ✓ |
| Submit tender to pipeline | ✓ | ✓ (own) | — | — | — | ✓ |
| View fraud score & flags | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| View SHAP explanation | — | — | — | ✓ | ✓ | ✓ |
| Invite agency members | ✓ | — | — | — | — | ✓ |
| Manage agency profile | ✓ | — | — | — | — | ✓ |
| View all agencies | — | — | — | ✓ | — | ✓ |
| Suspend/approve agency | — | — | — | — | — | ✓ |

---

### Requirement 4: Agency Member Invitation and User Management

**User Story:** As an Agency_Admin, I want to invite colleagues to join my agency's account, so that my team can collaborate on tender submissions.

#### Acceptance Criteria

1. WHEN an Agency_Admin sends an invitation, THE System SHALL create an `Invitation` record with a cryptographically random 32-byte token, the invitee's email address, the target role (`AGENCY_OFFICER` or `REVIEWER`), the inviting agency's ID, and an expiry timestamp 72 hours from creation.
2. WHEN an invitation is created, THE System SHALL send an invitation email to the invitee's email address containing the invitation link with the token.
3. WHEN an invitee clicks the invitation link and the token is valid and unexpired, THE Portal SHALL present a registration form pre-filled with the invitee's email address.
4. WHEN an invitee completes registration via a valid invitation, THE System SHALL create a `User` record linked to the inviting agency with the role specified in the invitation, and mark the invitation as consumed.
5. WHEN an invitee attempts to use an expired or already-consumed invitation token, THE System SHALL return HTTP 410 and display an error message.
6. THE System SHALL enforce that an Agency_Admin can only invite users to roles `AGENCY_OFFICER` or `REVIEWER`; attempts to invite to `AGENCY_ADMIN` or `GOVERNMENT_AUDITOR` SHALL return HTTP 403.
7. WHEN an Agency_Admin deactivates a team member, THE System SHALL set `User.is_active = False` for that user and invalidate all active JWT refresh tokens for that user.
8. THE System SHALL enforce that an Agency_Admin can only deactivate users belonging to their own agency.
9. THE System SHALL record every invitation creation, acceptance, and user deactivation in the AuditLog.

---

### Requirement 5: Agency Dashboard

**User Story:** As an authenticated agency user, I want a dashboard showing my agency's tender submissions and their fraud detection status, so that I can monitor procurement activity and respond to alerts.

#### Acceptance Criteria

1. WHEN an authenticated agency user accesses the dashboard, THE Portal SHALL display only tender submissions belonging to the user's agency.
2. THE Dashboard SHALL display the following KPIs for the authenticated user's agency: total tender submissions, count of submissions with fraud score ≥ 70 (high risk), count of active alerts, and count of submissions currently under review.
3. THE Dashboard SHALL display a paginated list of the agency's tender submissions, each showing: tender ID, title, category, estimated value (INR), submission status, fraud risk score (if computed), and submission date.
4. WHEN a fraud risk score is available for a tender, THE Dashboard SHALL display a colour-coded risk badge: green for score < 40, amber for score 40–69, red for score ≥ 70.
5. WHEN the Fraud_Detection_Pipeline raises a red flag on an agency's tender, THE Dashboard SHALL display an alert notification to Agency_Admin and Agency_Officer users of that agency within 60 seconds of the flag being raised.
6. THE Dashboard SHALL support filtering tender submissions by status (`DRAFT` | `SUBMITTED` | `UNDER_REVIEW` | `FLAGGED` | `CLEARED`), category, and date range.
7. THE Dashboard SHALL support sorting tender submissions by submission date (descending by default), estimated value, and fraud risk score.
8. WHEN a Reviewer accesses the dashboard, THE Dashboard SHALL display the same tender list but SHALL NOT display the "Create Tender" action button.

---

### Requirement 6: Tender Submission

**User Story:** As an Agency_Officer or Agency_Admin, I want to create and submit tender records through the portal, so that they are analysed by TenderShield's fraud detection pipeline.

#### Acceptance Criteria

1. THE Tender_Submission form SHALL collect the following fields: tender reference number, title, category (from a predefined list aligned with GeM/CPPP categories), estimated value (INR), submission deadline, publication date, buyer department name, and tender specification text (up to 100,000 characters).
2. WHEN a tender is saved without submission, THE System SHALL store it with status `DRAFT` and associate it with the submitting user's agency.
3. WHEN an Agency_Officer submits a tender, THE System SHALL validate that all required fields are present and that the estimated value is a positive decimal number with at most two decimal places.
4. IF the submission deadline is in the past at the time of submission, THEN THE System SHALL reject the submission and return a validation error.
5. WHEN a tender is submitted (status transitions from `DRAFT` to `SUBMITTED`), THE System SHALL enqueue a Celery task to run the Fraud_Detection_Pipeline on the submitted tender.
6. WHEN the Fraud_Detection_Pipeline completes scoring, THE System SHALL update the tender's fraud risk score and set the tender status to `UNDER_REVIEW` if the score is ≥ 70, or `CLEARED` if the score is < 40.
7. WHEN a tender's fraud risk score is ≥ 70, THE System SHALL create an alert and dispatch it to the Agency_Admin and all Agency_Officers of the submitting agency.
8. THE System SHALL enforce that an Agency_Officer can only edit or delete tenders they personally created while in `DRAFT` status.
9. THE System SHALL enforce that an Agency_Admin can edit or delete any tender belonging to their agency while in `DRAFT` status.
10. WHEN a tender has been submitted (status is not `DRAFT`), THE System SHALL reject any edit or delete request with HTTP 403.
11. THE System SHALL sanitise all text inputs (title, spec_text, buyer_name) using the existing bleach sanitisation pipeline before persisting to the database.
12. THE System SHALL record every tender creation, edit, submission, and deletion in the AuditLog with the actor's user ID, agency ID, tender ID, and timestamp.

---

### Requirement 7: Tender Submission Status Lifecycle

**User Story:** As an agency user, I want to understand the current state of each tender submission, so that I can take appropriate action at each stage.

#### Acceptance Criteria

1. THE System SHALL enforce the following tender submission status transitions: `DRAFT → SUBMITTED`, `SUBMITTED → UNDER_REVIEW`, `SUBMITTED → CLEARED`, `UNDER_REVIEW → FLAGGED`, `UNDER_REVIEW → CLEARED`, `FLAGGED → CLEARED` (after manual review by Government_Auditor or Admin).
2. WHEN a status transition is attempted that is not in the permitted set, THE System SHALL return HTTP 400 with a message identifying the invalid transition.
3. THE System SHALL record every status transition in the AuditLog with the actor, previous status, new status, tender ID, and timestamp.
4. WHEN a tender reaches `FLAGGED` status, THE System SHALL notify the Agency_Admin of the submitting agency via email within 5 minutes.
5. WHEN a Government_Auditor or Admin marks a `FLAGGED` tender as `CLEARED`, THE System SHALL record the clearing action in the AuditLog with the reviewer's user ID and a mandatory review note of at least 10 characters.

---

### Requirement 8: Multi-Tenancy Data Isolation

**User Story:** As a TenderShield system designer, I want strict data isolation between agencies, so that one agency cannot access another agency's tender data or user information.

#### Acceptance Criteria

1. THE System SHALL associate every `Tender_Submission` record with exactly one `Agency` via a non-nullable foreign key.
2. THE System SHALL enforce that all API endpoints returning tender data filter results by the authenticated user's `agency_id` for `AGENCY_ADMIN`, `AGENCY_OFFICER`, and `REVIEWER` roles.
3. THE System SHALL enforce that `GOVERNMENT_AUDITOR` users can read tender submissions across all agencies but cannot filter out or modify the `agency_id` association.
4. THE System SHALL enforce that the existing internal `Tender` model (used by the fraud detection pipeline) remains accessible to `AUDITOR` and `ADMIN` roles without agency scoping.
5. WHEN a database query for agency-scoped resources is constructed, THE System SHALL apply the agency filter at the queryset level, not at the serializer or view level, to prevent accidental data leakage.
6. THE System SHALL enforce that user management endpoints (list members, deactivate member) are scoped to the authenticated Agency_Admin's agency.

---

### Requirement 9: Authentication and Session Security

**User Story:** As a security-conscious platform operator, I want agency user authentication to be secure and auditable, so that unauthorised access is prevented and all access events are traceable.

#### Acceptance Criteria

1. THE System SHALL authenticate agency users using the existing JWT-based authentication system (SimpleJWT with AuditingJWTAuthentication).
2. THE System SHALL include the authenticated user's `agency_id` and `role` as claims in the JWT access token payload.
3. WHEN an agency user logs in, THE System SHALL record the login event in the AuditLog with the user ID, agency ID, IP address, and timestamp.
4. WHEN an agency user logs out, THE System SHALL blacklist the refresh token using the existing token blacklist mechanism.
5. THE System SHALL enforce a maximum of 5 consecutive failed login attempts per email address before locking the account for 15 minutes.
6. WHEN an account is locked due to failed login attempts, THE System SHALL record the lockout event in the AuditLog.
7. WHEN a user belonging to a `SUSPENDED` agency attempts to authenticate, THE System SHALL reject the request with HTTP 403 before issuing any token.
8. THE System SHALL enforce that JWT access tokens for agency users expire after 15 minutes and refresh tokens expire after 24 hours.

---

### Requirement 10: Fraud Detection Pipeline Integration

**User Story:** As an Agency_Officer, I want submitted tenders to be automatically analysed by TenderShield's fraud detection engine, so that I receive timely risk assessments without manual intervention.

#### Acceptance Criteria

1. WHEN a tender is submitted through the Portal, THE System SHALL enqueue a `score_tender` Celery task within 5 seconds of the submission being persisted.
2. WHEN the `score_tender` task executes, THE Fraud_Detection_Pipeline SHALL run all six rule-based detectors and the ML scoring models (Isolation Forest + Random Forest) against the submitted tender.
3. WHEN the Fraud_Detection_Pipeline produces a fraud risk score, THE System SHALL persist the score to the `FraudRiskScore` model and associate it with the submitted tender.
4. WHEN the Fraud_Detection_Pipeline raises one or more red flags, THE System SHALL create `RedFlag` records linked to the submitted tender and the submitting agency.
5. WHEN the fraud risk score is ≥ 70, THE System SHALL create an `Alert` record and dispatch it to all Agency_Admin and Agency_Officer users of the submitting agency.
6. THE System SHALL make the fraud risk score and red flag summary available on the agency dashboard within 30 seconds of the `score_tender` task completing.
7. IF the `score_tender` task fails after 3 retry attempts, THEN THE System SHALL set the tender status to `SUBMITTED` (not `UNDER_REVIEW`) and create an internal alert for `ADMIN` users indicating the scoring failure.
8. THE System SHALL preserve the existing fraud detection pipeline behaviour for tenders ingested via the internal API and data ingestion commands; agency-submitted tenders SHALL be processed by the same pipeline without modification.

---

### Requirement 11: Agency Profile Management

**User Story:** As an Agency_Admin, I want to manage my agency's profile information, so that the platform reflects accurate and up-to-date agency details.

#### Acceptance Criteria

1. THE Agency_Admin SHALL be able to update the agency's contact name, contact email, and ministry or department affiliation via the Portal.
2. THE System SHALL enforce that the GSTIN field is immutable after agency registration; attempts to update GSTIN SHALL return HTTP 400.
3. WHEN an Agency_Admin updates the agency profile, THE System SHALL record the change in the AuditLog with the actor's user ID, the fields changed, the previous values, and the new values.
4. THE Agency_Admin SHALL be able to view a list of all active members in their agency, including each member's name, email, role, and last login timestamp.
5. THE System SHALL display the agency's current status (`ACTIVE` | `SUSPENDED`) on the agency profile page.
6. WHEN the agency status is `SUSPENDED`, THE Portal SHALL display a prominent banner on the agency profile page indicating the suspension and providing a contact email for TenderShield support.

---

### Requirement 12: Government Auditor Cross-Agency View

**User Story:** As a Government_Auditor, I want read-only access to tender submissions and fraud scores across all agencies, so that I can perform independent oversight without being restricted to a single agency's view.

#### Acceptance Criteria

1. WHEN a Government_Auditor accesses the tender list endpoint, THE System SHALL return tender submissions from all agencies without agency-scoping.
2. THE System SHALL enforce that Government_Auditor users cannot create, update, or delete any resource; all write operations SHALL return HTTP 403.
3. THE System SHALL enforce that Government_Auditor users can view fraud risk scores and red flag summaries for all tenders.
4. THE System SHALL enforce that Government_Auditor users cannot view SHAP explanations; requests to the explanation endpoint SHALL return HTTP 403.
5. WHEN a Government_Auditor accesses a tender detail page, THE System SHALL display the agency name and agency ID alongside the tender details.
6. THE System SHALL record every Government_Auditor data access event in the AuditLog with the user ID, resource type, resource ID, and timestamp.
