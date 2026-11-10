"""Export one scan as a labeled, timestamped CSV dataset run.

The exporter is dependency-free (standard library only) so the mapping server
can call it with the same Python that serves the dashboard. It writes:

  points.csv    one row per scan point, with labels and derived flags
  objects.csv   one row per measured/prior box
  manifest.json run metadata, counts and file hashes
  manifest.csv  one-row summary (also appended to dataset/index.csv)
  annotations.json snapshot used for the run
  README.txt    column notes and clean/dirty explanation

Runs are separated by clean/dirty so a training set can be collected without
mixing experimental scans.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

MAPPING = Path(__file__).resolve().parent
if str(MAPPING) not in sys.path:
    sys.path.insert(0, str(MAPPING))

from common import CALIBRATION, RESEARCH, SCANS, read_json, utc_iso, utc_stamp  # noqa: E402
from reconstruct import reconstruct_points  # noqa: E402

DATASET_ROOT = RESEARCH / "dataset"

POINT_COLUMNS = [
    "scan_id", "run_utc", "run_label", "clean",
    "scan_started_utc", "scan_finished_utc", "point_utc_est",
    "point_index", "yaw_half_steps", "yaw_deg", "servo_us", "tilt_deg",
    "hc_raw_mm", "hc_cal_mm", "hc_valid_rate",
    "tof_raw_mm", "tof_cal_mm", "tof_valid_rate", "tof_status",
    "hlk_cm", "hlk_energy", "hlk_valid",
    "range_mm", "range_source",
    "x_mm", "y_mm", "z_mm", "x_m", "y_m", "z_m",
    "is_valid", "is_mount", "is_ceiling",
    "sample_count", "sample_uptime_ms_first", "sample_uptime_ms_last",
    "sample_hlk_distance_cm_median", "sample_hlk_energy_max",
    "point_label", "object_id", "object_label", "object_source",
    "object_label_source", "prior_region", "prior_label",
]

OBJECT_COLUMNS = [
    "scan_id", "run_utc", "run_label", "clean",
    "scan_started_utc", "scan_finished_utc",
    "object_id", "label", "label_source", "source",
    "is_measured", "is_prior",
    "cx_m", "cy_m", "angle_deg", "length_m", "width_m",
    "z_bottom_m", "z_top_m", "distance_m", "nearest_m", "points",
    "footprint_m2", "volume_m3",
    "room_width_m", "room_depth_m", "yaw_scale", "map_rotation_deg",
    "sensor_height_mm", "hc_offset_mm", "tof_offset_mm",
    "notes",
]

INDEX_COLUMNS = [
    "run_utc", "scan_id", "run_label", "clean", "notes",
    "points_total", "points_valid", "tof_points", "hc_points",
    "boxes_total", "measured_boxes", "prior_boxes",
    "folder", "points_csv", "objects_csv", "manifest_json",
]


def _as_float(value, default=None):
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value, default=None):
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative(path: Path) -> str:
    try:
        return path.relative_to(RESEARCH).as_posix()
    except ValueError:
        return path.as_posix()


def _read_points(scan_dir: Path):
    path = scan_dir / "points.csv"
    if not path.is_file():
        raise ValueError("points.csv not found")
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _read_samples(scan_dir: Path):
    """Aggregate samples.jsonl per (yaw_index, tilt_index)."""
    path = scan_dir / "samples.jsonl"
    groups = {}
    if not path.is_file():
        return groups
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            key = (_as_int(record.get("yaw_index"), -1),
                   _as_int(record.get("tilt_index"), -1))
            status = record.get("status") or {}
            sensors = status.get("sensors") or {}
            hlk = sensors.get("hlk") or {}
            uptime = _as_int(status.get("uptime_ms"))
            groups.setdefault(key, []).append({
                "uptime_ms": uptime,
                "hlk_distance_cm": _as_float(hlk.get("distance_cm")),
                "hlk_energy": _as_float(hlk.get("energy")),
            })
    aggregated = {}
    for key, items in groups.items():
        uptimes = [item["uptime_ms"] for item in items if item["uptime_ms"] is not None]
        distances = sorted(item["hlk_distance_cm"] for item in items
                           if item["hlk_distance_cm"] is not None)
        energies = [item["hlk_energy"] for item in items if item["hlk_energy"] is not None]
        aggregated[key] = {
            "sample_count": len(items),
            "uptime_first": min(uptimes) if uptimes else None,
            "uptime_last": max(uptimes) if uptimes else None,
            "hlk_distance_median": (distances[len(distances) // 2]
                                    if distances else None),
            "hlk_energy_max": max(energies) if energies else None,
        }
    return aggregated


def _point_utc(scan_started: str | None, scan_finished: str | None,
               index: int, total: int) -> str | None:
    if not scan_started or not scan_finished or total <= 1:
        return scan_started
    try:
        start = datetime.fromisoformat(scan_started.replace("Z", "+00:00"))
        end = datetime.fromisoformat(scan_finished.replace("Z", "+00:00"))
    except ValueError:
        return scan_started
    ratio = max(0.0, min(1.0, index / (total - 1)))
    moment = start + (end - start) * ratio
    return moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _box_contains(box, x, y, z):
    angle = math.radians(float(box.get("angle_deg", 0.0) or 0.0))
    ca, sa = math.cos(angle), math.sin(angle)
    dx, dy = x - float(box.get("cx_m", 0.0) or 0.0), y - float(box.get("cy_m", 0.0) or 0.0)
    u = dx * ca + dy * sa
    v = -dx * sa + dy * ca
    half_length = float(box.get("length_m", 0.0) or 0.0) / 2.0
    half_width = float(box.get("width_m", 0.0) or 0.0) / 2.0
    z0 = float(box.get("z_bottom_m", 0.0) or 0.0)
    z1 = float(box.get("z_top_m", 0.0) or 0.0)
    return (abs(u) <= half_length and abs(v) <= half_width
            and z0 - 1e-6 <= z <= z1 + 1e-6)


def _point_label_map(annotations):
    mapping = {}
    for label, indices in (annotations.get("point_labels") or {}).items():
        for index in indices or []:
            mapping[_as_int(index)] = str(label)
    return mapping


def _is_mount(row, near_field_m=0.40, mount_guard_m=0.75, mount_guard_z_m=0.72):
    x = _as_float(row.get("x_mm"), 0.0) / 1000.0
    y = _as_float(row.get("y_mm"), 0.0) / 1000.0
    z = _as_float(row.get("z_mm"), 0.0) / 1000.0
    distance = math.hypot(x, y)
    if z < -0.05:
        return True
    if distance < near_field_m:
        return True
    if distance < mount_guard_m and z < mount_guard_z_m:
        return True
    range_mm = _as_float(row.get("range_mm"))
    return range_mm is not None and range_mm < near_field_m * 1000.0


def _write_csv(path: Path, columns, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in columns})


def _append_index(path: Path, row):
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.is_file()
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=INDEX_COLUMNS, extrasaction="ignore")
        if not exists:
            writer.writeheader()
        writer.writerow({key: row.get(key, "") for key in INDEX_COLUMNS})


def _readme(scan_id, run_utc, clean, run_label, notes):
    return f"""AIoT room-scan dataset run
==========================
scan_id: {scan_id}
run_utc: {run_utc}
run_label: {run_label or '-'}
clean: {str(bool(clean)).lower()}
notes: {notes or '-'}

Files
-----
points.csv       one row per scan point (raw sensors + calibrated x/y/z + labels)
objects.csv      one row per box (measured auto/manual boxes and prior boxes)
manifest.json    counts, settings, file hashes and column list
manifest.csv     one-row summary (also appended to ../index.csv)
annotations.json snapshot of labels/priors used for this run

Columns that matter for training
--------------------------------
points.csv:
  x_m, y_m, z_m          calibrated room coordinates (metres)
  range_source           tof or hc
  point_label            manual point label, if any
  object_label           measured box label containing the point, if any
  object_source          auto or manual
  prior_region           true when the point falls inside a prior box
  prior_label            prior box label (not measured ground truth)
  is_mount, is_ceiling   derived flags; mount/ceiling points should be excluded
  point_utc_est          estimated UTC timestamp from scan start/finish

objects.csv:
  is_measured            true for boxes built from scan points
  is_prior               true for prior-only boxes (points=0, not training data)
  label                  desk/bed/fan/wall/... after manual labels
  points                 number of scan points in the box

Clean vs dirty
--------------
clean=true runs are stored under dataset/clean/<scan_id>/<run_utc>/ and are
intended for the training set. clean=false runs are stored under
dataset/dirty/<scan_id>/<run_utc>/ and are kept for comparison/debugging.
Prior boxes are never training ground truth.
"""


def export_run(scan_id: str, clean: bool = False, run_label: str = "",
               notes: str = "", output_root: Path | None = None,
               scans_root: Path | None = None):
    scans_root = Path(scans_root) if scans_root else SCANS
    scan_dir = scans_root / scan_id
    if not scan_dir.is_dir():
        raise ValueError("scan not found")
    metadata = read_json(scan_dir / "metadata.json", {}) or {}
    annotations = read_json(scan_dir / "annotations.json", {}) or {}
    calibration = read_json(CALIBRATION, {}) or {}
    rows = _read_points(scan_dir)
    samples = _read_samples(scan_dir)
    room = annotations.get("room") or {}
    yaw_scale = _as_float(room.get("yaw_scale"), 1.0)
    map_rotation = _as_float(room.get("map_rotation_deg"), 0.0)
    reconstruction = reconstruct_points(
        rows, yaw_scale=yaw_scale, map_rotation_deg=map_rotation,
        annotations=annotations)
    boxes = reconstruction.get("boxes") or []
    mount_row_set = set(reconstruction.get("mount_rows") or [])
    ceiling_row_set = set(reconstruction.get("ceiling_rows") or [])
    measured_boxes = [box for box in boxes
                      if str(box.get("source")) != "prior"
                      and int(box.get("points", 0) or 0) > 0]
    prior_boxes = [box for box in boxes
                   if str(box.get("source")) == "prior"
                   or int(box.get("points", 0) or 0) == 0]
    point_labels = _point_label_map(annotations)
    scan_started = metadata.get("started_utc")
    scan_finished = metadata.get("finished_utc")
    run_utc = utc_stamp()
    quality = "clean" if clean else "dirty"
    root = Path(output_root) if output_root else DATASET_ROOT
    folder = root / quality / scan_id / run_utc
    folder.mkdir(parents=True, exist_ok=True)

    total = len(rows)
    tilt_count = len(metadata.get("tilt_targets") or []) or 19
    point_rows = []
    valid_count = tof_count = hc_count = 0
    mount_count = ceiling_count = prior_region_count = 0
    for row in rows:
        index = _as_int(row.get("point_index"), 0)
        x_mm = _as_float(row.get("x_mm"))
        y_mm = _as_float(row.get("y_mm"))
        z_mm = _as_float(row.get("z_mm"))
        range_mm = _as_float(row.get("range_mm"))
        x_m = x_mm / 1000.0 if x_mm is not None else None
        y_m = y_mm / 1000.0 if y_mm is not None else None
        z_m = z_mm / 1000.0 if z_mm is not None else None
        source = str(row.get("range_source") or "")
        valid = range_mm is not None and range_mm > 0
        if valid:
            valid_count += 1
            if source == "tof":
                tof_count += 1
            elif source == "hc":
                hc_count += 1
        mount = index in mount_row_set or _is_mount(row)
        ceiling = index in ceiling_row_set
        object_box = None
        prior_box = None
        if x_m is not None and y_m is not None and z_m is not None:
            for box in measured_boxes:
                if _box_contains(box, x_m, y_m, z_m):
                    if object_box is None or int(box.get("points", 0)) > int(object_box.get("points", 0)):
                        object_box = box
            for box in prior_boxes:
                if _box_contains(box, x_m, y_m, z_m):
                    prior_box = box
                    break
        if mount:
            mount_count += 1
        if ceiling:
            ceiling_count += 1
        if prior_box:
            prior_region_count += 1
        yaw_index = index // tilt_count
        tilt_index = index % tilt_count
        sample = samples.get((yaw_index, tilt_index), {})
        point_rows.append({
            "scan_id": scan_id,
            "run_utc": run_utc,
            "run_label": run_label,
            "clean": str(bool(clean)).lower(),
            "scan_started_utc": scan_started,
            "scan_finished_utc": scan_finished,
            "point_utc_est": _point_utc(scan_started, scan_finished, index, total),
            "point_index": index,
            "yaw_half_steps": row.get("yaw_half_steps"),
            "yaw_deg": row.get("yaw_deg"),
            "servo_us": row.get("servo_us"),
            "tilt_deg": row.get("tilt_deg"),
            "hc_raw_mm": row.get("hc_raw_mm"),
            "hc_cal_mm": row.get("hc_cal_mm"),
            "hc_valid_rate": row.get("hc_valid_rate"),
            "tof_raw_mm": row.get("tof_raw_mm"),
            "tof_cal_mm": row.get("tof_cal_mm"),
            "tof_valid_rate": row.get("tof_valid_rate"),
            "tof_status": row.get("tof_status"),
            "hlk_cm": row.get("hlk_cm"),
            "hlk_energy": row.get("hlk_energy"),
            "hlk_valid": row.get("hlk_valid"),
            "range_mm": row.get("range_mm"),
            "range_source": source,
            "x_mm": row.get("x_mm"),
            "y_mm": row.get("y_mm"),
            "z_mm": row.get("z_mm"),
            "x_m": round(x_m, 4) if x_m is not None else None,
            "y_m": round(y_m, 4) if y_m is not None else None,
            "z_m": round(z_m, 4) if z_m is not None else None,
            "is_valid": str(bool(valid)).lower(),
            "is_mount": str(bool(mount)).lower(),
            "is_ceiling": str(bool(ceiling)).lower(),
            "sample_count": sample.get("sample_count", 0),
            "sample_uptime_ms_first": sample.get("uptime_first"),
            "sample_uptime_ms_last": sample.get("uptime_last"),
            "sample_hlk_distance_cm_median": sample.get("hlk_distance_median"),
            "sample_hlk_energy_max": sample.get("hlk_energy_max"),
            "point_label": point_labels.get(index, ""),
            "object_id": object_box.get("id") if object_box else "",
            "object_label": object_box.get("label") if object_box else "",
            "object_source": object_box.get("source") if object_box else "",
            "object_label_source": object_box.get("label_source") if object_box else "",
            "prior_region": str(bool(prior_box)).lower(),
            "prior_label": prior_box.get("label") if prior_box else "",
        })

    object_rows = []
    for box in boxes:
        length = _as_float(box.get("length_m"), 0.0) or 0.0
        width = _as_float(box.get("width_m"), 0.0) or 0.0
        z0 = _as_float(box.get("z_bottom_m"), 0.0) or 0.0
        z1 = _as_float(box.get("z_top_m"), 0.0) or 0.0
        points = int(box.get("points", 0) or 0)
        is_prior = str(box.get("source")) == "prior" or points == 0
        object_rows.append({
            "scan_id": scan_id,
            "run_utc": run_utc,
            "run_label": run_label,
            "clean": str(bool(clean)).lower(),
            "scan_started_utc": scan_started,
            "scan_finished_utc": scan_finished,
            "object_id": box.get("id"),
            "label": box.get("label"),
            "label_source": box.get("label_source"),
            "source": box.get("source") or ("prior" if is_prior else "auto"),
            "is_measured": str(not is_prior).lower(),
            "is_prior": str(is_prior).lower(),
            "cx_m": box.get("cx_m"),
            "cy_m": box.get("cy_m"),
            "angle_deg": box.get("angle_deg"),
            "length_m": box.get("length_m"),
            "width_m": box.get("width_m"),
            "z_bottom_m": box.get("z_bottom_m"),
            "z_top_m": box.get("z_top_m"),
            "distance_m": box.get("distance_m"),
            "nearest_m": box.get("nearest_m"),
            "points": points,
            "footprint_m2": round(length * width, 4),
            "volume_m3": round(length * width * max(0.0, z1 - z0), 4),
            "room_width_m": room.get("width_m"),
            "room_depth_m": room.get("depth_m"),
            "yaw_scale": yaw_scale,
            "map_rotation_deg": map_rotation,
            "sensor_height_mm": (metadata.get("calibration") or {}).get("sensor_height_mm"),
            "hc_offset_mm": calibration.get("hc_offset_mm"),
            "tof_offset_mm": calibration.get("tof_offset_mm"),
            "notes": notes,
        })

    points_path = folder / "points.csv"
    objects_path = folder / "objects.csv"
    manifest_path = folder / "manifest.json"
    manifest_csv_path = folder / "manifest.csv"
    annotations_path = folder / "annotations.json"
    readme_path = folder / "README.txt"

    _write_csv(points_path, POINT_COLUMNS, point_rows)
    _write_csv(objects_path, OBJECT_COLUMNS, object_rows)
    annotations_path.write_text(
        json.dumps(annotations, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    readme_path.write_text(
        _readme(scan_id, run_utc, clean, run_label, notes), encoding="utf-8")

    files = {
        "points_csv": _relative(points_path),
        "objects_csv": _relative(objects_path),
        "manifest_json": _relative(manifest_path),
        "manifest_csv": _relative(manifest_csv_path),
        "annotations_json": _relative(annotations_path),
        "readme": _relative(readme_path),
    }
    manifest = {
        "scan_id": scan_id,
        "run_utc": run_utc,
        "run_label": run_label,
        "clean": bool(clean),
        "notes": notes,
        "scan_started_utc": scan_started,
        "scan_finished_utc": scan_finished,
        "scan_config": metadata.get("config") or {},
        "sensor_height_mm": (metadata.get("calibration") or {}).get("sensor_height_mm"),
        "hc_offset_mm": calibration.get("hc_offset_mm"),
        "tof_offset_mm": calibration.get("tof_offset_mm"),
        "points_total": total,
        "points_valid": valid_count,
        "tof_points": tof_count,
        "hc_points": hc_count,
        "mount_points": mount_count,
        "ceiling_points": ceiling_count,
        "prior_region_points": prior_region_count,
        "boxes_total": len(boxes),
        "measured_boxes": len(measured_boxes),
        "prior_boxes": len(prior_boxes),
        "yaw_scale": yaw_scale,
        "map_rotation_deg": map_rotation,
        "room": room,
        "labels": annotations.get("labels") or {},
        "files": files,
        "sha256": {
            "points_csv": _sha256(points_path),
            "objects_csv": _sha256(objects_path),
            "annotations_json": _sha256(annotations_path),
        },
        "columns": {
            "points": POINT_COLUMNS,
            "objects": OBJECT_COLUMNS,
        },
        "note": ("Measured boxes have points>0; prior boxes have points=0 and "
                 "are not training ground truth. is_ceiling/is_mount are derived "
                 "flags and should be excluded from object training."),
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    manifest_csv = dict(manifest)
    manifest_csv["clean"] = str(bool(clean)).lower()
    manifest_csv["folder"] = _relative(folder)
    manifest_csv["points_csv"] = files["points_csv"]
    manifest_csv["objects_csv"] = files["objects_csv"]
    manifest_csv["manifest_json"] = files["manifest_json"]
    _write_csv(manifest_csv_path, INDEX_COLUMNS, [manifest_csv])
    index_row = dict(manifest_csv)
    index_row["folder"] = _relative(folder)
    _append_index(root / "index.csv", index_row)
    return {
        "ok": True,
        "scan_id": scan_id,
        "run_utc": run_utc,
        "clean": bool(clean),
        "run_label": run_label,
        "notes": notes,
        "folder": _relative(folder),
        "files": files,
        "counts": {
            "points_total": total,
            "points_valid": valid_count,
            "tof_points": tof_count,
            "hc_points": hc_count,
            "mount_points": mount_count,
            "ceiling_points": ceiling_count,
            "prior_region_points": prior_region_count,
            "boxes_total": len(boxes),
            "measured_boxes": len(measured_boxes),
            "prior_boxes": len(prior_boxes),
        },
    }


