#!/usr/bin/env python3
"""Build one timestamped master CSV from mapping scans and HLK sessions.

The output is a long-format dataset: every row is either a mapping point or an
HLK presence frame, tagged by ``record_type``/``task``. This keeps the final
submission dataset in one CSV while still allowing training code to filter the
task it needs. Per-scan exports remain available under ``research/dataset``.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

MAPPING = Path(__file__).resolve().parent
if str(MAPPING) not in sys.path:
    sys.path.insert(0, str(MAPPING))

from common import RESEARCH, read_json, utc_iso  # noqa: E402
from dataset_export import export_run  # noqa: E402

DEFAULT_SCANS = ["20261110T184241Z"]
MASTER_COLUMNS = [
    "dataset_version", "record_type", "task", "session_id", "scan_id",
    "frame_index", "point_index", "timestamp_utc", "elapsed_ms", "split",
    "label", "label_type", "point_label", "object_id", "object_label",
    "object_source", "prior_region",
    "distance_cm", "energy", "target_state",
    "moving_cm", "moving_energy", "stationary_cm", "stationary_energy",
    "detection_cm", "delta_distance_cm",
    "yaw_half_steps", "yaw_deg", "servo_us", "tilt_deg",
    "hc_raw_mm", "hc_cal_mm", "hc_cm", "hc_valid_rate",
    "tof_raw_mm", "tof_cal_mm", "tof_cm", "tof_valid_rate", "tof_status",
    "hlk_cm", "hlk_energy", "hlk_valid",
    "rule_beep", "rule_zone", "rule_interval_ms", "range_mm", "range_source",
    "x_mm", "y_mm", "z_mm", "x_m", "y_m", "z_m",
    "is_valid", "is_mount", "is_ceiling",
    "sample_count", "sample_uptime_ms_first", "sample_uptime_ms_last",
    "sample_hlk_distance_cm_median", "sample_hlk_energy_max",
    "room_width_m", "room_depth_m", "mirror_y", "yaw_scale",
    "map_rotation_deg", "sensor_height_mm", "hc_offset_mm", "tof_offset_mm",
    "source_file",
]


def _parse_utc(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _elapsed_ms(start, value):
    first = _parse_utc(start)
    current = _parse_utc(value)
    if first is None or current is None:
        return None
    return round((current - first).total_seconds() * 1000.0, 1)


def _sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _latest_clean_points(scan_id):
    root = RESEARCH / "dataset" / "clean" / scan_id
    if not root.is_dir():
        return None
    for run_dir in sorted(root.iterdir(), reverse=True):
        points_path = run_dir / "points.csv"
        if points_path.is_file():
            return points_path
    return None


def _scan_rows(scan_id, output_root, scans_root, label, clean=True,
               refresh=False):
    points_path = None if refresh else _latest_clean_points(scan_id)
    if points_path is not None:
        result = {
            "scan_id": scan_id,
            "folder": points_path.parent.relative_to(RESEARCH).as_posix(),
            "reused": True,
        }
    else:
        result = export_run(
            scan_id,
            clean=clean,
            run_label=label,
            notes="Master dataset mapping export; Rencana boxes are flagged as priors.",
            output_root=output_root,
            scans_root=scans_root,
        )
        points_path = RESEARCH / result["folder"] / "points.csv"
    if not points_path.is_file():
        raise FileNotFoundError(points_path)
    with points_path.open("r", encoding="utf-8", newline="") as handle:
        points = list(csv.DictReader(handle))
    rows = []
    for point in points:
        timestamp = point.get("point_utc_est") or point.get("scan_started_utc")
        label_value = point.get("object_label") or point.get("point_label") or ""
        rows.append({
            "dataset_version": "v1",
            "record_type": "scan_point",
            "task": "mapping",
            "session_id": scan_id,
            "scan_id": scan_id,
            "point_index": point.get("point_index"),
            "timestamp_utc": timestamp,
            "elapsed_ms": _elapsed_ms(point.get("scan_started_utc"), timestamp),
            "split": "train",
            "label": label_value,
            "label_type": "object",
            "point_label": point.get("point_label"),
            "object_id": point.get("object_id"),
            "object_label": point.get("object_label"),
            "object_source": point.get("object_source"),
            "prior_region": point.get("prior_region"),
            "yaw_half_steps": point.get("yaw_half_steps"),
            "yaw_deg": point.get("yaw_deg"),
            "servo_us": point.get("servo_us"),
            "tilt_deg": point.get("tilt_deg"),
            "hc_raw_mm": point.get("hc_raw_mm"),
            "hc_cal_mm": point.get("hc_cal_mm"),
            "hc_valid_rate": point.get("hc_valid_rate"),
            "tof_raw_mm": point.get("tof_raw_mm"),
            "tof_cal_mm": point.get("tof_cal_mm"),
            "tof_valid_rate": point.get("tof_valid_rate"),
            "tof_status": point.get("tof_status"),
            "hlk_cm": point.get("hlk_cm"),
            "hlk_energy": point.get("hlk_energy"),
            "hlk_valid": point.get("hlk_valid"),
            "range_mm": point.get("range_mm"),
            "range_source": point.get("range_source"),
            "x_mm": point.get("x_mm"),
            "y_mm": point.get("y_mm"),
            "z_mm": point.get("z_mm"),
            "x_m": point.get("x_m"),
            "y_m": point.get("y_m"),
            "z_m": point.get("z_m"),
            "is_valid": point.get("is_valid"),
            "is_mount": point.get("is_mount"),
            "is_ceiling": point.get("is_ceiling"),
            "sample_count": point.get("sample_count"),
            "sample_uptime_ms_first": point.get("sample_uptime_ms_first"),
            "sample_uptime_ms_last": point.get("sample_uptime_ms_last"),
            "sample_hlk_distance_cm_median": point.get("sample_hlk_distance_cm_median"),
            "sample_hlk_energy_max": point.get("sample_hlk_energy_max"),
            "source_file": str(points_path),
        })
    return rows, result


def _ml_rows(session_dir, split="train"):
    frames_path = session_dir / "frames.jsonl"
    if not frames_path.is_file():
        return []
    rows = []
    previous_distance = None
    first_utc = None
    with frames_path.open("r", encoding="utf-8") as handle:
        for index, line in enumerate(handle):
            line = line.strip()
            if not line:
                continue
            frame = json.loads(line)
            if first_utc is None:
                first_utc = frame.get("utc")
            last = frame.get("hlk_last_reading") or {}
            distance = frame.get("hlk_distance_cm")
            try:
                distance_value = float(distance)
            except (TypeError, ValueError):
                distance_value = None
            delta = None
            if distance_value is not None and previous_distance is not None:
                delta = round(distance_value - previous_distance, 1)
            if distance_value is not None:
                previous_distance = distance_value
            label = frame.get("label") or session_dir.name.rsplit("-", 1)[-1]
            moving = last.get("moving_distance_cm")
            stationary = last.get("stationary_distance_cm")
            try:
                moving_value = float(moving) if moving is not None else 0.0
                stationary_value = float(stationary) if stationary is not None else 0.0
                rule_distance = (moving_value if (moving_value and
                                 (not stationary_value or moving_value < stationary_value))
                                 else stationary_value)
                rule_energy = max(float(last.get("moving_energy") or 0.0),
                                  float(last.get("stationary_energy") or 0.0))
            except (TypeError, ValueError):
                rule_distance = 0.0
                rule_energy = 0.0
            rule_beep = bool(30.0 <= rule_distance <= 75.0 and rule_energy >= 40.0)
            if rule_beep:
                rule_zone = (1 if rule_distance >= 63 else
                             2 if rule_distance >= 52 else
                             3 if rule_distance >= 41 else 4)
                rule_interval = int(round(150 + (rule_distance - 30.0) / 45.0 * 1850))
            else:
                rule_zone = 0
                rule_interval = 0
            rows.append({
                "dataset_version": "v1",
                "record_type": "hlk_frame",
                "task": "presence",
                "session_id": session_dir.name,
                "frame_index": index,
                "timestamp_utc": frame.get("utc"),
                "elapsed_ms": _elapsed_ms(first_utc, frame.get("utc")),
                "split": split,
                "label": label,
                "label_type": "presence",
                "distance_cm": distance,
                "energy": frame.get("hlk_energy"),
                "target_state": frame.get("hlk_target_state"),
                "moving_cm": last.get("moving_distance_cm"),
                "moving_energy": last.get("moving_energy"),
                "stationary_cm": last.get("stationary_distance_cm"),
                "stationary_energy": last.get("stationary_energy"),
                "detection_cm": last.get("detection_distance_cm"),
                "delta_distance_cm": delta,
                "rule_beep": rule_beep,
                "rule_zone": rule_zone,
                "rule_interval_ms": rule_interval,
                "hc_cm": frame.get("hc_cm"),
                "tof_cm": frame.get("tof_cm"),
                "source_file": str(frames_path),
            })
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scan", action="append", default=None,
                        help="scan id to include; repeatable; default reference scan")
    parser.add_argument("--ml-root", default=str(RESEARCH / "ml"))
    parser.add_argument("--output", default=str(RESEARCH / "dataset" / "aiot_room_dataset_v1.csv"))
    parser.add_argument("--version", default="v1")
    parser.add_argument("--refresh-scan", action="store_true",
                        help="create a new dataset run instead of reusing the latest clean run")
    parser.add_argument("--validation-session", action="append", default=[],
                        help="ML session directory name to mark as validation")
    args = parser.parse_args()
    scans = args.scan or DEFAULT_SCANS
    validation = set(args.validation_session or [])
    rows = []
    scan_results = []
    for scan_id in scans:
        scan_rows, result = _scan_rows(scan_id, None, None,
                                       f"master-{scan_id}",
                                       refresh=args.refresh_scan)
        rows.extend(scan_rows)
        scan_results.append({"scan_id": scan_id, **result})
    ml_root = Path(args.ml_root)
    ml_sessions = []
    for session_dir in sorted(ml_root.iterdir()) if ml_root.is_dir() else []:
        if not session_dir.is_dir() or not (session_dir / "frames.jsonl").is_file():
            continue
        split = "validation" if session_dir.name in validation else "train"
        session_rows = _ml_rows(session_dir, split=split)
        if session_rows:
            rows.extend(session_rows)
            ml_sessions.append({
                "session_id": session_dir.name,
                "frames": len(session_rows),
                "split": split,
                "label": session_rows[0].get("label"),
            })
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MASTER_COLUMNS,
                                extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            row["dataset_version"] = args.version
            writer.writerow({key: row.get(key, "") for key in MASTER_COLUMNS})
    manifest = {
        "dataset_version": args.version,
        "created_utc": utc_iso(),
        "output": str(output),
        "sha256": _sha256(output),
        "rows": len(rows),
        "scan_points": sum(1 for row in rows if row["record_type"] == "scan_point"),
        "hlk_frames": sum(1 for row in rows if row["record_type"] == "hlk_frame"),
        "scans": scan_results,
        "ml_sessions": ml_sessions,
        "labels": {
            "presence": sorted({row["label"] for row in rows
                                if row["record_type"] == "hlk_frame"}),
            "objects": sorted({row["label"] for row in rows
                               if row["record_type"] == "scan_point" and row["label"]}),
        },
        "note": ("Long-format master CSV. Filter record_type=hlk_frame for "
                 "presence training and record_type=scan_point for mapping. "
                 "Rencana boxes are not measured training data."),
    }
    manifest_path = output.with_suffix(".manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n",
                             encoding="utf-8")
    print(json.dumps({
        "ok": True,
        "output": str(output),
        "manifest": str(manifest_path),
        "rows": len(rows),
        "scan_points": manifest["scan_points"],
        "hlk_frames": manifest["hlk_frames"],
        "sha256": manifest["sha256"],
    }, indent=2))


if __name__ == "__main__":
    main()
