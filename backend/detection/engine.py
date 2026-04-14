"""
FraudDetectionEngine — evaluates all active rule-based red flag checks
against a tender and its bids.

Rules implemented:
  1. SINGLE_BIDDER    — exactly 1 bidder at submission deadline → HIGH
  2. PRICE_ANOMALY    — winning bid deviates > 40% from estimated_value → MEDIUM
  3. REPEAT_WINNER    — same bidder wins > 60% of tenders in category (12-month window) → HIGH
  4. SHORT_DEADLINE   — < 3 calendar days between publication and deadline → MEDIUM
  5. LINKED_ENTITIES  — 2+ bidders share registered_address or director_name → HIGH
  6. COVER_BID_PATTERN— bidder bids in 3+ tenders in same category in 30 days, wins none → HIGH
"""

import logging
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from audit.models import AuditLog, EventType
from detection.models import FlagType, RedFlag, RuleDefinition

logger = logging.getLogger(__name__)


class FraudDetectionEngine:
    """
    Stateless fraud detection engine.

    Rules are loaded from the DB on every evaluate_rules() call (hot-reload).
    """

    # ------------------------------------------------------------------ #
    # Public interface                                                     #
    # ------------------------------------------------------------------ #

    def evaluate_rules(self, tender_id: int) -> list:
        """
        Evaluate all active rules for a tender.

        Returns the list of RedFlag objects that are currently active after
        this evaluation run (newly raised + previously raised and still firing).
        Clears flags that no longer fire.
        """
        from tenders.models import Tender  # local import to avoid circular deps

        try:
            tender = Tender.objects.get(pk=tender_id)
        except Tender.DoesNotExist:
            logger.warning("evaluate_rules called with unknown tender_id=%s", tender_id)
            return []

        active_rules = self.get_active_rules()
        rule_map = {r.rule_code: r for r in active_rules}

        raised_flags: list[RedFlag] = []

        for rule_code, rule_def in rule_map.items():
            handler = self._get_handler(rule_code)
            if handler is None:
                continue
            try:
                flags = handler(tender, rule_def)
                raised_flags.extend(flags)
            except Exception:
                logger.exception("Error evaluating rule %s for tender %s", rule_code, tender_id)

        # Clear previously active flags that no longer fire
        self._sync_flags(tender, raised_flags)

        # Trigger score recomputation after rule evaluation
        self._trigger_rescore(tender_id)

        return list(RedFlag.objects.filter(tender=tender, is_active=True))

    def get_active_rules(self) -> list:
        """Return all currently active RuleDefinition records (hot-reload from DB)."""
        return list(RuleDefinition.objects.filter(is_active=True))

    def add_rule(self, rule: RuleDefinition) -> None:
        """Persist a new RuleDefinition (no restart required)."""
        rule.save()
        AuditLog.objects.create(
            event_type=EventType.RULE_ADDED,
            affected_entity_type="RuleDefinition",
            affected_entity_id=str(rule.pk),
            data_snapshot={"rule_code": rule.rule_code, "severity": rule.severity},
        )

    # ------------------------------------------------------------------ #
    # Rule handlers                                                        #
    # ------------------------------------------------------------------ #

    def _get_handler(self, rule_code: str):
        handlers = {
            FlagType.SINGLE_BIDDER: self._rule_single_bidder,
            FlagType.PRICE_ANOMALY: self._rule_price_anomaly,
            FlagType.REPEAT_WINNER: self._rule_repeat_winner,
            FlagType.SHORT_DEADLINE: self._rule_short_deadline,
            FlagType.LINKED_ENTITIES: self._rule_linked_entities,
            FlagType.COVER_BID_PATTERN: self._rule_cover_bid_pattern,
        }
        return handlers.get(rule_code)

    # 8.2 — SINGLE_BIDDER
    def _rule_single_bidder(self, tender, rule_def: RuleDefinition) -> list:
        from bids.models import Bid

        bid_count = Bid.objects.filter(tender=tender).values("bidder").distinct().count()
        if bid_count == 1:
            return [self._raise_flag(
                tender=tender,
                bidder=None,
                flag_type=FlagType.SINGLE_BIDDER,
                severity=rule_def.severity,
                rule_version=str(rule_def.pk),
                trigger_data={"bid_count": bid_count},
            )]
        return []

    # 8.3 — PRICE_ANOMALY
    def _rule_price_anomaly(self, tender, rule_def: RuleDefinition) -> list:
        from bids.models import Bid

        bids = Bid.objects.filter(tender=tender).order_by("bid_amount")
        if not bids.exists():
            return []

        winning_bid = bids.first()
        estimated = tender.estimated_value
        if not estimated or estimated == 0:
            return []

        deviation = abs(winning_bid.bid_amount - estimated) / abs(estimated)
        threshold = Decimal(str(rule_def.parameters.get("threshold", "0.40")))

        if deviation > threshold:
            return [self._raise_flag(
                tender=tender,
                bidder=winning_bid.bidder,
                flag_type=FlagType.PRICE_ANOMALY,
                severity=rule_def.severity,
                rule_version=str(rule_def.pk),
                trigger_data={
                    "winning_bid": str(winning_bid.bid_amount),
                    "estimated_value": str(estimated),
                    "deviation_pct": float(round(deviation * 100, 4)),
                },
            )]
        return []

    # 8.4 — REPEAT_WINNER
    def _rule_repeat_winner(self, tender, rule_def: RuleDefinition) -> list:
        from bids.models import Bid
        from tenders.models import Tender

        window_start = timezone.now() - timedelta(days=365)
        category = tender.category

        # All tenders in same category within 12-month window
        category_tenders = Tender.objects.filter(
            category=category,
            created_at__gte=window_start,
        )
        total = category_tenders.count()
        if total == 0:
            return []

        threshold = float(rule_def.parameters.get("threshold", 0.60))
        flags = []

        # For each bidder that has bids on this tender, check their win rate
        bidder_ids = Bid.objects.filter(tender=tender).values_list("bidder_id", flat=True).distinct()

        for bidder_id in bidder_ids:
            # Count tenders in category where this bidder submitted the lowest bid
            wins = 0
            for t in category_tenders:
                lowest = Bid.objects.filter(tender=t).order_by("bid_amount").first()
                if lowest and lowest.bidder_id == bidder_id:
                    wins += 1

            win_rate = wins / total
            if win_rate > threshold:
                from bids.models import Bidder
                try:
                    bidder = Bidder.objects.get(pk=bidder_id)
                except Bidder.DoesNotExist:
                    bidder = None

                flags.append(self._raise_flag(
                    tender=tender,
                    bidder=bidder,
                    flag_type=FlagType.REPEAT_WINNER,
                    severity=rule_def.severity,
                    rule_version=str(rule_def.pk),
                    trigger_data={
                        "bidder_id": bidder_id,
                        "wins": wins,
                        "total_tenders": total,
                        "win_rate_pct": round(win_rate * 100, 4),
                        "category": category,
                    },
                ))

        return flags

    # 8.5 — SHORT_DEADLINE
    def _rule_short_deadline(self, tender, rule_def: RuleDefinition) -> list:
        # Use publication_date if available, else created_at
        publication = tender.publication_date or tender.created_at
        if not publication or not tender.submission_deadline:
            return []

        delta = tender.submission_deadline - publication
        min_days = int(rule_def.parameters.get("min_days", 3))

        if delta.total_seconds() < min_days * 86400:
            return [self._raise_flag(
                tender=tender,
                bidder=None,
                flag_type=FlagType.SHORT_DEADLINE,
                severity=rule_def.severity,
                rule_version=str(rule_def.pk),
                trigger_data={
                    "publication_date": publication.isoformat(),
                    "submission_deadline": tender.submission_deadline.isoformat(),
                    "delta_seconds": delta.total_seconds(),
                },
            )]
        return []

    # 8.6 — LINKED_ENTITIES
    def _rule_linked_entities(self, tender, rule_def: RuleDefinition) -> list:
        from bids.models import Bid, Bidder

        bidder_ids = list(
            Bid.objects.filter(tender=tender).values_list("bidder_id", flat=True).distinct()
        )
        if len(bidder_ids) < 2:
            return []

        bidders = list(Bidder.objects.filter(pk__in=bidder_ids))

        # Check shared registered_address
        address_groups: dict[str, list] = {}
        for b in bidders:
            addr = (b.registered_address or "").strip()
            if addr:
                address_groups.setdefault(addr, []).append(b)

        # Check shared director names
        director_groups: dict[str, list] = {}
        for b in bidders:
            for director in b.get_director_list():
                director_groups.setdefault(director, []).append(b)

        flags = []
        seen_pairs: set = set()

        def _emit_flag(b1, b2, link_type, link_value):
            pair = tuple(sorted([b1.pk, b2.pk]))
            key = (pair, link_type, link_value)
            if key in seen_pairs:
                return
            seen_pairs.add(key)
            flags.append(self._raise_flag(
                tender=tender,
                bidder=b1,
                flag_type=FlagType.LINKED_ENTITIES,
                severity=rule_def.severity,
                rule_version=str(rule_def.pk),
                trigger_data={
                    "link_type": link_type,
                    "link_value": link_value,
                    "bidder_ids": [b1.pk, b2.pk],
                    "bidder_names": [b1.bidder_name, b2.bidder_name],
                },
            ))

        for addr, group in address_groups.items():
            if len(group) >= 2:
                for i in range(len(group)):
                    for j in range(i + 1, len(group)):
                        _emit_flag(group[i], group[j], "shared_address", addr)

        for director, group in director_groups.items():
            if len(group) >= 2:
                for i in range(len(group)):
                    for j in range(i + 1, len(group)):
                        _emit_flag(group[i], group[j], "shared_director", director)

        return flags

    # 8.7 — COVER_BID_PATTERN
    def _rule_cover_bid_pattern(self, tender, rule_def: RuleDefinition) -> list:
        from bids.models import Bid

        window_days = int(rule_def.parameters.get("window_days", 30))
        min_bids = int(rule_def.parameters.get("min_bids", 3))
        window_start = timezone.now() - timedelta(days=window_days)
        category = tender.category

        bidder_ids = list(
            Bid.objects.filter(tender=tender).values_list("bidder_id", flat=True).distinct()
        )

        flags = []
        for bidder_id in bidder_ids:
            # Tenders in same category where this bidder bid within the window
            bids_in_window = Bid.objects.filter(
                bidder_id=bidder_id,
                tender__category=category,
                submission_timestamp__gte=window_start,
            ).select_related("tender")

            tender_ids_in_window = list(
                bids_in_window.values_list("tender_id", flat=True).distinct()
            )
            bid_count = len(tender_ids_in_window)

            if bid_count < min_bids:
                continue

            # Check if bidder won any of those tenders (lowest bid)
            wins = 0
            for t_id in tender_ids_in_window:
                lowest = Bid.objects.filter(tender_id=t_id).order_by("bid_amount").first()
                if lowest and lowest.bidder_id == bidder_id:
                    wins += 1

            if wins == 0:
                from bids.models import Bidder
                try:
                    bidder = Bidder.objects.get(pk=bidder_id)
                except Bidder.DoesNotExist:
                    bidder = None

                flags.append(self._raise_flag(
                    tender=tender,
                    bidder=bidder,
                    flag_type=FlagType.COVER_BID_PATTERN,
                    severity=rule_def.severity,
                    rule_version=str(rule_def.pk),
                    trigger_data={
                        "bidder_id": bidder_id,
                        "tenders_bid": bid_count,
                        "wins": wins,
                        "category": category,
                        "window_days": window_days,
                    },
                ))

        return flags

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    def _raise_flag(
        self,
        tender,
        bidder,
        flag_type: str,
        severity: str,
        rule_version: str,
        trigger_data: dict,
    ) -> RedFlag:
        """
        Create or update a RedFlag record.

        If an active flag of the same type already exists for this tender
        (and bidder), reuse it. Otherwise create a new one.
        """
        now = timezone.now()
        qs = RedFlag.objects.filter(
            tender=tender,
            flag_type=flag_type,
            bidder=bidder,
            is_active=True,
        )
        existing = qs.first()
        if existing:
            # Update trigger_data and rule_version in case they changed
            existing.trigger_data = trigger_data
            existing.rule_version = rule_version
            existing.save(update_fields=["trigger_data", "rule_version"])
            return existing

        flag = RedFlag.objects.create(
            tender=tender,
            bidder=bidder,
            flag_type=flag_type,
            severity=severity,
            rule_version=rule_version,
            trigger_data=trigger_data,
            is_active=True,
            raised_at=now,
        )
        AuditLog.objects.create(
            event_type=EventType.RED_FLAG_RAISED,
            affected_entity_type="RedFlag",
            affected_entity_id=str(flag.pk),
            data_snapshot={
                "tender_id": tender.pk,
                "flag_type": flag_type,
                "severity": severity,
                "trigger_data": trigger_data,
            },
        )
        return flag

    def _sync_flags(self, tender, raised_flags: list) -> None:
        """
        Clear any previously active flags that were NOT raised in this run.
        """
        raised_pks = {f.pk for f in raised_flags}
        stale = RedFlag.objects.filter(tender=tender, is_active=True).exclude(pk__in=raised_pks)
        now = timezone.now()
        for flag in stale:
            flag.is_active = False
            flag.cleared_at = now
            flag.save(update_fields=["is_active", "cleared_at"])
            AuditLog.objects.create(
                event_type=EventType.RED_FLAG_CLEARED,
                affected_entity_type="RedFlag",
                affected_entity_id=str(flag.pk),
                data_snapshot={
                    "tender_id": tender.pk,
                    "flag_type": flag.flag_type,
                    "severity": flag.severity,
                },
            )

    def _trigger_rescore(self, tender_id: int) -> None:
        """Enqueue a score recomputation task (within 5 s via Celery)."""
        try:
            from bids.tasks import compute_score_task
            compute_score_task.delay(tender_id)
        except Exception:
            logger.exception("Failed to enqueue compute_score_task for tender_id=%s", tender_id)
