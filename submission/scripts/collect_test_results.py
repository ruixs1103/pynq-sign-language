#!/usr/bin/env python3
"""Aggregate completed benchmark CSV rows into a compact JSON summary."""
import argparse
import csv
import json
from pathlib import Path


def number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("csv")
    parser.add_argument("--out", default="submission/data/test_summary.json")
    args = parser.parse_args()
    rows = list(csv.DictReader(Path(args.csv).open(encoding="utf-8-sig", newline="")))
    valid = [r for r in rows if "TBD-TEST" not in "".join(r.values())]
    summary = {"completed_runs": len(valid), "runs": valid}
    for mode in ("cpu", "pl"):
        selected = [r for r in valid if r.get("mode") == mode]
        latencies = [number(r.get("mean_latency_ms")) for r in selected]
        latencies = [x for x in latencies if x is not None]
        summary[mode] = {
            "runs": len(selected),
            "mean_of_mean_latency_ms": (sum(latencies) / len(latencies)
                                         if latencies else None),
        }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
