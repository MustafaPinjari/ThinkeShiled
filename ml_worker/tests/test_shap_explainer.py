"""
Unit tests for ml_worker/services/shap_explainer.py

Covers:
  - Completeness: shap_values has exactly one entry per feature (9 features)
  - Top-5 ordering: top_factors has exactly 5 entries sorted by |SHAP| descending
  - Fallback behavior: on SHAP exception, shap_failed=True, AuditLog entry created
  - Version stamping: model_version and rule_engine_version are non-null and match inputs

All Django ORM calls are mocked via sys.modules injection and monkeypatching.
"""

from __future__ import annotations

import sys
from contextlib import contextmanager
from types import ModuleType
from unittest.mock import MagicMock

import numpy as np
import pytest

from ml_worker.train import FEATURE_COLUMNS


def _make_stub_module(name, **attrs):
    mod = ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    return mod


@contextmanager
def _inject_django_stubs(tender_obj, red_flag_qs_mock=None):
    if red_flag_qs_mock is None:
        red_flag_qs_mock = MagicMock()
        red_flag_qs_mock.filter.return_value.values.return_value = []
    mock_tender_cls = MagicMock()
    mock_tender_cls.objects.get.return_value = tender_obj
    mock_tender_cls.DoesNotExist = type("DoesNotExist", (Exception,), {})
    mock_redflag_cls = MagicMock()
    mock_redflag_cls.objects = red_flag_qs_mock
    mock_company_profile = MagicMock()
    mock_company_profile.objects.filter.return_value.first.return_value = None
    mock_bid_cls = MagicMock()
    mock_bid_cls.objects.filter.return_value.select_related.return_value = []
    tenders_models = _make_stub_module("tenders.models", Tender=mock_tender_cls)
    tenders_pkg = _make_stub_module("tenders", models=tenders_models)
    detection_models = _make_stub_module("detection.models", RedFlag=mock_redflag_cls)
    detection_pkg = _make_stub_module("detection", models=detection_models)
    companies_models = _make_stub_module("companies.models", CompanyProfile=mock_company_profile)
    companies_pkg = _make_stub_module("companies", models=companies_models)
    bids_models = _make_stub_module("bids.models", Bid=mock_bid_cls)
    bids_pkg = _make_stub_module("bids", models=bids_models)
    stubs = {
        "tenders": tenders_pkg, "tenders.models": tenders_models,
        "detection": detection_pkg, "detection.models": detection_models,
        "companies": companies_pkg, "companies.models": companies_models,
        "bids": bids_pkg, "bids.models": bids_models,
    }
    originals = {k: sys.modules.get(k) for k in stubs}
    sys.modules.update(stubs)
    try:
        yield {"Tender": mock_tender_cls, "RedFlag": mock_redflag_cls}
    finally:
        for k, v in originals.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


def _make_feature_vector(seed=0):
    rng = np.random.default_rng(seed)
    return {col: float(rng.uniform(0.1, 1.0)) for col in FEATURE_COLUMNS}


def _make_shap_values(seed=1):
    rng = np.random.default_rng(seed)
    return {col: float(rng.uniform(-1.0, 1.0)) for col in FEATURE_COLUMNS}


def _make_mock_tender(tender_id=42):
    tender = MagicMock()
    tender.id = tender_id
    tender.pk = tender_id
    tender.estimated_value = 100_000.0
    tender.submission_deadline = MagicMock()
    tender.publication_date = MagicMock()
    tender.category = "IT"
    return tender


def _make_mock_explanation(shap_values, top_factors, shap_failed=False,
                            model_version="RF:v1", rule_engine_version="1.0"):
    obj = MagicMock()
    obj.pk = 1
    obj.shap_values = shap_values
    obj.top_factors = top_factors
    obj.shap_failed = shap_failed
    obj.model_version = model_version
    obj.rule_engine_version = rule_engine_version
    return obj


def _run_compute_shap(
    monkeypatch,
    shap_values,
    tender_id=42,
    model_version="RF:v1",
    rule_engine_version="1.0",
    shap_failed=False,
    rf_shap_raises=None,
    if_shap_raises=None,
    include_if_model=False,
):
    from ml_worker.services import shap_explainer as module

    tender = _make_mock_tender(tender_id)
    feature_vector = _make_feature_vector()

    if shap_values:
        top_factors = [
            {"feature": f, "shap_value": shap_values[f], "feature_value": 0.5, "explanation": "x"}
            for f in sorted(shap_values, key=lambda k: abs(shap_values[k]), reverse=True)[:5]
        ]
    else:
        top_factors = []

    explanation_obj = _make_mock_explanation(
        shap_values if not shap_failed else {},
        top_factors if not shap_failed else [],
        shap_failed=shap_failed,
        model_version=model_version,
        rule_engine_version=rule_engine_version,
    )

    mock_shap_exp_cls = MagicMock()
    mock_shap_exp_cls.objects.create.return_value = explanation_obj

    mock_auditlog = MagicMock()
    mock_eventtype = MagicMock()
    mock_eventtype.SHAP_FAILED = "SHAP_FAILED"

    mock_rf_version = MagicMock()
    mock_rf_version.model_artifact_path = "/fake/rf.pkl"
    mock_if_version = MagicMock(model_artifact_path="/fake/if.pkl") if include_if_model else None

    mock_mlmodelversion = MagicMock()
    mock_mlmodelversion.objects.filter.return_value.order_by.return_value.first.side_effect = [
        mock_rf_version,
        mock_if_version,
    ]

    mock_mlmodeltype = MagicMock()
    mock_mlmodeltype.RANDOM_FOREST = "RANDOM_FOREST"
    mock_mlmodeltype.ISOLATION_FOREST = "ISOLATION_FOREST"

    models_dict = {
        "AuditLog": mock_auditlog,
        "EventType": mock_eventtype,
        "Bid": MagicMock(),
        "RedFlag": MagicMock(),
        "MLModelType": mock_mlmodeltype,
        "MLModelVersion": mock_mlmodelversion,
        "SHAPExplanation": mock_shap_exp_cls,
    }

    monkeypatch.setattr(module, "_get_django_models", lambda: models_dict)
    monkeypatch.setattr(module, "_build_feature_vector_for_tender", lambda t, b: feature_vector)
    monkeypatch.setattr(module, "load_random_forest", lambda path: MagicMock())
    monkeypatch.setattr(module, "load_isolation_forest", lambda path: (MagicMock(), MagicMock()))

    if rf_shap_raises is not None:
        def _raise_rf(model, fv):
            raise rf_shap_raises
        monkeypatch.setattr(module, "_compute_rf_shap", _raise_rf)
    else:
        monkeypatch.setattr(module, "_compute_rf_shap", lambda model, fv: shap_values)

    if if_shap_raises is not None:
        def _raise_if(model, scaler, fv, **kw):
            raise if_shap_raises
        monkeypatch.setattr(module, "_compute_if_shap_kernel", _raise_if)

    with _inject_django_stubs(tender):
        result = module.compute_shap(
            tender_id=tender_id,
            model_version=model_version,
            rule_engine_version=rule_engine_version,
        )

    return result, mock_shap_exp_cls, mock_auditlog, mock_eventtype


class TestSHAPCompleteness:
    """shap_values must have exactly 9 entries, one per FEATURE_COLUMN."""

    def test_shap_values_has_exactly_nine_entries(self, monkeypatch):
        shap_values = _make_shap_values(seed=10)
        result, _, _, _ = _run_compute_shap(monkeypatch, shap_values)
        assert len(result["shap_values"]) == 9
        assert len(result["shap_values"]) == len(FEATURE_COLUMNS)

    def test_shap_values_keys_match_feature_columns(self, monkeypatch):
        shap_values = _make_shap_values(seed=20)
        result, _, _, _ = _run_compute_shap(monkeypatch, shap_values)
        assert set(result["shap_values"].keys()) == set(FEATURE_COLUMNS)

    def test_shap_values_are_floats(self, monkeypatch):
        shap_values = _make_shap_values(seed=30)
        result, _, _, _ = _run_compute_shap(monkeypatch, shap_values)
        for feature, value in result["shap_values"].items():
            assert isinstance(value, float), f"Expected float for {feature}, got {type(value)}"

    def test_stored_explanation_receives_all_features(self, monkeypatch):
        shap_values = _make_shap_values(seed=40)
        _, mock_shap_exp_cls, _, _ = _run_compute_shap(monkeypatch, shap_values)
        create_kwargs = mock_shap_exp_cls.objects.create.call_args[1]
        stored_shap = create_kwargs["shap_values"]
        assert set(stored_shap.keys()) == set(FEATURE_COLUMNS)

    def test_all_nine_named_features_present(self, monkeypatch):
        expected = {
            "cv_bids", "bid_spread_ratio", "norm_winning_distance",
            "single_bidder_flag", "price_deviation_pct", "deadline_days",
            "repeat_winner_rate", "bidder_count", "winner_bid_rank",
        }
        shap_values = _make_shap_values(seed=50)
        result, _, _, _ = _run_compute_shap(monkeypatch, shap_values)
        assert set(result["shap_values"].keys()) == expected


class TestTop5Ordering:
    """top_factors must have exactly 5 entries sorted by |SHAP| descending."""

    def test_top_factors_has_exactly_five_entries(self, monkeypatch):
        shap_values = _make_shap_values(seed=60)
        result, _, _, _ = _run_compute_shap(monkeypatch, shap_values)
        assert len(result["top_factors"]) == 5

    def test_top_factors_sorted_by_absolute_shap_descending(self, monkeypatch):
        shap_values = _make_shap_values(seed=70)
        result, _, _, _ = _run_compute_shap(monkeypatch, shap_values)
        magnitudes = [abs(f["shap_value"]) for f in result["top_factors"]]
        assert magnitudes == sorted(magnitudes, reverse=True)

    def test_top_factors_contain_highest_magnitude_features(self, monkeypatch):
        shap_values = _make_shap_values(seed=80)
        result, _, _, _ = _run_compute_shap(monkeypatch, shap_values)
        expected_top5 = sorted(
            FEATURE_COLUMNS, key=lambda f: abs(shap_values[f]), reverse=True
        )[:5]
        actual_features = [f["feature"] for f in result["top_factors"]]
        assert actual_features == expected_top5

    def test_top_factors_each_have_required_keys(self, monkeypatch):
        shap_values = _make_shap_values(seed=90)
        result, _, _, _ = _run_compute_shap(monkeypatch, shap_values)
        for factor in result["top_factors"]:
            assert "feature" in factor
            assert "shap_value" in factor
            assert "feature_value" in factor
            assert "explanation" in factor

    def test_derive_top_factors_unit_ascending_magnitudes(self):
        from ml_worker.services.shap_explainer import _derive_top_factors
        shap_values = {col: float(i + 1) for i, col in enumerate(FEATURE_COLUMNS)}
        feature_vector = {col: 0.5 for col in FEATURE_COLUMNS}
        top = _derive_top_factors(shap_values, feature_vector, n=5)
        assert len(top) == 5
        magnitudes = [abs(f["shap_value"]) for f in top]
        assert magnitudes == sorted(magnitudes, reverse=True)
        assert top[0]["feature"] == FEATURE_COLUMNS[-1]

    def test_derive_top_factors_negative_shap_ranks_by_absolute_value(self):
        from ml_worker.services.shap_explainer import _derive_top_factors
        shap_values = {col: 0.0 for col in FEATURE_COLUMNS}
        shap_values["cv_bids"] = -5.0
        shap_values["bid_spread_ratio"] = 3.0
        feature_vector = {col: 0.5 for col in FEATURE_COLUMNS}
        top = _derive_top_factors(shap_values, feature_vector, n=5)
        features = [f["feature"] for f in top]
        assert features[0] == "cv_bids"
        assert features[1] == "bid_spread_ratio"

    def test_derive_top_factors_returns_n_entries(self):
        from ml_worker.services.shap_explainer import _derive_top_factors
        shap_values = _make_shap_values(seed=11)
        feature_vector = _make_feature_vector()
        for n in (1, 3, 5):
            top = _derive_top_factors(shap_values, feature_vector, n=n)
            assert len(top) == n


class TestFallbackBehavior:
    def _run_failure(self, monkeypatch):
        return _run_compute_shap(
            monkeypatch,
            shap_values={},
            shap_failed=True,
            rf_shap_raises=RuntimeError("SHAP exploder"),
            if_shap_raises=RuntimeError("Kernel exploder"),
            include_if_model=True,
        )

    def test_shap_failed_is_true_in_result(self, monkeypatch):
        result, _, _, _ = self._run_failure(monkeypatch)
        assert result["shap_failed"] is True

    def test_shap_values_empty_on_failure(self, monkeypatch):
        result, _, _, _ = self._run_failure(monkeypatch)
        assert result["shap_values"] == {}

    def test_top_factors_empty_on_failure(self, monkeypatch):
        result, _, _, _ = self._run_failure(monkeypatch)
        assert result["top_factors"] == []

    def test_shap_explanation_created_with_shap_failed_true(self, monkeypatch):
        _, mock_shap_exp_cls, _, _ = self._run_failure(monkeypatch)
        create_kwargs = mock_shap_exp_cls.objects.create.call_args[1]
        assert create_kwargs["shap_failed"] is True

    def test_audit_log_created_on_failure(self, monkeypatch):
        _, _, mock_auditlog, mock_eventtype = self._run_failure(monkeypatch)
        mock_auditlog.objects.create.assert_called_once()
        create_kwargs = mock_auditlog.objects.create.call_args[1]
        assert create_kwargs["event_type"] == mock_eventtype.SHAP_FAILED

    def test_audit_log_references_correct_tender(self, monkeypatch):
        _, _, mock_auditlog, _ = self._run_failure(monkeypatch)
        create_kwargs = mock_auditlog.objects.create.call_args[1]
        assert create_kwargs["affected_entity_type"] == "Tender"
        assert create_kwargs["affected_entity_id"] == "42"

    def test_audit_log_snapshot_contains_versions(self, monkeypatch):
        _, _, mock_auditlog, _ = self._run_failure(monkeypatch)
        create_kwargs = mock_auditlog.objects.create.call_args[1]
        snapshot = create_kwargs["data_snapshot"]
        assert snapshot["model_version"] == "RF:v1"
        assert snapshot["rule_engine_version"] == "1.0"

    def test_fallback_explanation_helper_structure(self):
        from ml_worker.services.shap_explainer import _fallback_explanation
        tender = _make_mock_tender()
        mock_redflag_qs = MagicMock()
        mock_redflag_qs.filter.return_value.values.return_value = [
            {"flag_type": "SINGLE_BIDDER", "severity": "HIGH",
             "trigger_data": {}, "rule_version": "1.0"}
        ]
        with _inject_django_stubs(tender, red_flag_qs_mock=mock_redflag_qs):
            result = _fallback_explanation(tender)
        assert result["shap_failed"] is True
        assert result["shap_values"] == {}
        assert result["top_factors"] == []
        assert len(result["red_flags"]) == 1

    def test_no_audit_log_when_shap_succeeds(self, monkeypatch):
        shap_values = _make_shap_values(seed=5)
        _, _, mock_auditlog, _ = _run_compute_shap(monkeypatch, shap_values)
        mock_auditlog.objects.create.assert_not_called()


class TestVersionStamping:
    def test_model_version_in_result_is_non_null(self, monkeypatch):
        shap_values = _make_shap_values(seed=100)
        result, _, _, _ = _run_compute_shap(
            monkeypatch, shap_values, model_version="IF:v2/RF:v3", rule_engine_version="1.0"
        )
        assert result["model_version"] is not None
        assert result["model_version"] != ""

    def test_rule_engine_version_in_result_is_non_null(self, monkeypatch):
        shap_values = _make_shap_values(seed=101)
        result, _, _, _ = _run_compute_shap(
            monkeypatch, shap_values, model_version="RF:v1", rule_engine_version="1.0"
        )
        assert result["rule_engine_version"] is not None
        assert result["rule_engine_version"] != ""

    def test_model_version_matches_input(self, monkeypatch):
        shap_values = _make_shap_values(seed=102)
        result, _, _, _ = _run_compute_shap(
            monkeypatch, shap_values,
            model_version="IF:20240101-abc/RF:20240101-def",
            rule_engine_version="2.1",
        )
        assert result["model_version"] == "IF:20240101-abc/RF:20240101-def"

    def test_rule_engine_version_matches_input(self, monkeypatch):
        shap_values = _make_shap_values(seed=103)
        result, _, _, _ = _run_compute_shap(
            monkeypatch, shap_values, model_version="RF:v1", rule_engine_version="2.5"
        )
        assert result["rule_engine_version"] == "2.5"

    def test_stored_explanation_has_correct_model_version(self, monkeypatch):
        shap_values = _make_shap_values(seed=104)
        _, mock_shap_exp_cls, _, _ = _run_compute_shap(
            monkeypatch, shap_values, model_version="RF:v99", rule_engine_version="3.0"
        )
        create_kwargs = mock_shap_exp_cls.objects.create.call_args[1]
        assert create_kwargs["model_version"] == "RF:v99"

    def test_stored_explanation_has_correct_rule_engine_version(self, monkeypatch):
        shap_values = _make_shap_values(seed=105)
        _, mock_shap_exp_cls, _, _ = _run_compute_shap(
            monkeypatch, shap_values, model_version="RF:v1", rule_engine_version="4.2"
        )
        create_kwargs = mock_shap_exp_cls.objects.create.call_args[1]
        assert create_kwargs["rule_engine_version"] == "4.2"

    def test_default_rule_engine_version_constant_is_set(self):
        from ml_worker.services.shap_explainer import RULE_ENGINE_VERSION
        assert isinstance(RULE_ENGINE_VERSION, str)
        assert len(RULE_ENGINE_VERSION) > 0

    def test_different_model_versions_produce_different_stamps(self, monkeypatch):
        shap_values = _make_shap_values(seed=106)
        result_a, _, _, _ = _run_compute_shap(
            monkeypatch, shap_values, model_version="RF:v1", rule_engine_version="1.0"
        )
        result_b, _, _, _ = _run_compute_shap(
            monkeypatch, shap_values, model_version="RF:v2", rule_engine_version="2.0"
        )
        assert result_a["model_version"] != result_b["model_version"]
        assert result_a["rule_engine_version"] != result_b["rule_engine_version"]

    def test_version_stamp_preserved_on_failure(self, monkeypatch):
        result, _, _, _ = _run_compute_shap(
            monkeypatch,
            shap_values={},
            shap_failed=True,
            model_version="RF:v5",
            rule_engine_version="9.9",
            rf_shap_raises=RuntimeError("boom"),
            if_shap_raises=RuntimeError("boom"),
            include_if_model=True,
        )
        assert result["model_version"] == "RF:v5"
        assert result["rule_engine_version"] == "9.9"
