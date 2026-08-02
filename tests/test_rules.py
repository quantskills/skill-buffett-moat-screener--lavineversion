from __future__ import annotations

import pandas as pd
import pytest

from lavine_buffett.config import RuleConfig
from lavine_buffett.rules import evaluate_symbol, select_visible_revisions


SYMBOL = "600001.SH"


def reports(*, margin_values: list[float] | None = None, bank: bool = False) -> pd.DataFrame:
    margins = margin_values or [0.45] * 11
    rows = []
    for offset, year in enumerate(range(2014, 2025)):
        assets = 100.0 if bank else 200.0
        profit = 16.0 if bank else 16.0
        rows.append(
            {
                "symbol": SYMBOL,
                "quarter": f"{year}q4",
                "date": f"{year + 1}0430",
                "if_adjusted": 0,
                "is_n_income_attr_p": profit,
                "bs_total_hldr_eqy_exc_min_int": 100.0,
                "bs_total_assets": assets,
                "is_gross_profit": margins[offset] * 100.0,
                "is_revenue": 100.0,
                "cfs_cash_paid_asset": 4.0,
                "bs_lt_borr": 20.0,
                "bs_bond_payable": 10.0,
                "bs_ncl_due_1y": 5.0,
                "is_basic_eps": 2.0,
            }
        )
    return pd.DataFrame(rows)


def evaluate(frame: pd.DataFrame, *, bank: bool = False, price: float = 40.0):
    visible, conflicts = select_visible_revisions(frame, "20251231")
    industry = {"industry_code": "801780" if bank else "801120", "industry_name": "Bank" if bank else "Food"}
    return evaluate_symbol(SYMBOL, visible, {"date": "20251231", "close": price}, industry, conflicts)


def test_complete_non_bank_passes_all_hard_rules():
    result = evaluate(reports())
    assert result["status"] == "pass"
    assert result["coverage_years"] == list(range(2015, 2025))
    assert result["metrics"]["pe_ttm"] == pytest.approx(20.0)
    assert all(result["checks"].values())


def test_bank_uses_roa_instead_of_roe():
    result = evaluate(reports(bank=True), bank=True)
    assert result["return_metric"] == "roa"
    assert result["metrics"]["current_return"] == pytest.approx(0.16)
    assert result["checks"]["gross_margin"] is None
    assert result["checks"]["debt_to_profit"] is None


def test_missing_balance_year_fails_closed():
    frame = reports()
    frame = frame[frame["quarter"] != "2019q4"]
    result = evaluate(frame)
    assert result["status"] == "insufficient_data"
    assert "non_contiguous_annual_history" in result["insufficient_reasons"]


@pytest.mark.parametrize(
    ("field", "value", "failed_check"),
    [
        ("cfs_cash_paid_asset", 4.8, "capex_to_profit"),
        ("bs_lt_borr", 49.0, "debt_to_profit"),
    ],
)
def test_strict_ratio_boundaries_fail(field: str, value: float, failed_check: str):
    frame = reports()
    frame.loc[frame["quarter"] == "2024q4", field] = value
    result = evaluate(frame)
    assert result["status"] == "fail"
    assert result["checks"][failed_check] is False


def test_pe_equal_to_25_fails():
    result = evaluate(reports(), price=50.0)
    assert result["status"] == "fail"
    assert result["checks"]["pe"] is False


def test_latest_same_day_conflict_is_insufficient():
    frame = reports()
    duplicate = frame.iloc[-1].copy()
    duplicate["is_n_income_attr_p"] = 99.0
    frame = pd.concat([frame, duplicate.to_frame().T], ignore_index=True)
    result = evaluate(frame)
    assert result["status"] == "insufficient_data"
    assert result["conflicting_quarters"] == ["2024q4"]


def test_future_revision_is_not_visible():
    frame = reports()
    future = frame.iloc[-1].copy()
    future["date"] = "20260101"
    future["is_n_income_attr_p"] = 1.0
    visible, _ = select_visible_revisions(pd.concat([frame, future.to_frame().T]), "20251231")
    latest = visible[visible["quarter"] == "2024q4"].iloc[0]
    assert float(latest["is_n_income_attr_p"]) == 16.0


def test_missing_industry_fails_closed():
    visible, conflicts = select_visible_revisions(reports(), "20251231")
    result = evaluate_symbol(SYMBOL, visible, {"date": "20251231", "close": 40.0}, None, conflicts)
    assert result["status"] == "insufficient_data"
    assert "missing_industry" in result["insufficient_reasons"]


def test_invalid_and_missing_dates_are_not_visible():
    frame = reports()
    frame.loc[frame["quarter"] == "2024q4", "date"] = "not-a-date"
    visible, _ = select_visible_revisions(frame, "20251231")
    assert "2024q4" not in set(visible["quarter"])


def test_latest_adjusted_comparative_version_is_selected_and_recorded():
    frame = reports()
    revised = frame.iloc[-2].copy()
    revised["date"] = "20250501"
    revised["if_adjusted"] = 1
    revised["is_n_income_attr_p"] = 18.0
    visible, conflicts = select_visible_revisions(pd.concat([frame, revised.to_frame().T]), "20251231")
    chosen = visible[visible["quarter"] == revised["quarter"]].iloc[0]
    assert int(chosen["if_adjusted"]) == 1
    assert float(chosen["is_n_income_attr_p"]) == 18.0
    result = evaluate_symbol(
        SYMBOL, visible, {"date": "20251231", "close": 40.0},
        {"industry_code": "801120", "industry_name": "Food"}, conflicts,
    )
    assert result["report_adjustment_flags"] == [0, 1]


def test_invalid_price_date_fails_closed():
    visible, conflicts = select_visible_revisions(reports(), "20251231")
    result = evaluate_symbol(
        SYMBOL, visible, {"date": "bad-date", "close": 40.0},
        {"industry_code": "801120", "industry_name": "Food"}, conflicts,
    )
    assert result["status"] == "insufficient_data"
    assert "invalid_price_date" in result["insufficient_reasons"]


def test_nonpositive_profit_is_rule_failure_not_missing_data():
    frame = reports()
    latest = frame["quarter"].eq("2024q4")
    frame.loc[latest, "is_n_income_attr_p"] = -1.0
    visible, conflicts = select_visible_revisions(frame, "20251231")
    result = evaluate_symbol(
        SYMBOL, visible, {"date": "20251231", "close": 40.0},
        {"industry_code": "801120", "industry_name": "Food"}, conflicts,
    )
    assert result["status"] == "fail"
    assert result["checks"]["positive_net_profit"] is False
    assert result["checks"]["capex_to_profit"] is None
    assert "missing_capex_to_profit" not in result["insufficient_reasons"]
    assert "missing_debt_to_profit" not in result["insufficient_reasons"]


def test_nonpositive_ttm_eps_is_rule_failure_not_missing_data():
    frame = reports()
    frame.loc[frame["quarter"].eq("2024q4"), "is_basic_eps"] = -2.0
    visible, conflicts = select_visible_revisions(frame, "20251231")
    result = evaluate_symbol(
        SYMBOL, visible, {"date": "20251231", "close": 40.0},
        {"industry_code": "801120", "industry_name": "Food"}, conflicts,
    )
    assert result["status"] == "fail"
    assert result["checks"]["positive_pe"] is False
    assert "missing_ttm_pe" not in result["insufficient_reasons"]


def test_all_null_debt_is_insufficient_not_zero():
    frame = reports()
    latest = frame["quarter"].eq("2024q4")
    frame.loc[latest, ["bs_lt_borr", "bs_bond_payable", "bs_ncl_due_1y"]] = None
    visible, conflicts = select_visible_revisions(frame, "20251231")
    result = evaluate_symbol(
        SYMBOL, visible, {"date": "20251231", "close": 40.0},
        {"industry_code": "801120", "industry_name": "Food"}, conflicts,
    )
    assert result["status"] == "insufficient_data"
    assert result["checks"]["debt_to_profit"] is None
    assert "missing_debt_to_profit" in result["insufficient_reasons"]


def test_ttm_eps_uses_point_in_time_ytd_bridge():
    frame = reports()
    extras = pd.DataFrame(
        [
            {**frame.iloc[-1].to_dict(), "quarter": "2025q2", "date": "20250830", "is_basic_eps": 1.2},
            {**frame.iloc[-1].to_dict(), "quarter": "2024q2", "date": "20240830", "is_basic_eps": 0.8},
        ]
    )
    result = evaluate(pd.concat([frame, extras], ignore_index=True), price=48.0)
    assert result["metrics"]["ttm_eps"] == pytest.approx(2.4)
    assert result["metrics"]["pe_ttm"] == pytest.approx(20.0)


def test_margin_volatility_equal_to_limit_fails():
    config = RuleConfig(gross_margin_volatility_max=0.10)
    frame = reports(margin_values=[0.45] + [0.35, 0.55] * 5)
    visible, conflicts = select_visible_revisions(frame, "20251231")
    result = evaluate_symbol(
        SYMBOL,
        visible,
        {"date": "20251231", "close": 40.0},
        {"industry_code": "801120"},
        conflicts,
        config,
    )
    assert result["metrics"]["gross_margin_volatility"] == pytest.approx(0.10)
    assert result["checks"]["gross_margin_volatility"] is False
