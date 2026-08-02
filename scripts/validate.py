from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import sys

import pandas as pd

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lavine_buffett.config import RULES_VERSION, SCHEMA_VERSION


def validate_result(result: dict) -> dict:
    as_of = str(result.get("as_of", ""))
    errors: list[str] = []
    try:
        datetime.strptime(as_of, "%Y%m%d")
    except ValueError:
        errors.append("invalid result as_of")
    required_metadata = {
        "run_id", "dataset_version", "rule_config_hash", "source_snapshot",
        "data_sdk_version", "runtime_versions", "universe_hash", "source_response_count",
        "rules_version", "schema_version", "diagnostics", "thresholds",
    }
    missing_metadata = sorted(required_metadata - set(result))
    if missing_metadata:
        errors.append(f"missing metadata {missing_metadata}")
    records = result.get("records", [])
    symbols = [record.get("symbol") for record in records]
    if len(symbols) != len(set(symbols)):
        errors.append("duplicate record symbols")
    if result.get("universe_size") != len(records):
        errors.append("universe_size does not match records")
    if result.get("rules_version") != RULES_VERSION:
        errors.append("rules_version does not match runtime")
    if result.get("schema_version") != SCHEMA_VERSION:
        errors.append("schema_version does not match runtime")
    thresholds = result.get("thresholds", {})
    expected_config_hash = hashlib.sha256(
        json.dumps(thresholds, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if result.get("rule_config_hash") != expected_config_hash:
        errors.append("rule_config_hash does not match thresholds")
    expected_universe_hash = hashlib.sha256(
        "\n".join(sorted(str(symbol) for symbol in symbols)).encode("utf-8")
    ).hexdigest()
    if result.get("universe_hash") != expected_universe_hash:
        errors.append("universe_hash does not match records")
    expected_dataset_hash = hashlib.sha256(
        f"{as_of}:{SCHEMA_VERSION}:{expected_config_hash}:{expected_universe_hash}:{result.get('source_snapshot', '')}".encode("utf-8")
    ).hexdigest()
    expected_dataset_version = f"{as_of}-{SCHEMA_VERSION}-{expected_dataset_hash[:16]}"
    if result.get("dataset_version") != expected_dataset_version:
        errors.append("dataset_version does not match inputs")
    expected_counts = {
        status: sum(record.get("status") == status for record in records)
        for status in ("pass", "fail", "insufficient_data")
    }
    if result.get("counts") != expected_counts:
        errors.append("counts do not match records")
    expected_selected = [record.get("symbol") for record in records if record.get("selected")]
    if result.get("selected_symbols") != expected_selected:
        errors.append("selected_symbols do not match records")
    expected_reasons = dict(sorted(Counter(
        reason for record in records for reason in record.get("insufficient_reasons", [])
    ).items()))
    expected_failed_checks = dict(sorted(Counter(
        name for record in records for name, value in record.get("checks", {}).items() if value is False
    ).items()))
    diagnostics = result.get("diagnostics", {})
    if diagnostics.get("insufficient_reason_counts") != expected_reasons:
        errors.append("diagnostic insufficient reasons do not match records")
    if diagnostics.get("failed_check_counts") != expected_failed_checks:
        errors.append("diagnostic failed checks do not match records")

    def valid_date(value) -> bool:
        try:
            datetime.strptime(str(value), "%Y%m%d")
            return True
        except ValueError:
            return False

    for record in records:
        symbol = record.get("symbol")
        status = record.get("status")
        if status not in {"pass", "fail", "insufficient_data"}:
            errors.append(f"{symbol}: invalid status {status}")
        announcements = record.get("announce_dates", [])
        valuations = record.get("valuation_evidence_dates", [])
        invalid_dates = [date for date in announcements + valuations if not valid_date(date)]
        future_announcements = [date for date in announcements if valid_date(date) and str(date) > as_of]
        future_valuations = [date for date in valuations if valid_date(date) and str(date) > as_of]
        if invalid_dates:
            errors.append(f"{record.get('symbol')}: invalid evidence dates {invalid_dates}")
        if future_announcements:
            errors.append(f"{record.get('symbol')}: future announcement dates {future_announcements}")
        if future_valuations:
            errors.append(f"{record.get('symbol')}: future valuation dates {future_valuations}")
        if record.get("selected") and record.get("status") != "pass":
            errors.append(f"{record.get('symbol')}: selected without pass status")
        if bool(record.get("selected")) != (status == "pass"):
            errors.append(f"{symbol}: selected flag does not match status")
        checks = record.get("checks", {})
        applicable = record.get("applicable_checks", [])
        if record.get("selected") and not all(checks.get(name) is True for name in applicable):
            errors.append(f"{record.get('symbol')}: selected with a failed applicable check")
        reasons = record.get("insufficient_reasons", [])
        if status == "insufficient_data" and not reasons:
            errors.append(f"{symbol}: insufficient_data without reasons")
        if status in {"pass", "fail"} and reasons:
            errors.append(f"{symbol}: {status} record has insufficient reasons")
        if status == "fail" and not any(checks.get(name) is False for name in applicable):
            errors.append(f"{symbol}: fail record has no failed applicable check")
        if status == "pass" and not all(checks.get(name) is True for name in applicable):
            errors.append(f"{symbol}: pass record has non-passing checks")
        if any(flag not in {0, 1} for flag in record.get("report_adjustment_flags", [])):
            errors.append(f"{symbol}: invalid report adjustment flag")
        coverage = record.get("coverage_years", [])
        if status in {"pass", "fail"}:
            if len(coverage) != 10 or any(b - a != 1 for a, b in zip(coverage, coverage[1:])):
                errors.append(f"{symbol}: complete status without ten consecutive years")
        required_metrics = {
            "current_return", "historical_return_floor", "latest_net_profit",
            "ttm_eps", "close", "pe_ttm",
        }
        if required_metrics - set(record.get("metrics", {})):
            errors.append(f"{symbol}: missing required metrics")
    return {"status": "PASS" if not errors else "FAIL", "errors": errors, "record_count": len(records)}


def validate_production(frame: pd.DataFrame) -> dict:
    errors: list[str] = []
    required = {
        "trade_date", "factor_id", "symbol", "signal", "status", "evidence_json",
        "run_metadata_json", "data_version", "rules_version", "rule_config_hash",
        "run_id", "source_snapshot", "data_sdk_version", "runtime_versions_json",
        "schema_version",
    }
    missing = sorted(required - set(frame.columns))
    if missing:
        errors.append(f"missing production columns {missing}")
        return {"status": "FAIL", "errors": errors, "record_count": len(frame)}
    if frame.duplicated(["trade_date", "factor_id", "symbol"]).any():
        errors.append("duplicate production keys")
    if not frame["status"].isin(["pass", "fail", "insufficient_data"]).all():
        errors.append("invalid production status")
    if not frame["schema_version"].eq(SCHEMA_VERSION).all():
        errors.append("production schema_version does not match runtime")
    if not frame["rules_version"].eq(RULES_VERSION).all():
        errors.append("production rules_version does not match runtime")
    for row in frame.itertuples(index=False):
        try:
            evidence = json.loads(row.evidence_json)
            metadata = json.loads(row.run_metadata_json)
            runtime = json.loads(row.runtime_versions_json)
        except (TypeError, json.JSONDecodeError):
            errors.append(f"{row.symbol}: invalid JSON evidence or metadata")
            continue
        if evidence.get("symbol") != row.symbol or evidence.get("status") != row.status:
            errors.append(f"{row.symbol}: row and evidence mismatch")
        expected_signal = "buy" if row.status == "pass" else "hold"
        if row.signal != expected_signal:
            errors.append(f"{row.symbol}: signal does not match status")
        for key, value in (
            ("run_id", row.run_id), ("dataset_version", row.data_version),
            ("rule_config_hash", row.rule_config_hash), ("source_snapshot", row.source_snapshot),
        ):
            if metadata.get(key) != value:
                errors.append(f"{row.symbol}: {key} metadata mismatch")
        if runtime.get("panda_data") != row.data_sdk_version:
            errors.append(f"{row.symbol}: runtime SDK metadata mismatch")
    return {"status": "PASS" if not errors else "FAIL", "errors": errors, "record_count": len(frame)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a Q44 JSON result")
    parser.add_argument("result")
    args = parser.parse_args()
    path = Path(args.result)
    if path.suffix.lower() == ".parquet":
        report = validate_production(pd.read_parquet(path))
    else:
        report = validate_result(json.loads(path.read_text(encoding="utf-8")))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
