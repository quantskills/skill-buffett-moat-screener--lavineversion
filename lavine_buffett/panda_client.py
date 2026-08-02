from __future__ import annotations

import importlib.metadata
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Any, Iterable

import pandas as pd

from .config import REPORT_FIELDS
from .rules import clean_date, clean_symbol


class PandaDataError(RuntimeError):
    pass


class PandaAuthenticationError(PandaDataError):
    pass


_CREDENTIALS: tuple[str, str, str | None] | None = None
_CACHE_DIR: Path | None = None
_MIN_REQUEST_INTERVAL = 0.0
_MAX_WORKERS = 1
_LAST_REQUEST_AT = 0.0
_REQUEST_LOCK = threading.Lock()
_AUTH_LOCK = threading.Lock()
_AUTHENTICATED = False
_SOURCE_LOCK = threading.Lock()
_USED_SOURCE_ENTRIES: set[str] = set()


def configure_credentials(username: str, password: str, base_url: str | None = None) -> None:
    if not username or not password:
        raise PandaAuthenticationError("PandaData username and password are required")
    global _CREDENTIALS, _AUTHENTICATED
    _CREDENTIALS = (str(username), str(password), base_url)
    _AUTHENTICATED = False


def configure_runtime(
    *, cache_dir: str | Path | None = None, min_request_interval: float = 0.0,
    max_workers: int = 1,
) -> None:
    global _CACHE_DIR, _MIN_REQUEST_INTERVAL, _MAX_WORKERS, _USED_SOURCE_ENTRIES
    _CACHE_DIR = Path(cache_dir) if cache_dir else None
    _MIN_REQUEST_INTERVAL = max(0.0, float(min_request_interval))
    _MAX_WORKERS = max(1, int(max_workers))
    _USED_SOURCE_ENTRIES = set()


def runtime_versions() -> dict[str, str]:
    import numpy as np
    import pyarrow

    return {
        "panda_data": sdk_version(),
        "pandas": pd.__version__,
        "numpy": np.__version__,
        "pyarrow": pyarrow.__version__,
    }


def _cache_context() -> dict[str, str]:
    username = _CREDENTIALS[0] if _CREDENTIALS else os.getenv("PANDA_DATA_USERNAME", "")
    base_url = (_CREDENTIALS[2] if _CREDENTIALS else os.getenv("PANDA_DATA_BASE_URL")) or "default"
    contract = json.dumps(REPORT_FIELDS, ensure_ascii=False, separators=(",", ":"))
    return {
        "sdk_version": sdk_version(),
        "base_url_hash": hashlib.sha256(base_url.encode("utf-8")).hexdigest()[:16],
        "account_hash": hashlib.sha256(username.encode("utf-8")).hexdigest()[:16],
        "contract_hash": hashlib.sha256(contract.encode("utf-8")).hexdigest()[:16],
    }


def _cache_path(name: str, kwargs: dict[str, Any]) -> Path | None:
    if _CACHE_DIR is None:
        return None
    context = _cache_context()
    payload = json.dumps(
        {"name": name, "kwargs": kwargs, "context": context},
        ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"),
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    namespace = hashlib.sha256(
        json.dumps(context, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return _CACHE_DIR / namespace / name / f"{digest}.parquet"


def _normalized_cache_frame(frame: pd.DataFrame) -> pd.DataFrame:
    cache_frame = frame.copy()
    for column in cache_frame.select_dtypes(include="object").columns:
        cache_frame[column] = cache_frame[column].astype("string")
    return cache_frame


def _frame_digest(frame: pd.DataFrame) -> str:
    normalized = _normalized_cache_frame(frame)
    metadata = json.dumps(
        {"columns": list(normalized.columns), "dtypes": [str(dtype) for dtype in normalized.dtypes]},
        ensure_ascii=False, sort_keys=True,
    ).encode("utf-8")
    values = pd.util.hash_pandas_object(normalized, index=True).values.tobytes()
    return hashlib.sha256(metadata + values).hexdigest()


def _record_source(cache_path: Path | None, frame_digest: str) -> None:
    request_id = cache_path.stem if cache_path is not None else "uncached"
    with _SOURCE_LOCK:
        _USED_SOURCE_ENTRIES.add(f"{request_id}:{frame_digest}")


def source_provenance() -> dict[str, Any]:
    with _SOURCE_LOCK:
        entries = sorted(_USED_SOURCE_ENTRIES)
    digest = hashlib.sha256("\n".join(entries).encode("utf-8")).hexdigest()
    return {"response_count": len(entries), "response_manifest_hash": digest}


def _throttled_call(api: Any, kwargs: dict[str, Any], timeout: float) -> Any:
    global _LAST_REQUEST_AT
    with _REQUEST_LOCK:
        delay = _MIN_REQUEST_INTERVAL - (time.monotonic() - _LAST_REQUEST_AT)
        if delay > 0:
            time.sleep(delay)
        _LAST_REQUEST_AT = time.monotonic()
    return _call_with_timeout(api, kwargs, timeout)


def consume_environment_credentials() -> None:
    username = os.environ.pop("PANDA_DATA_USERNAME", None)
    password = os.environ.pop("PANDA_DATA_PASSWORD", None)
    base_url = os.environ.pop("PANDA_DATA_BASE_URL", None)
    configure_credentials(username or "", password or "", base_url)


def sdk_version() -> str:
    try:
        return importlib.metadata.version("panda-data")
    except importlib.metadata.PackageNotFoundError as exc:
        raise PandaDataError("panda_data is not installed") from exc


def ensure_authenticated() -> None:
    global _AUTHENTICATED
    if _AUTHENTICATED:
        return
    import panda_data

    with _AUTH_LOCK:
        if _AUTHENTICATED:
            return
        if _CREDENTIALS is None:
            consume_environment_credentials()
        assert _CREDENTIALS is not None
        username, password, base_url = _CREDENTIALS
        kwargs: dict[str, Any] = {"username": username, "password": password}
        if base_url:
            kwargs["base_url"] = base_url
        try:
            panda_data.init_token(**kwargs)
            _AUTHENTICATED = True
        except Exception as exc:
            raise PandaAuthenticationError(f"PandaData authentication failed: {type(exc).__name__}") from exc


def _call_with_timeout(api: Any, kwargs: dict[str, Any], timeout: float) -> Any:
    result: queue.Queue[tuple[bool, Any]] = queue.Queue(maxsize=1)

    def worker() -> None:
        try:
            result.put((True, api(**kwargs)))
        except BaseException as exc:
            result.put((False, exc))

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    thread.join(timeout)
    if thread.is_alive():
        raise PandaDataError("PandaData request timed out")
    ok, value = result.get_nowait()
    if not ok:
        raise value
    return value


def fetch(name: str, *, timeout: float = 60, retries: int = 8, **kwargs: Any) -> pd.DataFrame:
    cache_path = _cache_path(name, kwargs)
    if cache_path is not None and cache_path.exists():
        manifest_path = cache_path.with_suffix(".json")
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            frame = pd.read_parquet(cache_path)
            digest = _frame_digest(frame)
            if manifest.get("frame_sha256") == digest:
                _record_source(cache_path, digest)
                return frame
        except Exception:
            pass
    ensure_authenticated()
    import panda_data

    api = getattr(panda_data, name, None)
    if not callable(api):
        raise PandaDataError(f"panda_data {sdk_version()} has no {name}")
    for attempt in range(retries):
        try:
            result = _throttled_call(api, kwargs, timeout)
            if result is None:
                frame = pd.DataFrame()
            else:
                frame = result.copy() if isinstance(result, pd.DataFrame) else pd.DataFrame(result)
            if cache_path is not None:
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                temporary = cache_path.with_suffix(f".{os.getpid()}.tmp.parquet")
                try:
                    cache_frame = _normalized_cache_frame(frame)
                    frame_sha256 = _frame_digest(cache_frame)
                    cache_frame.to_parquet(temporary, index=False)
                    temporary.replace(cache_path)
                    manifest = {
                        "fetched_at": datetime.now().astimezone().isoformat(),
                        "api": name,
                        "row_count": len(cache_frame),
                        "columns": list(cache_frame.columns),
                        "dtypes": [str(dtype) for dtype in cache_frame.dtypes],
                        "frame_sha256": frame_sha256,
                        "context": _cache_context(),
                    }
                    manifest_path = cache_path.with_suffix(".json")
                    manifest_tmp = manifest_path.with_suffix(f".{os.getpid()}.tmp.json")
                    manifest_tmp.write_text(
                        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2),
                        encoding="utf-8",
                    )
                    manifest_tmp.replace(manifest_path)
                except Exception:
                    # Cache availability must not turn a successful provider call into a failed screen.
                    pass
                finally:
                    temporary.unlink(missing_ok=True)
            digest = _frame_digest(frame)
            _record_source(cache_path, digest)
            return frame
        except Exception as exc:
            message = str(exc)
            rate_limited = "500010" in message or "请求次数超限" in message
            if rate_limited and attempt + 1 < retries:
                time.sleep(min(60, 15 * (attempt + 1)))
                continue
            raise PandaDataError(f"{name} failed: {type(exc).__name__}: {exc}") from exc
    return pd.DataFrame()


def _batches(values: list[str], size: int) -> Iterable[list[str]]:
    for offset in range(0, len(values), size):
        yield values[offset : offset + size]


def fetch_reports(symbols: list[str], as_of: str, years: int = 13) -> pd.DataFrame:
    latest_year = int(clean_date(as_of)[:4])
    first_year = latest_year - years
    jobs = []
    for batch in _batches(symbols, 20):
        chunk_start = first_year
        while chunk_start <= latest_year:
            chunk_end = min(chunk_start + 4, latest_year)
            jobs.append((batch, chunk_start, chunk_end))
            chunk_start = chunk_end + 1

    def load(job) -> pd.DataFrame:
        batch, chunk_start, chunk_end = job
        return fetch(
                "get_fina_reports",
                symbol=batch,
                start_quarter=f"{chunk_start}q1",
                end_quarter=f"{chunk_end}q4",
                date=clean_date(as_of),
                is_latest=False,
                fields=REPORT_FIELDS,
            )

    if _MAX_WORKERS == 1:
        loaded = map(load, jobs)
    else:
        with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
            loaded = list(pool.map(load, jobs))
    frames = [frame for frame in loaded if not frame.empty]
    return pd.concat(frames, ignore_index=True, sort=False) if frames else pd.DataFrame(columns=REPORT_FIELDS)


def fetch_latest_prices(symbols: list[str], as_of: str) -> dict[str, dict[str, Any]]:
    end = datetime.strptime(clean_date(as_of), "%Y%m%d")
    start = (end - timedelta(days=30)).strftime("%Y%m%d")
    frames: list[pd.DataFrame] = []
    for batch in _batches(symbols, 50):
        frame = fetch(
            "get_stock_daily",
            symbol=batch,
            start_date=start,
            end_date=clean_date(as_of),
            fields=["symbol", "date", "close"],
        )
        if not frame.empty:
            frames.append(frame)
    if not frames:
        return {}
    work = pd.concat(frames, ignore_index=True, sort=False)
    work["symbol"] = work["symbol"].map(clean_symbol)
    work["date"] = work["date"].map(clean_date)
    work["close"] = pd.to_numeric(work["close"], errors="coerce")
    work = work[work["date"].ne("") & (work["date"] <= clean_date(as_of)) & work["close"].gt(0)]
    work = work.sort_values(["symbol", "date"]).drop_duplicates("symbol", keep="last")
    return {
        str(row["symbol"]): {"date": str(row["date"]), "close": float(row["close"])}
        for _, row in work.iterrows()
    }


def fetch_forward_returns(symbols: list[str], start_date: str, end_date: str) -> dict[str, float]:
    """Return post-adjusted close returns after a signal date.

    The first available close strictly after ``start_date`` is the entry and
    the last close on or before ``end_date`` is the exit.
    """
    start = (datetime.strptime(clean_date(start_date), "%Y%m%d") + timedelta(days=1)).strftime("%Y%m%d")
    frames: list[pd.DataFrame] = []
    for batch in _batches(symbols, 50):
        frame = fetch(
            "get_stock_daily_post",
            symbol=batch,
            start_date=start,
            end_date=clean_date(end_date),
            fields=["symbol", "date", "close"],
        )
        if not frame.empty:
            frames.append(frame)
    if not frames:
        return {}
    work = pd.concat(frames, ignore_index=True, sort=False)
    work["symbol"] = work["symbol"].map(clean_symbol)
    work["date"] = work["date"].map(clean_date)
    work["close"] = pd.to_numeric(work["close"], errors="coerce")
    work = work[
        work["symbol"].notna() & work["date"].ne("") & work["close"].notna()
        & work["date"].between(start, clean_date(end_date))
    ].sort_values(["symbol", "date"])
    returns: dict[str, float] = {}
    for symbol, group in work.groupby("symbol"):
        if len(group) < 2 or float(group.iloc[0]["close"]) <= 0:
            continue
        returns[str(symbol)] = float(group.iloc[-1]["close"] / group.iloc[0]["close"] - 1)
    return returns


def fetch_industries(symbols: list[str], as_of: str) -> dict[str, dict[str, str]]:
    frames: list[pd.DataFrame] = []
    for batch in _batches(symbols, 100):
        frame = fetch(
            "get_industry_constituents",
            stock_symbol=batch,
            level="L1",
            fields=["stock_symbol", "l1_code", "in_date", "out_date"],
        )
        if not frame.empty:
            frames.append(frame)
    if not frames:
        return {}
    work = pd.concat(frames, ignore_index=True, sort=False)
    work["symbol"] = work["stock_symbol"].map(clean_symbol)
    work["in_date"] = work["in_date"].map(clean_date)
    work["out_date"] = work["out_date"].fillna("").map(clean_date)
    cutoff = clean_date(as_of)
    work = work[
        work["in_date"].ne("") & (work["in_date"] <= cutoff)
        & ((work["out_date"] == "") | (work["out_date"] > cutoff))
    ]
    conflicting_symbols = set(
        work.groupby("symbol")["l1_code"].nunique().loc[lambda values: values > 1].index
    )
    work = work[~work["symbol"].isin(conflicting_symbols)]
    work = work.sort_values(["symbol", "in_date"]).drop_duplicates("symbol", keep="last")
    details = fetch("get_industry_detail", level="L1", fields=["industry_code", "industry_name"])
    names = (
        details.set_index("industry_code")["industry_name"].astype(str).to_dict()
        if {"industry_code", "industry_name"}.issubset(details.columns)
        else {}
    )
    return {
        str(row["symbol"]): {
            "industry_code": str(row["l1_code"]),
            "industry_name": str(names.get(row["l1_code"], "")),
        }
        for _, row in work.iterrows()
    }


def discover_all_a(as_of: str) -> list[str]:
    frame = fetch("get_stock_detail", status=None)
    if frame.empty or "symbol" not in frame:
        raise PandaDataError("get_stock_detail returned no A-share universe")
    cutoff = clean_date(as_of)
    work = frame.copy()
    work["symbol"] = work["symbol"].map(clean_symbol)
    listed = work.get("listed_date", pd.Series("", index=work.index)).map(clean_date)
    delisted = work.get("de_listed_date", pd.Series("", index=work.index)).fillna("").map(clean_date)
    mask = (
        work["symbol"].astype(str).str.match(r"^\d{6}\.(SH|SZ)$")
        & listed.ne("")
        & (listed <= cutoff)
        & ((delisted == "") | (delisted > cutoff))
    )
    return sorted(set(work.loc[mask, "symbol"].dropna().astype(str)))
