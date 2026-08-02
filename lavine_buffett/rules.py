from __future__ import annotations

import math
import re
from datetime import datetime
from typing import Any, Mapping

import numpy as np
import pandas as pd

from .config import BANK_INDUSTRY_CODE, RuleConfig


_QUARTER_RE = re.compile(r"^(\d{4})q([1-4])$", re.I)


def clean_symbol(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    symbol = str(value).strip().upper()
    return symbol[:-3] + ".SH" if symbol.endswith(".SS") else symbol


def clean_date(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    if re.fullmatch(r"\d{8}", text):
        cleaned = text
    elif re.match(r"^\d{4}-\d{2}-\d{2}", text):
        cleaned = text[:10].replace("-", "")
    else:
        return ""
    try:
        datetime.strptime(cleaned, "%Y%m%d")
    except ValueError:
        return ""
    return cleaned


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _quarter_key(value: Any) -> tuple[int, int] | None:
    match = _QUARTER_RE.match(str(value).strip())
    return (int(match.group(1)), int(match.group(2))) if match else None


def select_visible_revisions(
    frame: pd.DataFrame, as_of: str
) -> tuple[pd.DataFrame, set[tuple[str, str]]]:
    """Select the last report version visible by ``as_of``.

    Conflicting rows published on the same latest date are reported separately
    so the caller can fail closed instead of selecting one arbitrarily.
    """
    required = {"symbol", "quarter", "date", "if_adjusted"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"financial reports missing columns: {sorted(missing)}")
    work = frame.copy()
    work["symbol"] = work["symbol"].map(clean_symbol)
    work["quarter"] = work["quarter"].astype(str).str.lower()
    work["date"] = work["date"].map(clean_date)
    work["if_adjusted"] = pd.to_numeric(work["if_adjusted"], errors="coerce").astype("Int64")
    work = work[
        work["symbol"].notna()
        & work["quarter"].str.match(r"^\d{4}q[1-4]$")
        & work["date"].ne("")
        & (work["date"] <= clean_date(as_of))
    ].drop_duplicates()
    if work.empty:
        return work.reset_index(drop=True), set()

    keys = ["symbol", "quarter"]
    work = work.sort_values(keys + ["date"], kind="stable")
    latest_date = work.groupby(keys, sort=False)["date"].transform("max")
    latest = work[work["date"].eq(latest_date)].copy()
    conflicts: set[tuple[str, str]] = set()
    value_columns = [column for column in latest.columns if column not in keys + ["date"]]
    for key, group in latest.groupby(keys, sort=False):
        if value_columns and group[value_columns].nunique(dropna=False).gt(1).any():
            conflicts.add((str(key[0]), str(key[1])))
    selected = latest.drop_duplicates(keys, keep="last").reset_index(drop=True)
    return selected, conflicts


def _series_value(row: pd.Series, name: str) -> float | None:
    return _number(row[name]) if name in row else None


def _ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return numerator / denominator


def _annual_metrics(
    annual: pd.DataFrame, latest_year: int, years: int
) -> tuple[list[dict[str, Any]], list[int]]:
    indexed = {int(row["year"]): row for _, row in annual.iterrows()}
    required_balance_years = list(range(latest_year - years, latest_year + 1))
    missing_years = [year for year in required_balance_years if year not in indexed]
    if missing_years:
        return [], missing_years

    metrics: list[dict[str, Any]] = []
    for year in range(latest_year - years + 1, latest_year + 1):
        row = indexed[year]
        previous = indexed[year - 1]
        profit = _series_value(row, "is_n_income_attr_p")
        equity = _series_value(row, "bs_total_hldr_eqy_exc_min_int")
        previous_equity = _series_value(previous, "bs_total_hldr_eqy_exc_min_int")
        assets = _series_value(row, "bs_total_assets")
        previous_assets = _series_value(previous, "bs_total_assets")
        gross_profit = _series_value(row, "is_gross_profit")
        revenue = _series_value(row, "is_revenue")
        average_equity = None if equity is None or previous_equity is None else (equity + previous_equity) / 2
        average_assets = None if assets is None or previous_assets is None else (assets + previous_assets) / 2
        metrics.append(
            {
                "year": year,
                "announce_date": str(row["date"]),
                "roe": _ratio(profit, average_equity),
                "roa": _ratio(profit, average_assets),
                "gross_margin": _ratio(gross_profit, revenue),
            }
        )
    return metrics, []


def _ttm_eps(quarterly: pd.DataFrame) -> tuple[float | None, list[str]]:
    if quarterly.empty:
        return None, []
    work = quarterly.copy()
    work["_key"] = work["quarter"].map(_quarter_key)
    work = work[work["_key"].notna()].sort_values("_key")
    if work.empty:
        return None, []
    by_quarter = {str(row["quarter"]): row for _, row in work.iterrows()}
    latest = work.iloc[-1]
    year, quarter = latest["_key"]
    current_eps = _series_value(latest, "is_basic_eps")
    if current_eps is None:
        return None, []
    if quarter == 4:
        return current_eps, [str(latest["date"])]
    previous_annual = by_quarter.get(f"{year - 1}q4")
    previous_same = by_quarter.get(f"{year - 1}q{quarter}")
    if previous_annual is None or previous_same is None:
        return None, []
    annual_eps = _series_value(previous_annual, "is_basic_eps")
    prior_ytd_eps = _series_value(previous_same, "is_basic_eps")
    if annual_eps is None or prior_ytd_eps is None:
        return None, []
    return (
        current_eps + annual_eps - prior_ytd_eps,
        [str(latest["date"]), str(previous_annual["date"]), str(previous_same["date"])],
    )


def _debt(row: pd.Series) -> float | None:
    fields = ("bs_lt_borr", "bs_bond_payable", "bs_ncl_due_1y")
    if not all(field in row.index for field in fields):
        return None
    values = [_series_value(row, field) for field in fields]
    present = [value for value in values if value is not None]
    return sum(present) if present else None


def _is_bank(industry: Mapping[str, Any] | None) -> bool:
    industry = industry or {}
    code = str(industry.get("industry_code") or industry.get("l1_code") or "")
    name = str(industry.get("industry_name") or "")
    return code == BANK_INDUSTRY_CODE or bool(re.search(r"银行|bank", name, re.I))


def _industry_known(industry: Mapping[str, Any] | None) -> bool:
    industry = industry or {}
    return bool(str(industry.get("industry_code") or industry.get("l1_code") or "").strip()) or bool(
        str(industry.get("industry_name") or "").strip()
    )


def evaluate_symbol(
    symbol: str,
    reports: pd.DataFrame,
    price: Mapping[str, Any] | None,
    industry: Mapping[str, Any] | None,
    conflicts: set[tuple[str, str]] | None = None,
    config: RuleConfig | None = None,
) -> dict[str, Any]:
    config = config or RuleConfig()
    symbol = clean_symbol(symbol) or str(symbol)
    conflicts = conflicts or set()
    own_conflicts = sorted(quarter for item_symbol, quarter in conflicts if item_symbol == symbol)
    own = reports[reports["symbol"].map(clean_symbol).eq(symbol)].copy()
    own["_quarter_key"] = own["quarter"].map(_quarter_key)
    annual = own[own["quarter"].astype(str).str.endswith("q4")].copy()
    annual["year"] = annual["_quarter_key"].map(lambda value: value[0] if value else None)
    annual = annual.dropna(subset=["year"]).sort_values("year")

    insufficient: list[str] = []
    if not _industry_known(industry):
        insufficient.append("missing_industry")
    if own_conflicts:
        insufficient.append("conflicting_latest_revisions")
    if "if_adjusted" not in own or own["if_adjusted"].isna().any():
        insufficient.append("missing_adjustment_flag")
    elif not own["if_adjusted"].isin([0, 1]).all():
        insufficient.append("invalid_adjustment_flag")
    if annual.empty:
        insufficient.append("no_visible_annual_reports")
        latest_year = None
        annual_history: list[dict[str, Any]] = []
        missing_years: list[int] = []
        latest = None
    else:
        latest_year = int(annual["year"].max())
        annual_history, missing_years = _annual_metrics(annual, latest_year, config.history_years)
        if missing_years:
            insufficient.append("non_contiguous_annual_history")
        latest = annual[annual["year"].eq(latest_year)].iloc[-1]

    bank = _is_bank(industry)
    return_metric = "roa" if bank else "roe"
    return_values = [item[return_metric] for item in annual_history]
    margin_values = [item["gross_margin"] for item in annual_history]
    if annual_history and any(value is None for value in return_values):
        insufficient.append(f"missing_{return_metric}_history")
    if not bank and annual_history and any(value is None for value in margin_values):
        insufficient.append("missing_gross_margin_history")

    latest_profit = _series_value(latest, "is_n_income_attr_p") if latest is not None else None
    capex = _series_value(latest, "cfs_cash_paid_asset") if latest is not None else None
    debt = _debt(latest) if latest is not None else None
    capex_ratio = _ratio(abs(capex) if capex is not None else None, latest_profit)
    debt_ratio = _ratio(debt, latest_profit)
    ttm_eps, eps_dates = _ttm_eps(own)
    close = _number((price or {}).get("close"))
    price_date = clean_date((price or {}).get("date"))
    if price and not price_date:
        insufficient.append("invalid_price_date")
    pe = close / ttm_eps if close is not None and ttm_eps not in (None, 0) else None

    if latest_profit is None:
        insufficient.append("missing_positive_net_profit")
    if ttm_eps is None or close is None:
        insufficient.append("missing_ttm_pe")
    if not bank and latest_profit is not None and latest_profit > 0:
        if capex is None:
            insufficient.append("missing_capex_to_profit")
        if debt is None:
            insufficient.append("missing_debt_to_profit")

    current_return = return_values[-1] if return_values and all(value is not None for value in return_values) else None
    return_floor = min(return_values) if return_values and all(value is not None for value in return_values) else None
    latest_margin = margin_values[-1] if margin_values and all(value is not None for value in margin_values) else None
    margin_volatility = (
        float(np.std(margin_values, ddof=0))
        if margin_values and all(value is not None for value in margin_values)
        else None
    )
    return_current_min = config.bank_current_roa_min if bank else config.current_return_min
    return_floor_min = config.bank_historical_roa_floor if bank else config.historical_return_floor
    capex_check = None
    debt_check = None
    if not bank and latest_profit is not None and latest_profit > 0:
        capex_check = None if capex_ratio is None else capex_ratio < config.capex_to_profit_max
        debt_check = None if debt_ratio is None else debt_ratio < config.debt_to_profit_max
    positive_pe_check = None if ttm_eps is None or close is None else ttm_eps > 0 and close > 0
    pe_check = None if pe is None or pe <= 0 else pe < config.pe_max
    checks: dict[str, bool | None] = {
        "current_return": None if current_return is None else current_return >= return_current_min,
        "historical_return_floor": None if return_floor is None else return_floor >= return_floor_min,
        "gross_margin": None if bank or latest_margin is None else latest_margin >= config.gross_margin_min,
        "gross_margin_volatility": None
        if bank or margin_volatility is None
        else margin_volatility < config.gross_margin_volatility_max,
        "positive_net_profit": None if latest_profit is None else latest_profit > 0,
        "capex_to_profit": capex_check,
        "debt_to_profit": debt_check,
        "positive_pe": positive_pe_check,
        "pe": pe_check,
    }
    insufficient = sorted(set(insufficient))
    applicable_checks = {name: value for name, value in checks.items() if value is not None}
    status = "insufficient_data" if insufficient else "pass" if all(applicable_checks.values()) else "fail"
    return {
        "symbol": symbol,
        "status": status,
        "selected": status == "pass",
        "is_bank": bank,
        "return_metric": return_metric,
        "latest_fiscal_year": latest_year,
        "coverage_years": [item["year"] for item in annual_history],
        "missing_balance_years": missing_years,
        "announce_dates": [item["announce_date"] for item in annual_history],
        "valuation_evidence_dates": eps_dates + ([price_date] if price_date else []),
        "report_adjustment_flags": sorted({int(value) for value in own.get("if_adjusted", []) if pd.notna(value)}),
        "metrics": {
            "current_return": current_return,
            "historical_return_floor": return_floor,
            "latest_gross_margin": latest_margin,
            "gross_margin_volatility": margin_volatility,
            "latest_net_profit": latest_profit,
            "capex_to_profit": capex_ratio,
            "debt_to_profit": debt_ratio,
            "ttm_eps": ttm_eps,
            "close": close,
            "pe_ttm": pe,
        },
        "checks": checks,
        "applicable_checks": sorted(applicable_checks),
        "insufficient_reasons": insufficient,
        "conflicting_quarters": own_conflicts,
    }
