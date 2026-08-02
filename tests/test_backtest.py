from __future__ import annotations

import pytest

from lavine_buffett.backtest import analyze_snapshots


def snapshot(date: str, selected: set[str]) -> dict:
    return {
        "as_of": date,
        "records": [
            {
                "symbol": symbol,
                "selected": symbol in selected,
                "metrics": {"current_return": value},
            }
            for symbol, value in zip(["A", "B", "C", "D", "E"], [0.20, 0.18, 0.16, 0.14, 0.12])
        ],
    }


def test_backtest_reports_ic_layers_turnover_and_costs():
    snapshots = [
        snapshot("20201231", {"A", "B"}),
        snapshot("20211231", {"A", "C"}),
        snapshot("20221231", {"C", "D"}),
    ]

    def returns(symbols, start, end):
        return dict(zip(symbols, [0.20, 0.15, 0.10, 0.05, 0.00]))

    result = analyze_snapshots(snapshots, returns)
    assert len(result["periods"]) == 2
    assert result["periods"][0]["rank_ic"] == pytest.approx(1.0)
    assert set(result["periods"][0]["layer_returns"]) == {"Q1", "Q2", "Q3", "Q4", "Q5"}
    assert result["metrics"]["average_turnover"] > 0
    assert result["periods"][0]["turnover"] == pytest.approx(1.0)
    assert result["periods"][1]["turnover"] == pytest.approx(0.5)
    assert result["periods"][0]["net_return"] < result["periods"][0]["gross_return"]


def test_backtest_fails_when_selected_symbol_has_no_forward_return():
    snapshots = [snapshot("20201231", {"A"}), snapshot("20211231", {"A"})]

    with pytest.raises(ValueError, match="missing forward returns.*A"):
        analyze_snapshots(snapshots, lambda symbols, start, end: {"B": 0.1})


def test_first_period_loss_is_included_in_max_drawdown():
    snapshots = [snapshot("20201231", {"A"}), snapshot("20211231", {"A"})]
    result = analyze_snapshots(
        snapshots,
        lambda symbols, start, end: {symbol: -0.5 for symbol in symbols},
        round_trip_cost=0.0,
    )
    assert result["metrics"]["max_drawdown"] == pytest.approx(-0.5)
