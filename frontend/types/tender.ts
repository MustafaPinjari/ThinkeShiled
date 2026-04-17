// Shared types for TenderShield frontend

export interface Tender {
  id: number;
  tender_id: string;
  title: string;
  category: string;
  estimated_value: string;
  currency: string;
  submission_deadline: string;
  buyer_id: string;
  buyer_name: string;
  status: string;
  created_at: string;
  updated_at: string;
  // Annotated fields from related models
  fraud_risk_score?: number | null;
  active_red_flag_count?: number;
}

export interface FraudRiskScore {
  id: number;
  tender_id: number;
  score: number;
  ml_anomaly_score: number | null;
  ml_collusion_score: number | null;
  red_flag_contribution: number;
  model_version: string;
  weight_config: Record<string, number>;
  computed_at: string;
}

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface TenderListItem {
  id: number;
  tender_id: string;
  title: string;
  category: string;
  estimated_value: string;
  currency: string;
  submission_deadline: string;
  buyer_id: string;
  buyer_name: string;
  status: string;
  created_at: string;
  /** Annotated from latest FraudRiskScore row */
  latest_score: number | null;
  active_red_flag_count: number;
}

export interface DashboardStats {
  total_tenders: number;
  high_risk_count: number;
  high_flag_count: number;
  collusion_ring_count: number;
}

export interface TenderFilters {
  score_min?: string;
  score_max?: string;
  category?: string;
  buyer_name?: string;
  date_from?: string;
  date_to?: string;
  flag_type?: string;
  ordering?: string;
  page?: number;
  page_size?: number;
}

// ── Tender detail types ───────────────────────────────────────────────────────

export interface TenderDetail {
  id: number;
  tender_id: string;
  title: string;
  category: string;
  estimated_value: string;
  currency: string;
  submission_deadline: string;
  buyer_id: string;
  buyer_name: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface RedFlag {
  id: number;
  flag_type: string;
  severity: "HIGH" | "MEDIUM" | "LOW";
  rule_version: string;
  trigger_data: Record<string, unknown>;
  is_active: boolean;
  raised_at: string;
  cleared_at: string | null;
  /** Rule description text from RuleDefinition */
  rule_description?: string;
}

export interface SHAPFactor {
  feature: string;
  shap_value: number;
  plain_language: string;
}

export interface Explanation {
  tender_id: number;
  model_version: string | null;
  rule_engine_version: string | null;
  shap_values: Record<string, number> | null;
  top_factors: SHAPFactor[];
  shap_failed: boolean;
  red_flags: RedFlag[];
  computed_at: string | null;
}

export interface BidScreen {
  cv_bids: number | null;
  bid_spread_ratio: number | null;
  norm_winning_distance: number | null;
  single_bidder_flag: number | null;
  price_deviation_pct: number | null;
  deadline_days: number | null;
  repeat_winner_rate: number | null;
  bidder_count: number | null;
  winner_bid_rank: number | null;
}

export interface Bid {
  id: number;
  bid_id: string;
  bidder_id: number;
  bidder_name: string;
  bid_amount: string;
  submission_timestamp: string;
  bid_screens?: BidScreen | null;
}
