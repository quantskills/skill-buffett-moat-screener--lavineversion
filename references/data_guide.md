# PandaData Field Guide

| Internal metric | PandaData evidence | Formula |
|---|---|---|
| parent net profit | `is_n_income_attr_p` | reported value |
| ROE | profit + `bs_total_hldr_eqy_exc_min_int` | profit / average current and prior-year parent equity |
| ROA | profit + `bs_total_assets` | profit / average current and prior-year total assets |
| gross margin | `is_gross_profit`, `is_revenue` | gross profit / revenue |
| CapEx ratio | `cfs_cash_paid_asset` | absolute CapEx / positive parent profit |
| long-term debt ratio | `bs_lt_borr`, `bs_bond_payable`, `bs_ncl_due_1y` | sum / positive parent profit |
| TTM PE | `is_basic_eps`, `get_stock_daily.close` | latest unadjusted close / PIT TTM basic EPS |

The verified one-year-due field is `bs_ncl_due_1y`; `bs_non_cur_liab_due_1y` is present in the SDK schema but returned no usable values in the 2025-12-31 evidence probe. Debt is the sum of available numeric values across the three verified columns. If all three are null, debt remains missing rather than being inferred as zero.

TTM EPS for Q1-Q3 is current YTD EPS plus prior annual EPS minus prior same-quarter YTD EPS. Q4 uses annual EPS directly. Every component must be visible by the decision date.

`get_fina_reports` accepts at most 20 quarters per call, so the client partitions history into five-year windows. Percentages are normalized to decimal ratios in the rule engine.

Report `date`, price `date`, industry `in_date/out_date`, and listing/delisting dates are parsed as calendar dates before point-in-time filtering. Invalid dates are excluded rather than compared as strings.

The report request uses `is_latest=False`. `if_adjusted` must be 0 or 1 and is retained as evidence: later filings can restate comparative periods, so historical reconstruction selects the last version actually visible at each decision date.
