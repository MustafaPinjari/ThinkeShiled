// Company-related types for TenderShield frontend

export type RiskStatus = "LOW" | "MEDIUM" | "HIGH_RISK";

export interface CompanyProfile {
  id: number;
  bidder_id: string;
  bidder_name: string;
  total_bids: number;
  total_wins: number;
  win_rate: string; // decimal string e.g. "0.6500"
  avg_bid_deviation: string; // decimal string
  active_red_flag_count: number;
  highest_fraud_risk_score: number;
  risk_status: RiskStatus;
  collusion_ring_id: string | null;
  updated_at: string;
}

export interface CompanyTender {
  id: number;
  tender_id: string;
  title: string;
  category: string;
  estimated_value: string;
  currency: string;
  submission_deadline: string;
  status: string;
}

export interface CompanyRedFlag {
  id: number;
  tender_id: string;
  flag_type: string;
  severity: "HIGH" | "MEDIUM" | "LOW";
  rule_version: string;
  trigger_data: Record<string, unknown>;
  is_active: boolean;
  raised_at: string;
  cleared_at: string | null;
}

export interface CompanyFilters {
  risk_status?: RiskStatus | "";
  bidder_name?: string;
  page?: number;
  page_size?: number;
}
