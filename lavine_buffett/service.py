from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from collections import Counter
import hashlib
import json
import re
from typing import Any
from uuid import uuid4

from .config import RULES_VERSION, SCHEMA_VERSION, RuleConfig
from . import panda_client
from .rules import clean_date, clean_symbol, evaluate_symbol, select_visible_revisions


def _validate_as_of(value: str) -> str:
    cleaned = clean_date(value)
    if not re.fullmatch(r"\d{8}", cleaned):
        raise ValueError("as_of must use YYYYMMDD")
    datetime.strptime(cleaned, "%Y%m%d")
    return cleaned


def _validate_symbols(symbols: list[str]) -> list[str]:
    normalized = [clean_symbol(symbol) for symbol in symbols]
    invalid = [symbol for symbol in normalized if symbol is None or not re.fullmatch(r"\d{6}\.(SH|SZ)", symbol)]
    if invalid:
        raise ValueError(f"unsupported A-share symbols: {invalid}")
    return sorted({str(symbol) for symbol in normalized})


def screen(
    *,
    as_of: str,
    symbols: list[str] | None = None,
    all_a: bool = False,
    config: RuleConfig | None = None,
) -> dict[str, Any]:
    """Run the fail-closed Q44 screen using PandaData evidence only."""
    as_of = _validate_as_of(as_of)
    if all_a == bool(symbols):
        raise ValueError("provide either symbols or all_a=True")
    universe = panda_client.discover_all_a(as_of) if all_a else _validate_symbols(symbols or [])
    config = config or RuleConfig()
    thresholds = asdict(config)
    config_hash = hashlib.sha256(
        json.dumps(thresholds, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    versions = panda_client.runtime_versions()
    panda_client.ensure_authenticated()
    reports = panda_client.fetch_reports(universe, as_of, years=config.history_years + 3)
    visible, conflicts = select_visible_revisions(reports, as_of)
    prices = panda_client.fetch_latest_prices(universe, as_of)
    industries = panda_client.fetch_industries(universe, as_of)
    report_groups = {
        str(symbol): group.reset_index(drop=True)
        for symbol, group in visible.groupby("symbol", sort=False)
    }
    empty_reports = visible.iloc[0:0].copy()
    conflicts_by_symbol: dict[str, set[tuple[str, str]]] = {}
    for symbol, quarter in conflicts:
        conflicts_by_symbol.setdefault(symbol, set()).add((symbol, quarter))
    records = [
        evaluate_symbol(
            symbol,
            report_groups.get(symbol, empty_reports),
            prices.get(symbol),
            industries.get(symbol),
            conflicts_by_symbol.get(symbol),
            config,
        )
        for symbol in universe
    ]
    records.sort(
        key=lambda record: (
            not record["selected"],
            -(record["metrics"].get("current_return") or float("-inf")),
            record["symbol"],
        )
    )
    counts = {status: sum(record["status"] == status for record in records) for status in ("pass", "fail", "insufficient_data")}
    insufficient_reasons = Counter(
        reason for record in records for reason in record["insufficient_reasons"]
    )
    failed_checks = Counter(
        name for record in records for name, value in record["checks"].items() if value is False
    )
    generated_at = datetime.now(timezone.utc).isoformat()
    universe_hash = hashlib.sha256("\n".join(sorted(universe)).encode("utf-8")).hexdigest()
    source = panda_client.source_provenance()
    dataset_hash = hashlib.sha256(
        f"{as_of}:{SCHEMA_VERSION}:{config_hash}:{universe_hash}:{source['response_manifest_hash']}".encode("utf-8")
    ).hexdigest()
    return {
        "skill_id": "Q44-LAVINE",
        "as_of": as_of,
        "generated_at": generated_at,
        "run_id": str(uuid4()),
        "data_source": "PandaData",
        "data_sdk_version": versions["panda_data"],
        "runtime_versions": versions,
        "universe_hash": universe_hash,
        "source_response_count": source["response_count"],
        "source_snapshot": source["response_manifest_hash"],
        "dataset_version": f"{as_of}-{SCHEMA_VERSION}-{dataset_hash[:16]}",
        "rules_version": RULES_VERSION,
        "schema_version": SCHEMA_VERSION,
        "rule_config_hash": config_hash,
        "thresholds": thresholds,
        "universe_size": len(universe),
        "counts": counts,
        "diagnostics": {
            "insufficient_reason_counts": dict(sorted(insufficient_reasons.items())),
            "failed_check_counts": dict(sorted(failed_checks.items())),
            "industry_coverage": sum("missing_industry" not in record["insufficient_reasons"] for record in records),
            "price_evidence_coverage": sum(record["metrics"].get("close") is not None for record in records),
        },
        "selected_symbols": [record["symbol"] for record in records if record["selected"]],
        "records": records,
    }
