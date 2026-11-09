#!/usr/bin/env python3
"""Capture HC-SR04 / VL53L1X / HLK readings against a measured target distance."""
from __future__ import annotations

import argparse
import sys

from common import (CALIBRATION, median, read_json, sample_status, utc_iso,
                    write_json)
from esp_client import EspClient


def capture(client: EspClient, actual_cm: float, samples: int, label: str = "") -> dict:
    state = client.ensure_sensors()
    if not state.get("sensors", {}).get("enabled"):
        raise RuntimeError("Sensors are not running.")
    rows = sample_status(client, samples, 0.25)
    hc_raw = median([r.get("sensors", {}).get("hc_sr04", {}).get("distance_mm") for r in rows])
    tof_raw = median([r.get("sensors", {}).get("vl53l1x", {}).get("distance_mm") for r in rows])
    hlk_cm = median([r.get("sensors", {}).get("hlk", {}).get("distance_cm") for r in rows])
    hc_valid = sum(1 for r in rows if r.get("sensors", {}).get("hc_sr04", {}).get("valid"))
    tof_valid = sum(1 for r in rows if r.get("sensors", {}).get("vl53l1x", {}).get("valid"))
    actual_mm = float(actual_cm) * 10.0
    record = {
        "utc": utc_iso(),
        "label": label,
        "actual_cm": round(float(actual_cm), 2),
        "samples": len(rows),
        "hc_raw_mm": round(hc_raw, 1) if hc_raw is not None else None,
        "tof_raw_mm": round(tof_raw, 1) if tof_raw is not None else None,
        "hlk_cm": round(hlk_cm, 1) if hlk_cm is not None else None,
        "hc_valid_rate": round(hc_valid / max(1, len(rows)), 3),
        "tof_valid_rate": round(tof_valid / max(1, len(rows)), 3),
        "hc_offset_mm": round(actual_mm - hc_raw, 1) if hc_raw is not None else None,
        "tof_offset_mm": round(actual_mm - tof_raw, 1) if tof_raw is not None else None,
        "hc_status": "valid" if rows[-1].get("sensors", {}).get("hc_sr04", {}).get("valid")
        else ("stale" if rows[-1].get("sensors", {}).get("hc_sr04", {}).get("stale") else "no_data"),
        "tof_status": rows[-1].get("sensors", {}).get("vl53l1x", {}).get("status"),
        "sensor_health": rows[-1].get("sensors", {}).get("health"),
    }
    calibration = read_json(CALIBRATION, {}) or {}
    calibration.setdefault("records", []).append(record)
    calibration["updated_utc"] = record["utc"]
    calibration["hc_offset_mm"] = record["hc_offset_mm"] if record["hc_offset_mm"] is not None else calibration.get("hc_offset_mm", 0)
    calibration["tof_offset_mm"] = record["tof_offset_mm"] if record["tof_offset_mm"] is not None else calibration.get("tof_offset_mm", 50)
    calibration["hlk_min_range_cm"] = 30
    calibration["latest"] = record
    write_json(CALIBRATION, calibration)
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--distance-cm", type=float, required=True,
                        help="Measured distance from the HC-SR04 reference face to the target.")
    parser.add_argument("--samples", type=int, default=10)
    parser.add_argument("--label", default="")
    args = parser.parse_args()
    record = capture(EspClient(), args.distance_cm, max(1, args.samples), args.label)
    print(record)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, TimeoutError) as exc:
        print("calibration failed: " + str(exc), file=sys.stderr)
        raise SystemExit(1)
