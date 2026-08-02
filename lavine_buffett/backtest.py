from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Callable

import numpy as np
import pandas as pd


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def analyze_snapshots(
    snapshots: list[dict[str, Any]],
    return_loader: Callable[[list[str], str, str], dict[str, float]],
    *,
    round_trip_cost: float = 0.003,
) -> dict[str, Any]:
    """Analyze annual point-in-time snapshots without changing their evidence."""
    if len(snapshots) < 2:
        raise ValueError("backtest requires at least two signal snapshots")
    snapshots = sorted(snapshots, key=lambda item: item["as_of"])
    periods: list[dict[str, Any]] = []
    previous_selected: set[str] = set()
    for current, following in zip(snapshots, snapshots[1:]):
        records = current["records"]
        symbols = [record["symbol"] for record in records]
        forward = return_loader(symbols, current["as_of"], following["as_of"])
        requested_selected = {record["symbol"] for record in records if record["selected"]}
        missing_selected_returns = sorted(
            symbol for symbol in requested_selected if _finite(forward.get(symbol)) is None
        )
        if missing_selected_returns:
            raise ValueError(
                f"missing forward returns for selected symbols {current['as_of']}: "
                + ", ".join(missing_selected_returns)
            )
        rows = []
        for record in records:
            value = _finite(record["metrics"].get("current_return"))
            future_return = _finite(forward.get(record["symbol"]))
            if value is None or future_return is None:
                continue
            rows.append(
                {
                    "symbol": record["symbol"],
                    "factor_value": value,
                    "forward_return": future_return,
                    "selected": bool(record["selected"]),
                }
            )
        panel = pd.DataFrame(rows)
        ic = None
        rank_ic = None
        layers: dict[str, float] = {}
        if (len(panel) >= 3 and panel["factor_value"].nunique() > 1
                and panel["forward_return"].nunique() > 1):
            ic_value = panel["factor_value"].corr(panel["forward_return"], method="pearson")
            rank_value = panel["factor_value"].rank().corr(panel["forward_return"].rank())
            ic = None if pd.isna(ic_value) else float(ic_value)
            rank_ic = None if pd.isna(rank_value) else float(rank_value)
        if len(panel) >= 5 and panel["factor_value"].nunique() >= 5:
            panel["layer"] = pd.qcut(panel["factor_value"], 5, labels=False, duplicates="drop")
            layers = {
                f"Q{int(layer) + 1}": float(group["forward_return"].mean())
                for layer, group in panel.groupby("layer", observed=True)
            }
        selected = set(panel.loc[panel["selected"], "symbol"])
        selected_returns = panel.loc[panel["selected"], "forward_return"]
        gross_return = float(selected_returns.mean()) if not selected_returns.empty else 0.0
        if not previous_selected and selected:
            turnover = 1.0
        elif previous_selected or selected:
            previous_weight = 1.0 / len(previous_selected) if previous_selected else 0.0
            selected_weight = 1.0 / len(selected) if selected else 0.0
            turnover = 0.5 * sum(
                abs((selected_weight if symbol in selected else 0.0)
                    - (previous_weight if symbol in previous_selected else 0.0))
                for symbol in previous_selected | selected
            )
        else:
            turnover = 0.0
        net_return = gross_return - turnover * round_trip_cost
        periods.append(
            {
                "signal_date": current["as_of"],
                "exit_date": following["as_of"],
                "observations": len(panel),
                "universe_records": len(records),
                "forward_return_coverage": len(panel) / len(records) if records else 0.0,
                "selected_count": len(selected),
                "selected_symbols": sorted(selected),
                "ic": ic,
                "rank_ic": rank_ic,
                "layer_returns": layers,
                "gross_return": gross_return,
                "turnover": turnover,
                "net_return": net_return,
            }
        )
        previous_selected = selected

    net_returns = np.array([period["net_return"] for period in periods], dtype=float)
    equity = np.concatenate(([1.0], np.cumprod(1.0 + net_returns)))
    peaks = np.maximum.accumulate(equity)
    drawdowns = equity / peaks - 1.0
    ic_values = np.array([period["ic"] for period in periods if period["ic"] is not None], dtype=float)
    rank_values = np.array([period["rank_ic"] for period in periods if period["rank_ic"] is not None], dtype=float)
    split = max(1, int(len(periods) * 0.7))
    first_date = datetime.strptime(periods[0]["signal_date"], "%Y%m%d")
    last_date = datetime.strptime(periods[-1]["exit_date"], "%Y%m%d")
    elapsed_years = (last_date - first_date).days / 365.25

    def compounded(values: np.ndarray) -> float | None:
        return float(np.prod(1.0 + values) - 1.0) if len(values) else None

    return {
        "periods": periods,
        "metrics": {
            "cumulative_return": compounded(net_returns),
            "annualized_return": float(equity[-1] ** (1 / elapsed_years) - 1)
            if elapsed_years > 0 and equity[-1] > 0 else None,
            "max_drawdown": float(drawdowns.min()) if len(drawdowns) else None,
            "average_turnover": float(np.mean([period["turnover"] for period in periods])),
            "ic_mean": float(ic_values.mean()) if len(ic_values) else None,
            "icir": float(ic_values.mean() / ic_values.std(ddof=1))
            if len(ic_values) > 1 and ic_values.std(ddof=1) > 0
            else None,
            "rank_ic_mean": float(rank_values.mean()) if len(rank_values) else None,
            "in_sample_return": compounded(net_returns[:split]),
            "out_of_sample_return": compounded(net_returns[split:]),
            "round_trip_cost": round_trip_cost,
        },
        "limitations": [
            "Annual snapshots provide low-frequency diagnostics, not execution-ready evidence.",
            "IC uses the applicable ROE/ROA return metric; bank and non-bank scales differ.",
            "IC excludes names without a complete point-in-time factor and forward-price pair; coverage is reported.",
            "A selected symbol without a finite forward return fails the diagnostic instead of being silently dropped.",
        ],
    }
