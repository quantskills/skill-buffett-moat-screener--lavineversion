from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import pandas as pd

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lavine_buffett.materialize import production_frame, write_production
from lavine_buffett import panda_client
from lavine_buffett.service import screen


def run(input_data: dict, config: dict | None = None) -> dict:
    config = config or {}
    allowed = {"materialize", "output_path", "replace_production"}
    unknown = sorted(set(config) - allowed)
    if unknown:
        raise ValueError(f"unknown config keys: {unknown}")
    result = screen(
        as_of=input_data["as_of"],
        symbols=input_data.get("symbols"),
        all_a=bool(input_data.get("all_a", False)),
    )
    if config.get("materialize"):
        output = config.get("output_path", "production/database.parquet")
        if Path(output).name == "database.parquet" and not input_data.get("all_a"):
            raise ValueError("partial universes cannot write canonical production/database.parquet")
        write_production(
            production_frame(result), output,
            replace=bool(config.get("replace_production", False)),
        )
        result["production_path"] = str(output)
    return result


def validate_input(input_data: dict) -> None:
    if not isinstance(input_data, dict):
        raise TypeError("input_data must be a dict")
    if "as_of" not in input_data:
        raise ValueError("input_data requires as_of")
    if bool(input_data.get("symbols")) == bool(input_data.get("all_a")):
        raise ValueError("provide either symbols or all_a=True")


def load_symbols_file(path: str | Path) -> list[str]:
    source = Path(path)
    if source.suffix.lower() == ".csv":
        frame = pd.read_csv(source, dtype=str)
        if "symbol" not in frame:
            raise ValueError("symbols CSV requires a symbol column")
        values = frame["symbol"].dropna().astype(str).tolist()
    else:
        values = [line.strip() for line in source.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not values:
        raise ValueError("symbols file is empty")
    return values


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Lavine's PandaData-only Q44 screener")
    parser.add_argument("--as-of", required=True, help="decision date YYYYMMDD")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--symbols", nargs="+")
    group.add_argument("--symbols-file")
    group.add_argument("--all-a", "--all-sh-sz", dest="all_a", action="store_true")
    parser.add_argument("--json-output")
    parser.add_argument("--parquet-output")
    parser.add_argument("--replace-production", action="store_true", help="explicitly replace, rather than upsert, a Parquet output")
    parser.add_argument("--cache-dir", help="resumable PandaData response cache")
    parser.add_argument("--request-interval", type=float, default=0.0, help="minimum seconds between API calls")
    parser.add_argument("--workers", type=int, default=1, help="maximum concurrent report requests")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    symbols = load_symbols_file(args.symbols_file) if args.symbols_file else args.symbols
    panda_client.configure_runtime(
        cache_dir=args.cache_dir,
        min_request_interval=args.request_interval,
        max_workers=args.workers,
    )
    input_data = {"as_of": args.as_of, "symbols": symbols, "all_a": args.all_a}
    validate_input(input_data)
    result = run(
        input_data,
        {"materialize": bool(args.parquet_output), "output_path": args.parquet_output,
         "replace_production": args.replace_production}
        if args.parquet_output
        else {},
    )
    text = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)
    if args.json_output:
        output = Path(args.json_output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
