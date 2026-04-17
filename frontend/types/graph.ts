// Graph-related types for TenderShield frontend

export type EdgeType = "CO_BID" | "SHARED_DIRECTOR" | "SHARED_ADDRESS";

export interface GraphNode {
  id: number;
  label: string;
  risk_status: "LOW" | "MEDIUM" | "HIGH_RISK";
  fraud_score: number;
}

export interface GraphEdge {
  id: number;
  source: number;
  target: number;
  type: EdgeType;
  tender_id: number | null;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface CollusionRing {
  id: number;
  ring_id: string;
  member_bidder_ids: number[];
  member_count: number;
  detected_at: string;
  is_active: boolean;
}
