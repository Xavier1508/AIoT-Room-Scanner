#!/usr/bin/env python3
"""Run a bounded yaw/tilt scan and write points.csv + samples.jsonl.

The ESP32 remains the real-time controller. This PC tool only sends explicit
nudges, waits for each move, samples status, and stores the result.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from common import (CALIBRATION, SCANS, as_float, median, polar_to_xyz,
                    read_json, tilt_from_pulse, utc_iso, utc_stamp, write_json)
from esp_client import EspClient

YAW_LIMIT = 513
YAW_STEP = 57
TILT_MIN = 500
TILT_MAX = 950
TILT_STEP = 25
SERVO_PARK_US = 800


@dataclass
class ScanConfig:
    yaw_step_deg: int = 5
    tilt_step_us: int = 25
    dwell_ms: int = 400
    samples: int = 5
    sample_interval_ms: int = 250
    yaw_limit_deg: int = 45
    tilt_min_us: int = 500
    tilt_max_us: int = 950
    stepper_step_deg: int = 5
    servo_step_delay_s: float = 0.1
    column_cooldown_s: float = 0.5
    release_stepper_during_sweep: bool = True
    label: str = ""

    def validate(self):
        _yaw_targets(self.yaw_step_deg, self.yaw_limit_deg)
        _tilt_targets(self.tilt_step_us, self.tilt_min_us, self.tilt_max_us)
        if self.stepper_step_deg not in (5, 10):
            raise ValueError("stepper step must be 5 or 10 degrees")
        if self.yaw_step_deg != self.stepper_step_deg:
            raise ValueError("yaw step and stepper step must match")
        if not 0.05 <= self.servo_step_delay_s <= 0.5:
            raise ValueError("servo step delay must be 0.05..0.5 seconds")
        if not 0 <= self.column_cooldown_s <= 5:
            raise ValueError("column cooldown must be 0..5 seconds")
        if not 50 <= self.sample_interval_ms <= 1000:
            raise ValueError("sample interval must be 50..1000 ms")


def _yaw_targets(step_deg: int, limit_deg: int = 45):
    if step_deg not in (5, 10):
        raise ValueError("yaw step must be 5 or 10 degrees")
    if limit_deg not in (5, 10, 15, 20, 30, 45):
        raise ValueError("yaw limit must be 5, 10, 15, 20, 30 or 45 degrees")
    if limit_deg < step_deg:
        raise ValueError("yaw limit must be at least the yaw step")
    stride = YAW_STEP if step_deg == 5 else YAW_STEP * 2
    if limit_deg >= 45:
        limit_steps = YAW_LIMIT
    else:
        # Quantize to the 57-half-step nudge grid; otherwise the stepper
        # orchestrator cannot reach the requested limit.
        limit_steps = int(round(limit_deg * 4096 / 360 / YAW_STEP)) * YAW_STEP
    limit_steps = max(stride, min(YAW_LIMIT, limit_steps))
    targets = list(range(0, limit_steps + 1, stride))
    if targets[-1] != limit_steps:
        targets.append(limit_steps)
    targets = sorted(set([-value for value in targets] + targets))
    return targets


def _tilt_targets(step_us: int, min_us: int = 500, max_us: int = 950):
    if step_us not in (25, 50):
        raise ValueError("tilt step must be 25 or 50 microseconds")
    if not (500 <= min_us < max_us <= 950):
        raise ValueError("tilt range must satisfy 500 <= min < max <= 950")
    return list(range(min_us, max_us + 1, step_us))


def _median_sample(rows, path, key):
    values = []
    for row in rows:
        node = row
        for part in path:
            node = node.get(part, {}) if isinstance(node, dict) else {}
        value = node.get(key) if isinstance(node, dict) else None
        if value is not None:
            values.append(value)
    return median(values)


def _point_from_samples(rows, yaw_half_steps, servo_us, calibration):
    hc_raw = _median_sample(rows, ("sensors", "hc_sr04"), "distance_mm")
    tof_raw = _median_sample(rows, ("sensors", "vl53l1x"), "distance_mm")
    hc_valid = sum(1 for row in rows if row.get("sensors", {}).get("hc_sr04", {}).get("valid"))
    tof_valid = sum(1 for row in rows if row.get("sensors", {}).get("vl53l1x", {}).get("valid"))
    hc_offset = float(calibration.get("hc_offset_mm", 0) or 0)
    tof_offset = float(calibration.get("tof_offset_mm", 50) or 50)
    hc_cal = hc_raw + hc_offset if hc_raw is not None else None
    tof_cal = tof_raw + tof_offset if tof_raw is not None else None
    hlk_cm = _median_sample(rows, ("sensors", "hlk"), "distance_cm")
    hlk_energy = _median_sample(rows, ("sensors", "hlk"), "energy")
    hlk_valid = any(row.get("sensors", {}).get("hlk", {}).get("valid") for row in rows)
    tof_status = rows[-1].get("sensors", {}).get("vl53l1x", {}).get("status") if rows else None
    if tof_cal is not None and tof_valid and 30 <= tof_cal <= 4000:
        range_mm, source = tof_cal, "tof"
    elif hc_cal is not None and hc_valid and 20 <= hc_cal <= 4000:
        range_mm, source = hc_cal, "hc"
    else:
        range_mm, source = None, ""
    yaw_deg = yaw_half_steps * 360.0 / 4096.0
    tilt_deg = tilt_from_pulse(servo_us, calibration)
    height_mm = float(calibration.get("sensor_height_mm", 0) or 0)
    x = y = z = None
    if range_mm is not None:
        x, y, z = polar_to_xyz(range_mm, yaw_deg, tilt_deg, height_mm)
    return {
        "yaw_half_steps": yaw_half_steps,
        "yaw_deg": round(yaw_deg, 2),
        "servo_us": servo_us,
        "tilt_deg": round(tilt_deg, 2),
        "hc_raw_mm": round(hc_raw, 1) if hc_raw is not None else None,
        "hc_cal_mm": round(hc_cal, 1) if hc_cal is not None else None,
        "hc_valid_rate": round(hc_valid / max(1, len(rows)), 3),
        "tof_raw_mm": round(tof_raw, 1) if tof_raw is not None else None,
        "tof_cal_mm": round(tof_cal, 1) if tof_cal is not None else None,
        "tof_valid_rate": round(tof_valid / max(1, len(rows)), 3),
        "tof_status": tof_status,
        "hlk_cm": round(hlk_cm, 1) if hlk_cm is not None else None,
        "hlk_energy": round(hlk_energy, 1) if hlk_energy is not None else None,
        "hlk_valid": hlk_valid,
        "range_mm": round(range_mm, 1) if range_mm is not None else None,
        "range_source": source,
        "x_mm": round(x, 1) if x is not None else None,
        "y_mm": round(y, 1) if y is not None else None,
        "z_mm": round(z, 1) if z is not None else None,
    }


def run_scan(client: EspClient, config: ScanConfig, progress=None, stop_event=None):
    config.validate()
    calibration = read_json(CALIBRATION, {}) or {}
    scan_id = utc_stamp()
    out_dir = SCANS / scan_id
    out_dir.mkdir(parents=True, exist_ok=False)
    yaws = _yaw_targets(config.yaw_step_deg, config.yaw_limit_deg)
    tilts = _tilt_targets(config.tilt_step_us, config.tilt_min_us, config.tilt_max_us)
    total = len(yaws) * len(tilts)
    points = []
    samples_path = out_dir / "samples.jsonl"
    started = utc_iso()
    error = None
    motion_started = False
    try:
        client.ensure_sensors()
        current = client.status()
        current_steps = int(current["actuators"]["relative_half_steps"])
        if current_steps % YAW_STEP != 0:
            raise RuntimeError("Stepper reference is not aligned to 5-degree units; zero it before scanning.")
        if current.get("actuators", {}).get("servo_attached"):
            client.servo_to(SERVO_PARK_US, step_delay_s=config.servo_step_delay_s)
            time.sleep(0.2)
            result = client.command("release_servo")
            if not result.get("ok"):
                raise RuntimeError("Cannot detach servo before scan: " + str(result.get("message")))
            time.sleep(0.25)
        client.command("scan_mode_start")
        client.command("park_stepper")
        with samples_path.open("w", encoding="utf-8") as sample_file:
            for yaw_index, yaw in enumerate(yaws):
                if stop_event is not None and stop_event.is_set():
                    raise InterruptedError("scan stopped by operator")
                state = client.status()
                if state.get("actuators", {}).get("servo_attached"):
                    client.servo_to(SERVO_PARK_US, step_delay_s=config.servo_step_delay_s)
                    time.sleep(0.2)
                    result = client.command("release_servo")
                    if not result.get("ok"):
                        raise RuntimeError("Cannot detach servo between columns: " + str(result.get("message")))
                    time.sleep(0.25)
                if progress:
                    progress({"phase": "moving_stepper", "scan_id": scan_id,
                              "yaw_index": yaw_index, "yaw_count": len(yaws),
                              "points": len(points), "total": total})
                client.move_stepper_to(yaw, settle_s=0.35, step_deg=config.stepper_step_deg)
                if config.release_stepper_during_sweep:
                    result = client.command("release_stepper")
                    if not result.get("ok"):
                        raise RuntimeError("Stepper release rejected: " + str(result.get("message")))
                    time.sleep(0.2)
                if progress:
                    progress({"phase": "servo_attach", "scan_id": scan_id,
                              "yaw_index": yaw_index, "yaw_count": len(yaws),
                              "points": len(points), "total": total})
                result = client.command("park_servo")
                if not result.get("ok"):
                    raise RuntimeError("Servo attach rejected: " + str(result.get("message")))
                motion_started = True
                time.sleep(0.5)
                client.servo_to(tilts[0], step_delay_s=config.servo_step_delay_s)
                time.sleep(0.2)
                for tilt_index, tilt in enumerate(tilts):
                    if stop_event is not None and stop_event.is_set():
                        raise InterruptedError("scan stopped by operator")
                    if tilt_index:
                        client.servo_to(tilt, step_delay_s=config.servo_step_delay_s)
                    time.sleep(max(0, config.dwell_ms) / 1000.0)
                    rows = []
                    for sample_index in range(max(1, config.samples)):
                        rows.append(client.status())
                        sample_file.write(json.dumps({
                            "scan_id": scan_id,
                            "yaw_index": yaw_index,
                            "tilt_index": tilt_index,
                            "sample_index": sample_index,
                            "status": rows[-1],
                        }, ensure_ascii=False) + "\n")
                        if sample_index + 1 < max(1, config.samples):
                            time.sleep(max(1, config.sample_interval_ms) / 1000.0)
                    point = _point_from_samples(rows, yaw, tilt, calibration)
                    point["point_index"] = len(points)
                    points.append(point)
                    if progress:
                        progress({
                            "phase": "scanning",
                            "scan_id": scan_id,
                            "yaw_index": yaw_index,
                            "yaw_count": len(yaws),
                            "tilt_index": tilt_index,
                            "tilt_count": len(tilts),
                            "points": len(points),
                            "total": total,
                            "last_point": point,
                        })
                # Return to the base pulse before detaching. Re-attaching at
                # 800 us after a column ended at 950 us caused a large jump and
                # a measured brownout on the second column.
                client.servo_to(SERVO_PARK_US, step_delay_s=config.servo_step_delay_s)
                time.sleep(0.2)
                result = client.command("release_servo")
                if not result.get("ok"):
                    raise RuntimeError("Servo detach rejected: " + str(result.get("message")))
                time.sleep(0.35)
                if config.release_stepper_during_sweep:
                    result = client.command("park_stepper")
                    if not result.get("ok"):
                        raise RuntimeError("Stepper re-hold rejected: " + str(result.get("message")))
                    time.sleep(0.2)
                if config.column_cooldown_s:
                    time.sleep(config.column_cooldown_s)
        client.move_stepper_to(0, settle_s=0.35, step_deg=config.stepper_step_deg)
        client.command("park_stepper")
        client.command("scan_mode_stop")
        if config.release_stepper_during_sweep:
            try:
                client.command("release_stepper")
            except Exception:
                pass
        fields = list(points[0].keys()) if points else []
        with (out_dir / "points.csv").open("w", encoding="utf-8", newline="") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=fields)
            writer.writeheader()
            writer.writerows(points)
        valid = [p for p in points if p.get("range_mm") is not None]
        metadata = {
            "scan_id": scan_id,
            "started_utc": started,
            "finished_utc": utc_iso(),
            "config": asdict(config),
            "sequential": True,
            "servo_detach_between_columns": True,
            "stepper_released_during_sweep": config.release_stepper_during_sweep,
            "stepper_released_after_scan": config.release_stepper_during_sweep,
            "calibration": calibration,
            "yaw_targets": yaws,
            "tilt_targets": tilts,
            "points": len(points),
            "valid_points": len(valid),
            "tof_points": sum(1 for p in points if p.get("range_source") == "tof"),
            "hc_points": sum(1 for p in points if p.get("range_source") == "hc"),
            "error": None,
        }
        write_json(out_dir / "metadata.json", metadata)
        if progress:
            progress({"phase": "done", "scan_id": scan_id, "points": len(points), "total": total})
        return {"scan_id": scan_id, "directory": str(out_dir), "points": len(points), "valid_points": len(valid)}
    except Exception as exc:
        error = str(exc)
        metadata = {
            "scan_id": scan_id,
            "started_utc": started,
            "finished_utc": utc_iso(),
            "config": asdict(config),
            "calibration": calibration,
            "points": len(points),
            "error": error,
        }
        write_json(out_dir / "metadata.json", metadata)
        if progress:
            progress({"phase": "error", "scan_id": scan_id, "error": error, "points": len(points), "total": total})
        raise
    finally:
        # Sequential power profile: leave the stepper held, but never re-attach
        # the servo in cleanup. A servo attach brownout was observed.
        try:
            client.command("scan_mode_stop")
            if motion_started:
                state = client.status()
                if state.get("actuators", {}).get("servo_attached"):
                    client.command("release_servo")
                client.command("park_stepper")
                if config.release_stepper_during_sweep:
                    try:
                        client.command("release_stepper")
                    except Exception:
                        pass
        except Exception:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--yaw-step-deg", type=int, default=5, choices=(5, 10))
    parser.add_argument("--yaw-limit-deg", type=int, default=45, choices=(5, 10, 15, 20, 30, 45))
    parser.add_argument("--tilt-step-us", type=int, default=25, choices=(25, 50))
    parser.add_argument("--tilt-min-us", type=int, default=500)
    parser.add_argument("--tilt-max-us", type=int, default=950)
    parser.add_argument("--stepper-step-deg", type=int, default=5, choices=(5, 10))
    parser.add_argument("--servo-step-delay-s", type=float, default=0.1)
    parser.add_argument("--column-cooldown-s", type=float, default=0.5)
    parser.add_argument("--hold-stepper-during-sweep", action="store_true",
                        help="Keep stepper energized during the servo sweep (higher current).")
    parser.add_argument("--sample-interval-ms", type=int, default=250)
    parser.add_argument("--dwell-ms", type=int, default=400)
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--label", default="")
    args = parser.parse_args()
    config = ScanConfig(
        yaw_step_deg=args.yaw_step_deg,
        tilt_step_us=args.tilt_step_us,
        dwell_ms=args.dwell_ms,
        samples=args.samples,
        sample_interval_ms=args.sample_interval_ms,
        yaw_limit_deg=args.yaw_limit_deg,
        tilt_min_us=args.tilt_min_us,
        tilt_max_us=args.tilt_max_us,
        stepper_step_deg=args.stepper_step_deg,
        servo_step_delay_s=args.servo_step_delay_s,
        column_cooldown_s=args.column_cooldown_s,
        release_stepper_during_sweep=not args.hold_stepper_during_sweep,
        label=args.label,
    )
    stop_event = threading.Event()
    result = run_scan(EspClient(), config, progress=lambda p: print(json.dumps(p)), stop_event=stop_event)
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, TimeoutError, InterruptedError) as exc:
        print("scan failed: " + str(exc), file=sys.stderr)
        raise SystemExit(1)
