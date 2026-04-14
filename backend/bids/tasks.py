"""
Celery task stubs for post-bid-ingestion pipeline.

These tasks are enqueued after a bid is ingested and trigger the full
fraud detection pipeline: rule evaluation, risk scoring, ML scoring,
company profile update, and collusion graph update.

Concrete implementations are provided in Phase 5–10 tasks.
"""

from celery import shared_task


@shared_task(name="detection.evaluate_rules_task")
def evaluate_rules_task(tender_id: int) -> None:
    """Evaluate all active fraud detection rules for the given tender."""
    from detection.engine import FraudDetectionEngine
    engine = FraudDetectionEngine()
    engine.evaluate_rules(tender_id)


@shared_task(name="scoring.compute_score_task")
def compute_score_task(tender_id: int) -> None:
    """Compute and persist the fraud risk score for the given tender."""
    from scoring.scorer import RiskScorer
    scorer = RiskScorer()
    scorer.compute_score(tender_id)


@shared_task(name="scoring.score_ml_task")
def score_ml_task(tender_id: int) -> None:
    """Run ML models (Isolation Forest + Random Forest) for the given tender."""
    from celery import current_app
    current_app.send_task("ml_worker.score_tender", args=[tender_id])


@shared_task(name="companies.update_company_profile_task")
def update_company_profile_task(bidder_id: int) -> None:
    """Recompute and persist the company risk profile for the given bidder."""
    from companies.tracker import BehavioralTracker
    tracker = BehavioralTracker()
    tracker.update_profile(bidder_id)


@shared_task(name="graph.update_graph_task")
def update_graph_task(tender_id: int) -> None:
    """Update the collusion graph nodes and edges for the given tender."""
    from graph.collusion_graph import CollusionGraph
    graph = CollusionGraph()
    graph.update_graph(tender_id)
    graph.detect_collusion_rings()
