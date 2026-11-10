#!/usr/bin/env python3
"""Export manually labelled point patches and object boxes for 3D DL.

Point labels are stored by stable ``point_index`` in the scan's
``annotations.json``. This exporter writes one CSV/NPZ per label plus an object
table and a manifest. It does not train a model.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np

MAPPING = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MAPPING))

from common import RESEARCH, SCANS, read_json, write_json  # noqa: E402
from reconstruct import reconstruct_points  # noqa: E402


def _safe_name(label: str) -> str:
    text = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in str(label))
    return text.strip("-")[:60] or "label"


def _relative(path: Path) -> str:
    try:
        return str(path.relative_to(RESEARCH))
    except ValueError:
        return str(path)


def _read_points(scan_id: str):
    path = SCANS / scan_id / "points.csv"
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def export_scan(scan_id: str, output_root: Path, yaw_scale: float = 0.76) -> dict:
    scan_dir = SCANS / scan_id
    annotations = read_json(scan_dir / "annotations.json", {}) or {}
    saved_yaw = (annotations.get("room") or {}).get("yaw_scale")
    if saved_yaw:
        try:
            yaw_scale = max(0.50, min(1.00, float(saved_yaw)))
        except (TypeError, ValueError):
            pass
    rows = _read_points(scan_id)
    by_index = {}
    for row in rows:
        try:
            by_index[int(row.get("point_index", -1))] = row
        except (TypeError, ValueError):
            continue

    target = output_root / scan_id
    target.mkdir(parents=True, exist_ok=True)
    labels = annotations.get("point_labels") or {}
    manifest = {
        "scan_id": scan_id,
        "yaw_scale": yaw_scale,
        "point_labels": {},
        "objects": [],
    }

    for label, indices in labels.items():
        selected = [by_index[int(index)] for index in indices if int(index) in by_index]
        if not selected:
            continue
        name = _safe_name(label)
        csv_path = target / f"{name}.csv"
        npz_path = target / f"{name}.npz"
        fields = ["point_index", "x_mm", "y_mm", "z_mm", "range_mm",
                  "yaw_deg", "tilt_deg", "range_source"]
        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for row in selected:
                writer.writerow({field: row.get(field, "") for field in fields})
        values = {
            "x_m": np.array([float(row.get("x_mm") or 0.0) / 1000.0 for row in selected], dtype=np.float32),
            "y_m": np.array([float(row.get("y_mm") or 0.0) / 1000.0 for row in selected], dtype=np.float32),
            "z_m": np.array([float(row.get("z_mm") or 0.0) / 1000.0 for row in selected], dtype=np.float32),
            "range_m": np.array([float(row.get("range_mm") or 0.0) / 1000.0 for row in selected], dtype=np.float32),
            "yaw_deg": np.array([float(row.get("yaw_deg") or 0.0) for row in selected], dtype=np.float32),
            "tilt_deg": np.array([float(row.get("tilt_deg") or 0.0) for row in selected], dtype=np.float32),
            "label": np.array([label] * len(selected)),
        }
        np.savez_compressed(npz_path, **values)
        manifest["point_labels"][label] = {
            "points": len(selected),
            "csv": _relative(csv_path),
            "npz": _relative(npz_path),
        }

    reconstruction = reconstruct_points(rows, yaw_scale=yaw_scale, annotations=annotations)
    objects_path = target / "objects.csv"
    object_fields = ["label", "source", "label_source", "distance_m", "nearest_m",
                     "length_m", "width_m", "z_top_m", "points", "cx_m", "cy_m", "angle_deg"]
    with objects_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=object_fields)
        writer.writeheader()
        for box in reconstruction.get("boxes") or []:
            row = {field: box.get(field, "") for field in object_fields}
            writer.writerow(row)
            manifest["objects"].append({
                "label": box.get("label"),
                "source": box.get("source", "auto"),
                "distance_m": box.get("distance_m"),
                "length_m": box.get("length_m"),
                "width_m": box.get("width_m"),
                "z_top_m": box.get("z_top_m"),
                "points": box.get("points", 0),
            })

    write_json(target / "manifest.json", manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scan", default="", help="scan id; omit to export all scans")
    parser.add_argument("--output", default=str(RESEARCH / "ml" / "pointcloud"))
    parser.add_argument("--yaw-scale", type=float, default=0.76)
    args = parser.parse_args()
    output = Path(args.output)
    scan_ids = [args.scan] if args.scan else sorted(
        directory.name for directory in SCANS.iterdir()
        if (directory / "points.csv").is_file()
    )
    results = []
    for scan_id in scan_ids:
        try:
            results.append(export_scan(scan_id, output, args.yaw_scale))
        except Exception as exc:  # keep exporting the remaining scans
            print(f"{scan_id}: failed: {exc}")
    print(json.dumps({"exported": [item["scan_id"] for item in results]}, indent=2))
    return 0 if results else 1


if __name__ == "__main__":
    raise SystemExit(main())
