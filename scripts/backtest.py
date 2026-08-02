from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lavine_buffett.backtest import analyze_snapshots
from lavine_buffett.panda_client import fetch_forward_returns
from lavine_buffett.service import screen


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Annual point-in-time Q44 diagnostic")
    parser.add_argument("--signal-dates", nargs="+", required=True)
    parser.add_argument("--symbols", nargs="+")
    parser.add_argument("--all-a", action="store_true")
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if bool(args.symbols) == bool(args.all_a):
        raise SystemExit("provide either --symbols or --all-a")
    snapshots = [
        screen(as_of=day, symbols=args.symbols, all_a=args.all_a)
        for day in sorted(set(args.signal_dates))
    ]
    result = analyze_snapshots(snapshots, fetch_forward_returns)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
