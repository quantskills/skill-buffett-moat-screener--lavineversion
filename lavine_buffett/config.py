from __future__ import annotations

from dataclasses import dataclass


RULES_VERSION = "1.2.0"
SCHEMA_VERSION = "1.2.0"
SKILL_ID = "Q44-LAVINE"
SKILL_NAME = "Buffett Moat Screener - Lavine Version"


@dataclass(frozen=True)
class RuleConfig:
    history_years: int = 10
    current_return_min: float = 0.15
    historical_return_floor: float = 0.12
    gross_margin_min: float = 0.40
    gross_margin_volatility_max: float = 0.10
    capex_to_profit_max: float = 0.30
    debt_to_profit_max: float = 4.0
    pe_max: float = 25.0
    bank_current_roa_min: float = 0.01
    bank_historical_roa_floor: float = 0.006


REPORT_FIELDS = [
    "symbol",
    "quarter",
    "date",
    "if_adjusted",
    "is_n_income_attr_p",
    "bs_total_hldr_eqy_exc_min_int",
    "bs_total_assets",
    "is_gross_profit",
    "is_revenue",
    "cfs_cash_paid_asset",
    "bs_lt_borr",
    "bs_bond_payable",
    "bs_ncl_due_1y",
    "is_basic_eps",
]

BANK_INDUSTRY_CODE = "801780"
