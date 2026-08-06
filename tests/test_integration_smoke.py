from __future__ import annotations

import json

import pandas as pd
import pytest

from lavine_buffett import panda_client
from scripts import build
from scripts.validate import validate_production, validate_result


def reports() -> pd.DataFrame:
    rows = []
    for year in range(2014, 2025):
        rows.append({
            "symbol": "600001.SH", "quarter": f"{year}q4", "date": f"{year + 1}0430",
            "if_adjusted": 0, "is_n_income_attr_p": 16.0,
            "bs_total_hldr_eqy_exc_min_int": 100.0, "bs_total_assets": 200.0,
            "is_gross_profit": 45.0, "is_revenue": 100.0, "cfs_cash_paid_asset": 4.0,
            "bs_lt_borr": 20.0, "bs_bond_payable": 10.0,
            "bs_ncl_due_1y": 5.0, "is_basic_eps": 2.0,
        })
    return pd.DataFrame(rows)


@pytest.fixture
def offline_provider(monkeypatch):
    monkeypatch.setattr(panda_client, "ensure_authenticated", lambda: None)
    monkeypatch.setattr(
        panda_client, "runtime_versions",
        lambda: {"panda_data": "smoke-sdk", "pandas": "test", "numpy": "test", "pyarrow": "test"},
    )
    monkeypatch.setattr(panda_client, "fetch_reports", lambda *args, **kwargs: reports())
    monkeypatch.setattr(
        panda_client, "fetch_latest_prices",
        lambda *args, **kwargs: {"600001.SH": {"date": "20251231", "close": 40.0}},
    )
    monkeypatch.setattr(
        panda_client, "fetch_industries",
        lambda *args, **kwargs: {"600001.SH": {"industry_code": "801120", "industry_name": "Food"}},
    )


def test_integration_smoke_build_json_and_parquet(offline_provider, tmp_path):
    json_path = tmp_path / "screen.json"
    parquet_path = tmp_path / "screen.parquet"

    result = build.run(
        {"as_of": "20251231", "symbols": ["600001.SH"]},
        {"materialize": True, "output_path": str(parquet_path)},
    )
    json_path.write_text(json.dumps(result, ensure_ascii=False, allow_nan=False), encoding="utf-8")

    assert result["counts"] == {"pass": 1, "fail": 0, "insufficient_data": 0}
    assert result["selected_symbols"] == ["600001.SH"]

    json_report = validate_result(json.loads(json_path.read_text(encoding="utf-8")))
    assert json_report["status"] == "PASS"
    assert json_report["record_count"] == 1

    frame = pd.read_parquet(parquet_path)
    assert frame.loc[0, "symbol"] == "600001.SH"
    assert frame.loc[0, "signal"] == "buy"
    assert frame.loc[0, "status"] == "pass"

    parquet_report = validate_production(frame)
    assert parquet_report["status"] == "PASS"
    assert parquet_report["record_count"] == 1
