# Methodology Freeze

Rules version: `1.2.0`.

- Ten annual return observations require eleven consecutive annual balance-sheet dates.
- The window ends at the latest annual report visible on the decision date.
- Gross-margin volatility is population standard deviation (`numpy.std(..., ddof=0)`) over the same ten years.
- `>=` applies to return and margin floors. `<` applies to volatility, CapEx/profit, debt/profit and PE ceilings.
- Missing, non-finite, nonpositive-denominator and conflicting-latest-version evidence fails closed.
- Announcement and price evidence dates must be valid calendar dates. Empty or invalid dates are never treated as visible.
- `if_adjusted=0` identifies the filing's current-period value and `if_adjusted=1` a comparative value restated by a later filing. The latest visible version is used and adjustment flags remain in output evidence.
- Missing industry membership is `insufficient_data`; an unknown industry is never assumed to be non-bank.
- A company with incomplete evidence is `insufficient_data`, not an ordinary rule failure.
- Selected names are ranked by the latest applicable return metric after all hard gates pass.

The bank branch is a Lavine-specific economic interpretation. It uses latest ROA >= 1% and a ten-year ROA floor >= 0.6%. Gross margin, industrial CapEx and corporate long-term-debt ratios are marked `N/A`; positive profit and TTM PE remain applicable.

Version 1.1.0 replaced set-Jaccard turnover with equal-weight one-way turnover in annual diagnostics and fails when any selected symbol lacks a finite forward return.

Version 1.2.0 separates known rule failures from missing evidence. Nonpositive profit or EPS is `fail`; missing raw fields are `insufficient_data`. Debt uses the verified `bs_ncl_due_1y` field and all-null debt evidence remains missing. The initial portfolio value is included in drawdown calculations.
