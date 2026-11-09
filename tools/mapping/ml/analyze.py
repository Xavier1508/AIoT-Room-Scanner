#!/usr/bin/env python3
"""Summarize HLK dataset sessions before training.

Prints per-session label, frame count, moving-energy coverage, distance range
and target-state counts. A human session with very few moving frames is a
warning that the recording may contain long still/empty periods.
"""
from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", default="research/mapping/ml")
    args = parser.parse_args()
    root = Path(args.data)
    total = 0
    for path in sorted(root.rglob("frames.jsonl")):
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if not rows:
            continue
        total += len(rows)
        moving = [float((row.get("hlk_last_reading") or {}).get("moving_energy") or 0) for row in rows]
        stationary = [float((row.get("hlk_last_reading") or {}).get("stationary_energy") or 0) for row in rows]
        distances = [float(row["hlk_distance_cm"]) for row in rows if row.get("hlk_distance_cm") is not None]
        states = Counter(row.get("hlk_target_state") for row in rows)
        moving_count = sum(1 for value in moving if value > 0)
        label = rows[0].get("label")
        print(f"{path.parent.name}: label={label} frames={len(rows)} "
              f"moving>0={moving_count} ({100.0 * moving_count / len(rows):.1f}%) "
              f"moving_max={max(moving):.0f} stationary_median={statistics.median(stationary):.0f}")
        if distances:
            print(f"  distance min/median/max={min(distances):.0f}/{statistics.median(distances):.0f}/{max(distances):.0f} cm")
        print(f"  target_state={dict(states)}")
    print(f"total frames={total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
