from __future__ import annotations

import pandas as pd
import pytest

from lavine_buffett import service
from lavine_buffett.materialize import production_frame, write_production
from scripts import build
from scripts.build import load_symbols_file


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


def test_service_metadata_and_materialized_provenance(monkeypatch):
    monkeypatch.setattr(service.panda_client, "fetch_reports", lambda *args, **kwargs: reports())
    monkeypatch.setattr(
        service.panda_client, "fetch_latest_prices",
        lambda *args, **kwargs: {"600001.SH": {"date": "20251231", "close": 40.0}},
    )
    monkeypatch.setattr(
        service.panda_client, "fetch_industries",
        lambda *args, **kwargs: {"600001.SH": {"industry_code": "801120", "industry_name": "Food"}},
    )
    monkeypatch.setattr(service.panda_client, "ensure_authenticated", lambda: None)
    monkeypatch.setattr(
        service.panda_client, "runtime_versions",
        lambda: {"panda_data": "test-sdk", "pandas": "test", "numpy": "test", "pyarrow": "test"},
    )

    result = service.screen(as_of="20251231", symbols=["600001.SH"])
    assert result["counts"] == {"pass": 1, "fail": 0, "insufficient_data": 0}
    assert result["diagnostics"]["industry_coverage"] == 1
    assert result["diagnostics"]["price_evidence_coverage"] == 1
    assert result["dataset_version"].startswith("20251231-")
    assert len(result["rule_config_hash"]) == 64
    frame = production_frame(result)
    assert frame.loc[0, "data_version"] == result["dataset_version"]
    assert frame.loc[0, "run_id"] == result["run_id"]
    assert frame.loc[0, "data_sdk_version"] == "test-sdk"
    assert "diagnostics" in frame.loc[0, "run_metadata_json"]


def test_load_symbols_file_supports_csv_and_text(tmp_path):
    csv_path = tmp_path / "symbols.csv"
    csv_path.write_text("symbol\n600519.SH\n000001.SZ\n", encoding="utf-8")
    text_path = tmp_path / "symbols.txt"
    text_path.write_text("600519.SH\n\n000001.SZ\n", encoding="utf-8")
    assert load_symbols_file(csv_path) == ["600519.SH", "000001.SZ"]
    assert load_symbols_file(text_path) == ["600519.SH", "000001.SZ"]


def test_production_write_upserts_other_dates(tmp_path):
    path = tmp_path / "database.parquet"
    first = pd.DataFrame([{"trade_date": "20241231", "factor_id": "Q44", "symbol": "A", "value": 1}])
    second = pd.DataFrame([{"trade_date": "20251231", "factor_id": "Q44", "symbol": "A", "value": 2}])
    write_production(first, path)
    write_production(second, path)
    result = pd.read_parquet(path).sort_values("trade_date")
    assert result["value"].tolist() == [1, 2]


def test_partial_run_cannot_overwrite_canonical_database(monkeypatch, tmp_path):
    monkeypatch.setattr(build, "screen", lambda **kwargs: {"records": []})
    with pytest.raises(ValueError, match="partial universes"):
        build.run(
            {"as_of": "20251231", "symbols": ["600519.SH"], "all_a": False},
            {"materialize": True, "output_path": tmp_path / "database.parquet"},
        )


def test_invalid_symbol_returns_value_error():
    with pytest.raises(ValueError, match="unsupported A-share symbols"):
        service._validate_symbols([None, "600519.SH"])
