#!/usr/bin/env python3
"""Collect labeled HLK frames from the ESP32 for TinyML training.

Run after the scan is finished and the arm is parked. One session = one label.
The PC dashboard also exposes the same recorder under the Dataset tab.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "mapping"))
from common import RESEARCH, utc_iso, utc_stamp  # noqa: E402
from esp_client import EspClient  # noqa: E402


def frame_from_status(state: dict, label: str) -> dict:
    sensors = state.get("sensors", {})
    hlk = sensors.get("hlk", {})
    return {
        "utc": utc_iso(),
        "label": label,
        "mode": state.get("mode"),
        "servo_attached": state.get("actuators", {}).get("servo_attached"),
        "stepper_holding": state.get("actuators", {}).get("stepper_holding"),
        "relative_half_steps": state.get("actuators", {}).get("relative_half_steps"),
        "hc_cm": sensors.get("hc_sr04", {}).get("distance_cal_cm"),
        "tof_cm": sensors.get("vl53l1x", {}).get("distance_cal_cm"),
        "hlk_valid": hlk.get("valid"),
        "hlk_distance_cm": hlk.get("distance_cm"),
        "hlk_energy": hlk.get("energy"),
        "hlk_target_state": hlk.get("target_state"),
        "hlk_frames": hlk.get("frames"),
        "hlk_last_reading": state.get("hlk", {}).get("last_reading"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True, help="empty, human, non-human, walking, sitting, standing, lying")
    parser.add_argument("--duration", type=float, default=60.0, help="Seconds; 0 means until Ctrl+C")
    parser.add_argument("--rate-hz", type=float, default=5.0)
    parser.add_argument("--output", help="Optional output directory")
    args = parser.parse_args()

    label = args.label.strip()[:40] or "unlabeled"
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in label)
    out_dir = Path(args.output) if args.output else RESEARCH / "ml" / f"{utc_stamp()}-{safe}"
    out_dir.mkdir(parents=True, exist_ok=False)
    path = out_dir / "frames.jsonl"
    interval = 1.0 / max(0.5, min(20.0, args.rate_hz))
    client = EspClient()
    frames = 0
    started = utc_iso()
    print(f"recording label={label} rate={1/interval:.1f}Hz to {path}")
    try:
        with path.open("w", encoding="utf-8") as handle:
            deadline = time.monotonic() + args.duration if args.duration > 0 else None
            while deadline is None or time.monotonic() < deadline:
                try:
                    state = client.status()
                except Exception as exc:
                    print(f"status error: {exc}", file=sys.stderr)
                    time.sleep(0.5)
                    continue
                frame = frame_from_status(state, label)
                handle.write(json.dumps(frame, ensure_ascii=False) + "\n")
                handle.flush()
                frames += 1
                if frames % 10 == 0:
                    print(f"frames={frames} hlk={frame.get('hlk_distance_cm')} energy={frame.get('hlk_energy')}")
                time.sleep(interval)
    except KeyboardInterrupt:
        print("stopped by operator")
    metadata = {
        "label": label,
        "started_utc": started,
        "finished_utc": utc_iso(),
        "frames": frames,
        "rate_hz": round(1.0 / interval, 2),
        "path": str(path),
        "note": "HLK time-series for TinyML; record with the arm parked.",
    }
    (out_dir / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(metadata, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, TimeoutError) as exc:
        print(f"collect failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
