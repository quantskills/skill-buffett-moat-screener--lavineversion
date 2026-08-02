from __future__ import annotations

import pandas as pd
import pytest
from concurrent.futures import ThreadPoolExecutor
import time

from lavine_buffett import panda_client


def test_fetch_reports_respects_symbol_and_five_year_windows(monkeypatch):
    calls = []

    def fake_fetch(name, **kwargs):
        calls.append((name, kwargs))
        return pd.DataFrame()

    monkeypatch.setattr(panda_client, "fetch", fake_fetch)
    panda_client.fetch_reports([f"{index:06d}.SZ" for index in range(21)], "20251231", years=6)
    assert len(calls) == 4
    assert all(name == "get_fina_reports" for name, _ in calls)
    assert all(kwargs["is_latest"] is False for _, kwargs in calls)
    for _, kwargs in calls:
        start_year = int(kwargs["start_quarter"][:4])
        end_year = int(kwargs["end_quarter"][:4])
        assert end_year - start_year <= 4
        assert len(kwargs["symbol"]) <= 20


def test_fetch_industries_uses_assignment_valid_at_as_of(monkeypatch):
    constituents = pd.DataFrame([
        {"stock_symbol": "000001.SZ", "l1_code": "OLD", "in_date": "20100101", "out_date": "20200101"},
        {"stock_symbol": "000001.SZ", "l1_code": "801780", "in_date": "20200101", "out_date": None},
        {"stock_symbol": "000002.SZ", "l1_code": "FUTURE", "in_date": "20260101", "out_date": None},
        {"stock_symbol": "000003.SZ", "l1_code": "BAD", "in_date": "bad-date", "out_date": None},
        {"stock_symbol": "000004.SZ", "l1_code": "ONE", "in_date": "20200101", "out_date": None},
        {"stock_symbol": "000004.SZ", "l1_code": "TWO", "in_date": "20210101", "out_date": None},
    ])
    details = pd.DataFrame([
        {"industry_code": "801780", "industry_name": "Bank"},
        {"industry_code": "OLD", "industry_name": "Old"},
    ])

    def fake_fetch(name, **kwargs):
        return details if name == "get_industry_detail" else constituents

    monkeypatch.setattr(panda_client, "fetch", fake_fetch)
    result = panda_client.fetch_industries(["000001.SZ", "000002.SZ", "000003.SZ"], "20251231")
    assert result == {"000001.SZ": {"industry_code": "801780", "industry_name": "Bank"}}


def test_discover_all_a_is_point_in_time_and_requires_listing_date(monkeypatch):
    details = pd.DataFrame([
        {"symbol": "000001.SZ", "listed_date": "19910403", "de_listed_date": None},
        {"symbol": "600001.SH", "listed_date": "20260101", "de_listed_date": None},
        {"symbol": "000003.SZ", "listed_date": "20000101", "de_listed_date": "20240101"},
        {"symbol": "000004.SZ", "listed_date": None, "de_listed_date": None},
        {"symbol": "HK0001.HK", "listed_date": "20000101", "de_listed_date": None},
    ])
    monkeypatch.setattr(panda_client, "fetch", lambda *args, **kwargs: details)
    assert panda_client.discover_all_a("20251231") == ["000001.SZ"]


def test_price_loaders_reject_invalid_dates(monkeypatch):
    prices = pd.DataFrame([
        {"symbol": "000001.SZ", "date": "bad", "close": 99.0},
        {"symbol": "000001.SZ", "date": "20250102", "close": 10.0},
        {"symbol": "000001.SZ", "date": "20251231", "close": 12.0},
    ])
    monkeypatch.setattr(panda_client, "fetch", lambda *args, **kwargs: prices)
    latest = panda_client.fetch_latest_prices(["000001.SZ"], "20251231")
    assert latest["000001.SZ"] == {"date": "20251231", "close": 12.0}
    returns = panda_client.fetch_forward_returns(["000001.SZ"], "20250101", "20251231")
    assert returns["000001.SZ"] == pytest.approx(0.2)


def test_fetch_uses_resumable_cache(monkeypatch, tmp_path):
    calls = []

    class Api:
        @staticmethod
        def get_demo(**kwargs):
            calls.append(kwargs)
            return pd.DataFrame([{"value": 1}])

    monkeypatch.setattr(panda_client, "ensure_authenticated", lambda: None)
    monkeypatch.setattr(panda_client, "sdk_version", lambda: "test")
    monkeypatch.setitem(__import__("sys").modules, "panda_data", Api)
    panda_client.configure_runtime(cache_dir=tmp_path, min_request_interval=0)
    try:
        first = panda_client.fetch("get_demo", key=["A"])
        second = panda_client.fetch("get_demo", key=["A"])
    finally:
        panda_client.configure_runtime()
    assert calls == [{"key": ["A"]}]
    pd.testing.assert_frame_equal(first, second)
    manifests = list(tmp_path.rglob("*.json"))
    assert len(manifests) == 1
    assert "frame_sha256" in manifests[0].read_text(encoding="utf-8")


def test_fetch_cache_handles_mixed_object_columns(monkeypatch, tmp_path):
    class Api:
        @staticmethod
        def get_demo(**kwargs):
            return pd.DataFrame({"mixed": [1.0, "NaN"]})

    monkeypatch.setattr(panda_client, "ensure_authenticated", lambda: None)
    monkeypatch.setitem(__import__("sys").modules, "panda_data", Api)
    panda_client.configure_runtime(cache_dir=tmp_path)
    try:
        panda_client.fetch("get_demo", key="mixed")
        cached = panda_client.fetch("get_demo", key="mixed")
    finally:
        panda_client.configure_runtime()
    assert cached["mixed"].tolist() == ["1.0", "NaN"]


def test_concurrent_authentication_initializes_token_once(monkeypatch):
    calls = []

    class Api:
        @staticmethod
        def init_token(**kwargs):
            time.sleep(0.02)
            calls.append(kwargs)

    monkeypatch.setitem(__import__("sys").modules, "panda_data", Api)
    monkeypatch.setattr(panda_client, "_AUTHENTICATED", False)
    monkeypatch.setattr(panda_client, "_CREDENTIALS", ("user", "password", None))
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda _: panda_client.ensure_authenticated(), range(8)))
    assert len(calls) == 1
