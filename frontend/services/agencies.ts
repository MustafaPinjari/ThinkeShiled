/**
 * frontend/services/agencies.ts
 *
 * Typed API functions for all Agency Portal RBAC endpoints.
 * Uses the shared axios instance from @/lib/api which handles
 * Bearer token injection and 401 → refresh token retry.
 */

import api from "@/lib/api";
import type { UserRole } from "@/contexts/AuthContext";
import type { PaginatedResponse } from "@/types/tender";

// ── Shared enums ──────────────────────────────────────────────────────────────

export type AgencyStatus = "PENDING_APPROVAL" | "ACTIVE" | "SUSPENDED";

export type SubmissionStatus =
  | "DRAFT"
  | "SUBMITTED"
  | "UNDER_REVIEW"
  | "FLAGGED"
  | "CLEARED";

// ── Registration & Auth ───────────────────────────────────────────────────────

export interface RegisterAgencyPayload {
  legal_name: string;
  gstin: string;
  ministry: string;
  contact_name: string;
  contact_email: string;
  password: string;
}

export interface RegisterAgencyResponse {
  agency_id: string;
  legal_name: string;
  status: AgencyStatus;
  message: string;
}

/** POST /api/v1/agencies/register/ */
export async function registerAgency(
  payload: RegisterAgencyPayload
): Promise<RegisterAgencyResponse> {
  const { data } = await api.post<RegisterAgencyResponse>(
    "/agencies/register/",
    payload
  );
  return data;
}

// ── Email Verification ────────────────────────────────────────────────────────

export interface VerifyEmailResponse {
  message: string;
}

/** GET /api/v1/agencies/verify-email/?token=<hex> */
export async function verifyEmail(token: string): Promise<VerifyEmailResponse> {
  const { data } = await api.get<VerifyEmailResponse>(
    "/agencies/verify-email/",
    { params: { token } }
  );
  return data;
}

// ── Login ─────────────────────────────────────────────────────────────────────

export interface LoginPayload {
  username: string;
  password: string;
}

export interface LoginResponse {
  access: string;
  refresh: string;
  expires_in: number;
  role: UserRole;
  agency_id: string | null;
}

/** POST /api/v1/agencies/login/ */
export async function loginAgency(
  email: string,
  password: string
): Promise<LoginResponse> {
  const { data } = await api.post<LoginResponse>("/agencies/login/", {
    username: email,
    password,
  });
  return data;
}

// ── Invitations ───────────────────────────────────────────────────────────────

export type InvitableRole = "AGENCY_OFFICER" | "REVIEWER";

export interface SendInvitationPayload {
  email: string;
  role: InvitableRole;
}

export interface SendInvitationResponse {
  message: string;
  email: string;
  role: InvitableRole;
  expires_at: string;
}

/** POST /api/v1/agencies/me/invitations/ */
export async function sendInvitation(
  email: string,
  role: InvitableRole
): Promise<SendInvitationResponse> {
  const { data } = await api.post<SendInvitationResponse>(
    "/agencies/me/invitations/",
    { email, role }
  );
  return data;
}

export interface InvitationDetails {
  email: string;
  role: InvitableRole;
  agency_name: string;
  expires_at: string;
}

/** GET /api/v1/agencies/me/invitations/accept/?token=<hex> */
export async function getInvitationDetails(
  token: string
): Promise<InvitationDetails> {
  const { data } = await api.get<InvitationDetails>(
    "/agencies/me/invitations/accept/",
    { params: { token } }
  );
  return data;
}

export interface AcceptInvitationPayload {
  token: string;
  password: string;
  username?: string;
}

export interface AcceptInvitationResponse {
  message: string;
  role: InvitableRole;
  agency_id: string;
}

/** POST /api/v1/agencies/me/invitations/accept/ */
export async function acceptInvitation(
  token: string,
  password: string,
  username?: string
): Promise<AcceptInvitationResponse> {
  const payload: AcceptInvitationPayload = { token, password };
  if (username !== undefined) {
    payload.username = username;
  }
  const { data } = await api.post<AcceptInvitationResponse>(
    "/agencies/me/invitations/accept/",
    payload
  );
  return data;
}

// ── Agency Profile ────────────────────────────────────────────────────────────

export interface AgencyProfile {
  agency_id: string;
  legal_name: string;
  gstin: string;
  ministry: string;
  contact_name: string;
  contact_email: string;
  status: AgencyStatus;
  created_at: string;
  approved_at: string | null;
}

/** GET /api/v1/agencies/me/ */
export async function getAgencyProfile(): Promise<AgencyProfile> {
  const { data } = await api.get<AgencyProfile>("/agencies/me/");
  return data;
}

export interface UpdateAgencyProfilePayload {
  contact_name?: string;
  contact_email?: string;
  ministry?: string;
}

/** PATCH /api/v1/agencies/me/ */
export async function updateAgencyProfile(
  payload: UpdateAgencyProfilePayload
): Promise<AgencyProfile> {
  const { data } = await api.patch<AgencyProfile>(
    "/agencies/me/",
    payload
  );
  return data;
}

// ── Members ───────────────────────────────────────────────────────────────────

export interface AgencyMember {
  id: number;
  username: string;
  email: string;
  role: UserRole;
  is_active: boolean;
  last_login: string | null;
}

/** GET /api/v1/agencies/me/members/ */
export async function getMembers(): Promise<AgencyMember[]> {
  const { data } = await api.get<AgencyMember[]>(
    "/agencies/me/members/"
  );
  return data;
}

export interface DeactivateMemberResponse {
  message: string;
}

/** PATCH /api/v1/agencies/me/members/<id>/deactivate/ */
export async function deactivateMember(
  id: number
): Promise<DeactivateMemberResponse> {
  const { data } = await api.patch<DeactivateMemberResponse>(
    `/agencies/me/members/${id}/deactivate/`
  );
  return data;
}

// ── Tender Submissions ────────────────────────────────────────────────────────

export interface TenderSubmission {
  id: number;
  agency: string;
  agency_name?: string;
  submitted_by: number | null;
  tender_ref: string;
  title: string;
  category: string;
  estimated_value: string;
  submission_deadline: string;
  publication_date: string | null;
  buyer_name: string;
  spec_text: string;
  status: SubmissionStatus;
  review_note: string;
  fraud_risk_score: number | null;
  created_at: string;
  updated_at: string;
}

export interface TenderFilters {
  status?: SubmissionStatus;
  category?: string;
  date_from?: string;
  date_to?: string;
  ordering?: "created_at" | "-created_at" | "estimated_value" | "-estimated_value" | "fraud_risk_score" | "-fraud_risk_score";
  page?: number;
  page_size?: number;
}

/** GET /api/v1/agencies/me/tenders/ */
export async function getTenders(
  params?: TenderFilters
): Promise<PaginatedResponse<TenderSubmission>> {
  const { data } = await api.get<PaginatedResponse<TenderSubmission>>(
    "/agencies/me/tenders/",
    { params }
  );
  return data;
}

export interface CreateTenderPayload {
  tender_ref: string;
  title: string;
  category: string;
  estimated_value: string;
  submission_deadline: string;
  publication_date?: string;
  buyer_name: string;
  spec_text?: string;
}

/** POST /api/v1/agencies/me/tenders/ */
export async function createTender(
  payload: CreateTenderPayload
): Promise<TenderSubmission> {
  const { data } = await api.post<TenderSubmission>(
    "/agencies/me/tenders/",
    payload
  );
  return data;
}

/** GET /api/v1/agencies/me/tenders/<id>/ */
export async function getTender(id: number): Promise<TenderSubmission> {
  const { data } = await api.get<TenderSubmission>(
    `/agencies/me/tenders/${id}/`
  );
  return data;
}

export type UpdateTenderPayload = Partial<CreateTenderPayload>;

/** PATCH /api/v1/agencies/me/tenders/<id>/ */
export async function updateTender(
  id: number,
  payload: UpdateTenderPayload
): Promise<TenderSubmission> {
  const { data } = await api.patch<TenderSubmission>(
    `/agencies/me/tenders/${id}/`,
    payload
  );
  return data;
}

/** DELETE /api/v1/agencies/me/tenders/<id>/ */
export async function deleteTender(id: number): Promise<void> {
  await api.delete(`/agencies/me/tenders/${id}/`);
}

export interface SubmitTenderResponse {
  message: string;
  status: SubmissionStatus;
}

/** POST /api/v1/agencies/me/tenders/<id>/submit/ */
export async function submitTender(id: number): Promise<SubmitTenderResponse> {
  const { data } = await api.post<SubmitTenderResponse>(
    `/agencies/me/tenders/${id}/submit/`
  );
  return data;
}

// ── Cross-Agency (Government Auditor / Admin) ─────────────────────────────────

export interface CrossAgencyTenderFilters {
  status?: SubmissionStatus;
  category?: string;
  agency_id?: string;
  date_from?: string;
  date_to?: string;
  ordering?: string;
  page?: number;
  page_size?: number;
}

/** GET /api/v1/agencies/tenders/ — GOVERNMENT_AUDITOR / ADMIN only */
export async function getCrossAgencyTenders(
  params?: CrossAgencyTenderFilters
): Promise<PaginatedResponse<TenderSubmission>> {
  const { data } = await api.get<PaginatedResponse<TenderSubmission>>(
    "/agencies/tenders/",
    { params }
  );
  return data;
}

export interface ClearTenderPayload {
  review_note: string;
}

export interface ClearTenderResponse {
  message: string;
  status: SubmissionStatus;
  review_note: string;
}

/** PATCH /api/v1/agencies/tenders/<id>/clear/ — GOVERNMENT_AUDITOR / ADMIN only */
export async function clearTender(
  id: number,
  reviewNote: string
): Promise<ClearTenderResponse> {
  const { data } = await api.patch<ClearTenderResponse>(
    `/agencies/tenders/${id}/clear/`,
    { review_note: reviewNote } satisfies ClearTenderPayload
  );
  return data;
}
