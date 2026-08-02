from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd

from .config import RULES_VERSION, SCHEMA_VERSION, SKILL_ID, SKILL_NAME


PRODUCTION_KEY = ["trade_date", "factor_id", "symbol"]


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False, default=str)


def production_frame(result: dict[str, Any]) -> pd.DataFrame:
    now = datetime.now(timezone.utc).isoformat()
    run_metadata = {
        key: value for key, value in result.items()
        if key not in {"records"}
    }
    rows = []
    for rank, record in enumerate(result["records"], start=1):
        current_return = record["metrics"].get("current_return")
        rows.append(
            {
                "trade_date": result["as_of"],
                "asset_type": "stock",
                "symbol": record["symbol"],
                "factor_id": SKILL_ID,
                "factor_name": SKILL_NAME,
                "factor_value": current_return,
                "score": 100.0 if record["selected"] else 0.0,
                "rank": rank if record["selected"] else pd.NA,
                "signal": "buy" if record["selected"] else "hold",
                "confidence": 1.0 if record["status"] != "insufficient_data" else 0.0,
                "status": record["status"],
                "evidence_json": canonical_json(record),
                "run_metadata_json": canonical_json(run_metadata),
                "data_source": "PandaData",
                "data_version": result["dataset_version"],
                "rules_version": RULES_VERSION,
                "rule_config_hash": result["rule_config_hash"],
                "run_id": result["run_id"],
                "source_snapshot": result["source_snapshot"],
                "data_sdk_version": result["data_sdk_version"],
                "runtime_versions_json": canonical_json(result["runtime_versions"]),
                "schema_version": SCHEMA_VERSION,
                "update_time": now,
            }
        )
    frame = pd.DataFrame(rows)
    if frame.empty:
        raise ValueError("cannot materialize an empty screen result")
    if frame.duplicated(PRODUCTION_KEY).any():
        raise ValueError(f"duplicate production key: {PRODUCTION_KEY}")
    for payload in frame["evidence_json"]:
        json.loads(payload)
    return frame


def write_production(frame: pd.DataFrame, path: str | Path, *, replace: bool = False) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    result = frame
    if output.exists() and not replace:
        existing = pd.read_parquet(output)
        if set(existing.columns) != set(frame.columns):
            raise ValueError("production schema changed; use explicit replace after migration review")
        incoming_keys = pd.MultiIndex.from_frame(frame[PRODUCTION_KEY])
        existing_keys = pd.MultiIndex.from_frame(existing[PRODUCTION_KEY])
        result = pd.concat(
            [existing.loc[~existing_keys.isin(incoming_keys)], frame],
            ignore_index=True,
        )
        if result.duplicated(PRODUCTION_KEY).any():
            raise ValueError(f"duplicate production key after upsert: {PRODUCTION_KEY}")
    temporary = output.with_name(f"{output.name}.{uuid4().hex}.tmp")
    try:
        result.to_parquet(temporary, index=False)
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    return output
