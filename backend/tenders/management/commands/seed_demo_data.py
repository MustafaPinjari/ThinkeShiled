"""
Demo seed data for TenderShield.

Data patterns inspired by:
- OECD (2016) "Preventing Corruption in Public Procurement"
- World Bank (2020) "Fraud and Corruption Awareness Handbook"  
- Transparency International India procurement fraud case studies
- CVC (Central Vigilance Commission) annual reports 2019-2023

All company names, tender IDs, and amounts are fictional.
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
import decimal


class Command(BaseCommand):
    help = "Seed demo procurement data for TenderShield"

    def handle(self, *args, **options):
        from bids.models import Bidder, Bid
        from tenders.models import Tender, TenderStatus
        from detection.models import RedFlag, FlagType, Severity
        from scoring.models import FraudRiskScore
        from companies.models import CompanyProfile, RiskStatus

        if Tender.objects.exists():
            self.stdout.write(self.style.WARNING("Demo data already exists. Skipping."))
            return

        self.stdout.write("Seeding demo data...")

        now = timezone.now()

        # ── Bidders ──────────────────────────────────────────────────────────
        # Inspired by real patterns: shell companies with similar addresses,
        # shared directors — common in Indian public procurement fraud cases
        # (Source: CVC Annual Report 2022, Chapter 4)

        b1 = Bidder.objects.create(
            bidder_id="BID-IN-2024-001",
            bidder_name="Apex Infrastructure Pvt Ltd",
            registered_address="Plot 47, Sector 18, Gurugram, Haryana 122015",
            director_names="Rajesh Kumar Sharma, Priya Mehta",
        )
        b2 = Bidder.objects.create(
            bidder_id="BID-IN-2024-002",
            bidder_name="Pinnacle Constructions Ltd",
            registered_address="Plot 47, Sector 18, Gurugram, Haryana 122015",  # same address — LINKED_ENTITIES flag
            director_names="Rajesh Kumar Sharma, Vikram Singh",  # shared director
        )
        b3 = Bidder.objects.create(
            bidder_id="BID-IN-2024-003",
            bidder_name="TechServe Solutions Pvt Ltd",
            registered_address="Tower B, Cyber City, Hyderabad 500081",
            director_names="Anita Desai, Suresh Patel",
        )
        b4 = Bidder.objects.create(
            bidder_id="BID-IN-2024-004",
            bidder_name="MedEquip Suppliers Ltd",
            registered_address="23 Industrial Area, Pune 411019",
            director_names="Kavitha Nair, Mohan Reddy",
        )
        b5 = Bidder.objects.create(
            bidder_id="BID-IN-2024-005",
            bidder_name="RoadBuild Engineering Co",
            registered_address="NH-8 Service Road, Jaipur 302001",
            director_names="Deepak Agarwal, Sunita Joshi",
        )

        # ── Tenders ──────────────────────────────────────────────────────────
        # Based on real Indian government tender categories and value ranges
        # (Source: GeM portal statistics 2023, CPPP tender database)

        t1 = Tender.objects.create(
            tender_id="NHAI-2024-CON-0891",
            title="Construction of 4-Lane Highway NH-48 Bypass — Km 142 to Km 167",
            category="Roads & Highways",
            estimated_value=decimal.Decimal("485000000.00"),
            currency="INR",
            submission_deadline=now - timedelta(days=45),
            publication_date=now - timedelta(days=47),  # only 2 days — SHORT_DEADLINE
            buyer_id="NHAI-ZONE-4",
            buyer_name="National Highways Authority of India",
            status=TenderStatus.AWARDED,
        )
        t2 = Tender.objects.create(
            tender_id="MCD-2024-IT-0234",
            title="Supply and Implementation of Integrated Smart City Management System",
            category="IT Services",
            estimated_value=decimal.Decimal("120000000.00"),
            currency="INR",
            submission_deadline=now - timedelta(days=20),
            publication_date=now - timedelta(days=50),
            buyer_id="MCD-IT-DEPT",
            buyer_name="Municipal Corporation of Delhi",
            status=TenderStatus.AWARDED,
        )
        t3 = Tender.objects.create(
            tender_id="AIIMS-2024-MED-0567",
            title="Procurement of ICU Ventilators and Critical Care Equipment — 200 Units",
            category="Healthcare Equipment",
            estimated_value=decimal.Decimal("95000000.00"),
            currency="INR",
            submission_deadline=now - timedelta(days=10),
            publication_date=now - timedelta(days=40),
            buyer_id="AIIMS-PROC",
            buyer_name="All India Institute of Medical Sciences",
            status=TenderStatus.ACTIVE,
        )
        t4 = Tender.objects.create(
            tender_id="PWD-2024-CON-1102",
            title="Renovation and Waterproofing of Government Secretariat Complex",
            category="Construction",
            estimated_value=decimal.Decimal("28000000.00"),
            currency="INR",
            submission_deadline=now + timedelta(days=5),
            publication_date=now - timedelta(days=2),  # SHORT_DEADLINE
            buyer_id="PWD-DELHI",
            buyer_name="Public Works Department Delhi",
            status=TenderStatus.ACTIVE,
        )
        t5 = Tender.objects.create(
            tender_id="BSNL-2024-IT-0089",
            title="Annual Maintenance Contract for Network Infrastructure — 500 Sites",
            category="IT Services",
            estimated_value=decimal.Decimal("67000000.00"),
            currency="INR",
            submission_deadline=now - timedelta(days=60),
            publication_date=now - timedelta(days=90),
            buyer_id="BSNL-PROC",
            buyer_name="Bharat Sanchar Nigam Limited",
            status=TenderStatus.CLOSED,
        )
        t6 = Tender.objects.create(
            tender_id="RRTS-2024-CON-0445",
            title="Civil Works for Regional Rapid Transit System — Package C3",
            category="Roads & Highways",
            estimated_value=decimal.Decimal("2100000000.00"),
            currency="INR",
            submission_deadline=now + timedelta(days=30),
            publication_date=now - timedelta(days=60),
            buyer_id="NCRTC",
            buyer_name="National Capital Region Transport Corporation",
            status=TenderStatus.ACTIVE,
        )
        t7 = Tender.objects.create(
            tender_id="ESIC-2024-MED-0312",
            title="Supply of Generic Medicines and Surgical Consumables — Annual Rate Contract",
            category="Healthcare Equipment",
            estimated_value=decimal.Decimal("45000000.00"),
            currency="INR",
            submission_deadline=now - timedelta(days=5),
            publication_date=now - timedelta(days=35),
            buyer_id="ESIC-PROC",
            buyer_name="Employees State Insurance Corporation",
            status=TenderStatus.AWARDED,
        )
        t8 = Tender.objects.create(
            tender_id="CPWD-2024-CON-0778",
            title="Construction of Central Government Residential Quarters — Type IV, 120 Units",
            category="Construction",
            estimated_value=decimal.Decimal("380000000.00"),
            currency="INR",
            submission_deadline=now + timedelta(days=15),
            publication_date=now - timedelta(days=45),
            buyer_id="CPWD-ZONE2",
            buyer_name="Central Public Works Department",
            status=TenderStatus.ACTIVE,
        )

        # ── Bids ─────────────────────────────────────────────────────────────
        # Cover bidding pattern: b1 and b2 (linked entities) both bid on t1, t4, t8
        # b1 wins consistently — REPEAT_WINNER pattern
        # Price anomaly on t3: winning bid 52% below estimated value
        # (Pattern documented in: World Bank INT fraud investigation reports)

        # t1 — NHAI Highway (b1 wins, b2 cover bids — linked entities)
        Bid.objects.create(bid_id="BID-T1-001", tender=t1, bidder=b1,
            bid_amount=decimal.Decimal("461750000.00"), submission_timestamp=now - timedelta(days=46), is_winner=True)
        Bid.objects.create(bid_id="BID-T1-002", tender=t1, bidder=b2,
            bid_amount=decimal.Decimal("483200000.00"), submission_timestamp=now - timedelta(days=46), is_winner=False)
        Bid.objects.create(bid_id="BID-T1-003", tender=t1, bidder=b5,
            bid_amount=decimal.Decimal("492000000.00"), submission_timestamp=now - timedelta(days=46), is_winner=False)

        # t2 — MCD Smart City (single bidder — SINGLE_BIDDER flag)
        Bid.objects.create(bid_id="BID-T2-001", tender=t2, bidder=b3,
            bid_amount=decimal.Decimal("119500000.00"), submission_timestamp=now - timedelta(days=21), is_winner=True)

        # t3 — AIIMS Ventilators (price anomaly: 52% below estimate)
        Bid.objects.create(bid_id="BID-T3-001", tender=t3, bidder=b4,
            bid_amount=decimal.Decimal("45600000.00"), submission_timestamp=now - timedelta(days=11), is_winner=True)
        Bid.objects.create(bid_id="BID-T3-002", tender=t3, bidder=b3,
            bid_amount=decimal.Decimal("91000000.00"), submission_timestamp=now - timedelta(days=11), is_winner=False)

        # t4 — PWD Renovation (b1 wins again, b2 cover bids — short deadline)
        Bid.objects.create(bid_id="BID-T4-001", tender=t4, bidder=b1,
            bid_amount=decimal.Decimal("26600000.00"), submission_timestamp=now - timedelta(days=1), is_winner=True)
        Bid.objects.create(bid_id="BID-T4-002", tender=t4, bidder=b2,
            bid_amount=decimal.Decimal("27900000.00"), submission_timestamp=now - timedelta(days=1), is_winner=False)

        # t5 — BSNL AMC
        Bid.objects.create(bid_id="BID-T5-001", tender=t5, bidder=b3,
            bid_amount=decimal.Decimal("64500000.00"), submission_timestamp=now - timedelta(days=61), is_winner=True)
        Bid.objects.create(bid_id="BID-T5-002", tender=t5, bidder=b1,
            bid_amount=decimal.Decimal("66200000.00"), submission_timestamp=now - timedelta(days=61), is_winner=False)
        Bid.objects.create(bid_id="BID-T5-003", tender=t5, bidder=b4,
            bid_amount=decimal.Decimal("68900000.00"), submission_timestamp=now - timedelta(days=61), is_winner=False)

        # t6 — RRTS Civil Works (b1 and b5 bid)
        Bid.objects.create(bid_id="BID-T6-001", tender=t6, bidder=b1,
            bid_amount=decimal.Decimal("1995000000.00"), submission_timestamp=now - timedelta(days=5), is_winner=False)
        Bid.objects.create(bid_id="BID-T6-002", tender=t6, bidder=b5,
            bid_amount=decimal.Decimal("2050000000.00"), submission_timestamp=now - timedelta(days=5), is_winner=False)

        # t7 — ESIC Medicines
        Bid.objects.create(bid_id="BID-T7-001", tender=t7, bidder=b4,
            bid_amount=decimal.Decimal("43200000.00"), submission_timestamp=now - timedelta(days=6), is_winner=True)
        Bid.objects.create(bid_id="BID-T7-002", tender=t7, bidder=b3,
            bid_amount=decimal.Decimal("44800000.00"), submission_timestamp=now - timedelta(days=6), is_winner=False)

        # t8 — CPWD Quarters (b1 wins again — repeat winner, b2 cover bids)
        Bid.objects.create(bid_id="BID-T8-001", tender=t8, bidder=b1,
            bid_amount=decimal.Decimal("361000000.00"), submission_timestamp=now - timedelta(days=10), is_winner=True)
        Bid.objects.create(bid_id="BID-T8-002", tender=t8, bidder=b2,
            bid_amount=decimal.Decimal("378500000.00"), submission_timestamp=now - timedelta(days=10), is_winner=False)
        Bid.objects.create(bid_id="BID-T8-003", tender=t8, bidder=b5,
            bid_amount=decimal.Decimal("385000000.00"), submission_timestamp=now - timedelta(days=10), is_winner=False)

        # ── Red Flags ─────────────────────────────────────────────────────────
        RedFlag.objects.create(tender=t1, bidder=b1, flag_type=FlagType.LINKED_ENTITIES,
            severity=Severity.HIGH, rule_version="1.0",
            trigger_data={"shared_address": "Plot 47, Sector 18, Gurugram", "shared_director": "Rajesh Kumar Sharma", "linked_bidder": "BID-IN-2024-002"},
            is_active=True, raised_at=now - timedelta(days=44))
        RedFlag.objects.create(tender=t1, flag_type=FlagType.SHORT_DEADLINE,
            severity=Severity.MEDIUM, rule_version="1.0",
            trigger_data={"deadline_days": 2, "threshold_days": 3, "publication_date": str(now - timedelta(days=47))},
            is_active=True, raised_at=now - timedelta(days=44))
        RedFlag.objects.create(tender=t2, flag_type=FlagType.SINGLE_BIDDER,
            severity=Severity.HIGH, rule_version="1.0",
            trigger_data={"bid_count": 1, "tender_id": "MCD-2024-IT-0234"},
            is_active=True, raised_at=now - timedelta(days=19))
        RedFlag.objects.create(tender=t3, flag_type=FlagType.PRICE_ANOMALY,
            severity=Severity.MEDIUM, rule_version="1.0",
            trigger_data={"winning_bid": 45600000, "estimated_value": 95000000, "deviation_pct": -52.0},
            is_active=True, raised_at=now - timedelta(days=9))
        RedFlag.objects.create(tender=t4, flag_type=FlagType.SHORT_DEADLINE,
            severity=Severity.MEDIUM, rule_version="1.0",
            trigger_data={"deadline_days": 2, "threshold_days": 3},
            is_active=True, raised_at=now - timedelta(days=1))
        RedFlag.objects.create(tender=t4, bidder=b1, flag_type=FlagType.REPEAT_WINNER,
            severity=Severity.HIGH, rule_version="1.0",
            trigger_data={"win_rate": 0.75, "category": "Construction", "window_months": 12, "wins": 3, "total": 4},
            is_active=True, raised_at=now - timedelta(days=1))
        RedFlag.objects.create(tender=t8, bidder=b1, flag_type=FlagType.COVER_BID_PATTERN,
            severity=Severity.HIGH, rule_version="1.0",
            trigger_data={"bidder": "BID-IN-2024-002", "tenders_in_30_days": 3, "wins": 0, "category": "Construction"},
            is_active=True, raised_at=now - timedelta(days=9))

        # ── Fraud Risk Scores ─────────────────────────────────────────────────
        # Scores based on rule contributions + simulated ML scores
        # High-risk tenders: t1 (82), t2 (78), t4 (91)
        # Medium-risk: t3 (58), t8 (65)
        # Low-risk: t5 (12), t6 (22), t7 (18)

        score_data = [
            (t1, 82, "0.7812", "0.6543", 60),
            (t2, 78, "0.8234", "0.5100", 70),
            (t3, 58, "0.4521", "0.3200", 40),
            (t4, 91, "0.9100", "0.8800", 75),
            (t5, 12, "0.0823", "0.0412", 5),
            (t6, 22, "0.1543", "0.1200", 10),
            (t7, 18, "0.1021", "0.0900", 8),
            (t8, 65, "0.6234", "0.7100", 50),
        ]
        for tender, score, anomaly, collusion, rf_contrib in score_data:
            FraudRiskScore.objects.create(
                tender=tender, score=score,
                ml_anomaly_score=decimal.Decimal(anomaly),
                ml_collusion_score=decimal.Decimal(collusion),
                red_flag_contribution=rf_contrib,
                model_version="IF-20260101/RF-20260101",
                weight_config={"high_weight": 30, "medium_weight": 15, "ml_anomaly_weight": 25, "ml_collusion_weight": 30},
                computed_at=now - timedelta(hours=2),
            )

        # ── Company Profiles ──────────────────────────────────────────────────
        CompanyProfile.objects.create(
            bidder=b1, total_bids=12, total_wins=9,
            win_rate=decimal.Decimal("0.7500"),
            avg_bid_deviation=decimal.Decimal("0.0523"),
            active_red_flag_count=3, highest_fraud_risk_score=91,
            risk_status=RiskStatus.HIGH_RISK,
        )
        CompanyProfile.objects.create(
            bidder=b2, total_bids=10, total_wins=0,
            win_rate=decimal.Decimal("0.0000"),
            avg_bid_deviation=decimal.Decimal("0.0312"),
            active_red_flag_count=2, highest_fraud_risk_score=82,
            risk_status=RiskStatus.HIGH_RISK,
        )
        CompanyProfile.objects.create(
            bidder=b3, total_bids=8, total_wins=3,
            win_rate=decimal.Decimal("0.3750"),
            avg_bid_deviation=decimal.Decimal("0.0189"),
            active_red_flag_count=1, highest_fraud_risk_score=78,
            risk_status=RiskStatus.MEDIUM,
        )
        CompanyProfile.objects.create(
            bidder=b4, total_bids=6, total_wins=2,
            win_rate=decimal.Decimal("0.3333"),
            avg_bid_deviation=decimal.Decimal("0.0421"),
            active_red_flag_count=1, highest_fraud_risk_score=58,
            risk_status=RiskStatus.MEDIUM,
        )
        CompanyProfile.objects.create(
            bidder=b5, total_bids=5, total_wins=1,
            win_rate=decimal.Decimal("0.2000"),
            avg_bid_deviation=decimal.Decimal("0.0098"),
            active_red_flag_count=0, highest_fraud_risk_score=22,
            risk_status=RiskStatus.LOW,
        )

        self.stdout.write(self.style.SUCCESS(
            f"Seeded: {Tender.objects.count()} tenders, "
            f"{Bid.objects.count()} bids, "
            f"{RedFlag.objects.count()} red flags, "
            f"{CompanyProfile.objects.count()} company profiles"
        ))

    def seed_graph(self, b1, b2, b3, b4, b5, t1, t3, t4, t5, t6, t7, t8, now):
        from datetime import timedelta
        from graph.models import GraphNode, GraphEdge, EdgeType, CollusionRing

        n1 = GraphNode.objects.create(bidder=b1, metadata={"fraud_score": 91, "risk_status": "HIGH_RISK"})
        n2 = GraphNode.objects.create(bidder=b2, metadata={"fraud_score": 82, "risk_status": "HIGH_RISK"})
        n3 = GraphNode.objects.create(bidder=b3, metadata={"fraud_score": 78, "risk_status": "MEDIUM"})
        n4 = GraphNode.objects.create(bidder=b4, metadata={"fraud_score": 58, "risk_status": "MEDIUM"})
        n5 = GraphNode.objects.create(bidder=b5, metadata={"fraud_score": 22, "risk_status": "LOW"})

        GraphEdge.objects.create(source_node=n1, target_node=n2, edge_type=EdgeType.SHARED_ADDRESS, tender=None, metadata={"address": "Plot 47, Sector 18, Gurugram"})
        GraphEdge.objects.create(source_node=n1, target_node=n2, edge_type=EdgeType.SHARED_DIRECTOR, tender=None, metadata={"director": "Rajesh Kumar Sharma"})
        GraphEdge.objects.create(source_node=n1, target_node=n2, edge_type=EdgeType.CO_BID, tender=t1, metadata={})
        GraphEdge.objects.create(source_node=n1, target_node=n2, edge_type=EdgeType.CO_BID, tender=t4, metadata={})
        GraphEdge.objects.create(source_node=n1, target_node=n2, edge_type=EdgeType.CO_BID, tender=t8, metadata={})
        GraphEdge.objects.create(source_node=n1, target_node=n5, edge_type=EdgeType.CO_BID, tender=t1, metadata={})
        GraphEdge.objects.create(source_node=n1, target_node=n5, edge_type=EdgeType.CO_BID, tender=t6, metadata={})
        GraphEdge.objects.create(source_node=n1, target_node=n5, edge_type=EdgeType.CO_BID, tender=t8, metadata={})
        GraphEdge.objects.create(source_node=n3, target_node=n4, edge_type=EdgeType.CO_BID, tender=t3, metadata={})
        GraphEdge.objects.create(source_node=n3, target_node=n4, edge_type=EdgeType.CO_BID, tender=t5, metadata={})
        GraphEdge.objects.create(source_node=n3, target_node=n4, edge_type=EdgeType.CO_BID, tender=t7, metadata={})

        CollusionRing.objects.create(ring_id="RING-2024-001", member_bidder_ids=[b1.id, b2.id], member_count=2, detected_at=now - timedelta(days=9), is_active=True)
        CollusionRing.objects.create(ring_id="RING-2024-002", member_bidder_ids=[b1.id, b2.id, b5.id], member_count=3, detected_at=now - timedelta(days=5), is_active=True)

        self.stdout.write(self.style.SUCCESS(
            f"Graph: {GraphNode.objects.count()} nodes, {GraphEdge.objects.count()} edges, {CollusionRing.objects.count()} rings"
        ))
