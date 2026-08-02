from __future__ import annotations

from dataclasses import asdict
import hashlib
import json

from lavine_buffett.config import RULES_VERSION, SCHEMA_VERSION, RuleConfig
from lavine_buffett import service
from lavine_buffett.materialize import production_frame
from scripts.validate import validate_production, validate_result


def result() -> dict:
    as_of = "20251231"
    symbol = "600519.SH"
    thresholds = asdict(RuleConfig())
    config_hash = hashlib.sha256(
        json.dumps(thresholds, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    universe_hash = hashlib.sha256(symbol.encode("utf-8")).hexdigest()
    source = "source"
    dataset_hash = hashlib.sha256(
        f"{as_of}:{SCHEMA_VERSION}:{config_hash}:{universe_hash}:{source}".encode("utf-8")
    ).hexdigest()
    return {
        "as_of": as_of, "run_id": "run",
        "dataset_version": f"{as_of}-{SCHEMA_VERSION}-{dataset_hash[:16]}",
        "rule_config_hash": config_hash, "source_snapshot": source, "data_sdk_version": "test",
        "runtime_versions": {"panda_data": "test", "pandas": "test", "numpy": "test", "pyarrow": "test"},
        "universe_hash": universe_hash, "source_response_count": 1,
        "rules_version": RULES_VERSION, "schema_version": SCHEMA_VERSION,
        "thresholds": thresholds, "universe_size": 1,
        "counts": {"pass": 1, "fail": 0, "insufficient_data": 0},
        "selected_symbols": ["600519.SH"],
        "diagnostics": {
            "insufficient_reason_counts": {}, "failed_check_counts": {},
            "industry_coverage": 1, "price_evidence_coverage": 1,
        },
        "records": [{
            "symbol": "600519.SH", "status": "pass", "selected": True,
            "coverage_years": list(range(2015, 2025)),
            "announce_dates": ["20250403"], "valuation_evidence_dates": ["20251231"],
            "report_adjustment_flags": [0, 1],
            "checks": {"pe": True}, "applicable_checks": ["pe"],
            "insufficient_reasons": [],
            "metrics": {
                "current_return": 0.2, "historical_return_floor": 0.15,
                "latest_net_profit": 1.0, "ttm_eps": 1.0, "close": 10.0, "pe_ttm": 10.0,
            },
        }],
    }


def test_validate_result_accepts_consistent_payload():
    assert validate_result(result())["status"] == "PASS"


def test_validate_result_rejects_bad_dates_and_counts():
    payload = result()
    payload["records"][0]["announce_dates"] = ["bad-date"]
    payload["counts"]["pass"] = 0
    report = validate_result(payload)
    assert report["status"] == "FAIL"
    assert any("invalid evidence dates" in error for error in report["errors"])
    assert "counts do not match records" in report["errors"]


def test_validate_result_rejects_unknown_status():
    payload = result()
    payload["records"][0]["status"] = "unexpected"
    payload["records"][0]["selected"] = False
    payload["selected_symbols"] = []
    payload["counts"] = {"pass": 0, "fail": 0, "insufficient_data": 0}
    report = validate_result(payload)
    assert report["status"] == "FAIL"
    assert any("invalid status" in error for error in report["errors"])


def test_validate_production_accepts_matching_evidence(monkeypatch):
    payload = result()
    record = payload["records"][0]
    frame = production_frame(payload)
    assert validate_production(frame)["status"] == "PASS"
    frame.loc[0, "signal"] = "hold"
    report = validate_production(frame)
    assert report["status"] == "FAIL"
    assert any("signal does not match status" in error for error in report["errors"])
