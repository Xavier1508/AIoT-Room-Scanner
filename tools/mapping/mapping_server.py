#!/usr/bin/env python3
"""Local PC dashboard for calibration, scan orchestration and 3D point clouds.

Dependency-free: standard-library HTTP server plus a vanilla canvas viewer.
Run from this directory:

    python mapping_server.py --host 127.0.0.1 --port 8000

The ESP32 diagnostic page remains a separate application. This server proxies
the ESP32 API so browser code never receives the ESP32 Basic-auth credentials.
"""
from __future__ import annotations

import argparse
import csv
import json
import mimetypes
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from calibrate import capture
from common import CALIBRATION, RESEARCH, ROOT, SCANS, read_json, utc_iso, utc_stamp, write_json
from dataset_export import export_run
from esp_client import EspClient
from presence import PresenceTracker
from reconstruct import auto_align_rotation, reconstruct_points
from scan import ScanConfig, run_scan
from scene_export import export_scene
from tracking import TrackingConfig, run_tracking_loop

STATIC = Path(__file__).with_name("static")
JOB_LOCK = threading.Lock()
JOB = {
    "state": "idle",
    "scan_id": None,
    "points": 0,
    "total": 0,
    "error": None,
    "progress": {},
    "thread": None,
    "stop_event": None,
}
ML_LOCK = threading.Lock()
ML_JOB = {
    "state": "idle",
    "label": "",
    "frames": 0,
    "path": None,
    "error": None,
    "started_utc": None,
    "thread": None,
    "stop_event": None,
}
TRACK_LOCK = threading.Lock()
TRACK_JOB = {
    "state": "idle",
    "scan_id": None,
    "estimate": None,
    "progress": {},
    "error": None,
    "started_utc": None,
    "thread": None,
    "stop_event": None,
}
PRESENCE_LOCK = threading.Lock()
PRESENCE = PresenceTracker()


def _public_job():
    with JOB_LOCK:
        return {key: JOB[key] for key in
                ("state", "scan_id", "points", "total", "error", "progress")}


def _public_ml():
    with ML_LOCK:
        return {key: ML_JOB[key] for key in
                ("state", "label", "frames", "path", "error", "started_utc")}


def _start_ml(label: str):
    label = str(label or "unlabeled").strip()[:40] or "unlabeled"
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in label)
    with JOB_LOCK:
        if JOB["state"] == "running":
            raise RuntimeError("scan running; stop the scan before recording a dataset")
    with ML_LOCK:
        if ML_JOB["state"] == "running":
            raise RuntimeError("dataset recording already running")
        directory = RESEARCH / "ml" / f"{utc_stamp()}-{safe}"
        directory.mkdir(parents=True, exist_ok=False)
        path = directory / "frames.jsonl"
        stop_event = threading.Event()
        ML_JOB.update({"state": "running", "label": label, "frames": 0,
                       "path": str(path), "error": None,
                       "started_utc": utc_iso(), "stop_event": stop_event})

    def worker():
        client = EspClient()
        try:
            with path.open("w", encoding="utf-8") as handle:
                while not stop_event.is_set():
                    try:
                        state = client.status()
                    except Exception as exc:
                        with ML_LOCK:
                            ML_JOB["error"] = str(exc)
                        time.sleep(0.5)
                        continue
                    sensors = state.get("sensors", {})
                    hlk = sensors.get("hlk", {})
                    frame = {
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
                    handle.write(json.dumps(frame, ensure_ascii=False) + "\n")
                    handle.flush()
                    with ML_LOCK:
                        ML_JOB["frames"] += 1
                        ML_JOB["error"] = None
                    time.sleep(0.2)
            with ML_LOCK:
                ML_JOB["state"] = "done"
        except Exception as exc:
            with ML_LOCK:
                ML_JOB["state"] = "error"
                ML_JOB["error"] = str(exc)

    thread = threading.Thread(target=worker, daemon=True)
    with ML_LOCK:
        ML_JOB["thread"] = thread
    thread.start()


def _stop_ml():
    with ML_LOCK:
        event = ML_JOB.get("stop_event")
    if event:
        event.set()
    return {"ok": True, "message": "stop_requested"}


def _public_track():
    with TRACK_LOCK:
        return {key: TRACK_JOB[key] for key in
                ("state", "scan_id", "estimate", "progress", "error", "started_utc")}


def _start_track(config):
    if config.get("confirm_power") is not True:
        raise ValueError("power confirmation required: 9V and arm clearance must be confirmed")
    with JOB_LOCK:
        if JOB["state"] == "running":
            raise RuntimeError("scan running; stop it before tracking")
    with ML_LOCK:
        if ML_JOB["state"] == "running":
            raise RuntimeError("dataset recording running; stop it before tracking")
    with TRACK_LOCK:
        if TRACK_JOB["state"] == "running":
            raise RuntimeError("tracking already running")
        stop_event = threading.Event()
        TRACK_JOB.update({"state": "running", "scan_id": str(config.get("scan_id", ""))[:40],
                          "estimate": None, "progress": {}, "error": None,
                          "started_utc": utc_iso(), "stop_event": stop_event})
    tracking_config = TrackingConfig(
        scan_id=str(config.get("scan_id", ""))[:40],
        yaw_limit_deg=max(10, min(60, int(config.get("yaw_limit_deg", 60)))),
        coarse_step_deg=10,
        fine_step_deg=5,
        tilt_us=max(500, min(950, int(config.get("tilt_us", 800)))),
        samples=max(1, min(3, int(config.get("samples", 2)))),
        dwell_ms=max(50, min(500, int(config.get("dwell_ms", 150)))),
        sample_interval_ms=max(50, min(300, int(config.get("sample_interval_ms", 100)))),
        interval_s=max(0.5, min(5.0, float(config.get("interval_s", 1.0)))),
        threshold_cm=max(5.0, min(50.0, float(config.get("threshold_cm", 15.0)))),
    )

    def progress(value):
        with TRACK_LOCK:
            TRACK_JOB["progress"] = value
            estimate = value.get("estimate") or {}
            if estimate.get("state") in ("confirmed", "predicted", "stale"):
                TRACK_JOB["estimate"] = estimate
            background = value.get("background") or {}
            if background.get("scan_id"):
                TRACK_JOB["scan_id"] = background["scan_id"]

    def worker():
        client = EspClient()
        try:
            result = run_tracking_loop(client, tracking_config, progress, stop_event)
            with TRACK_LOCK:
                TRACK_JOB.update({"state": "stopped" if stop_event.is_set() else "done",
                                  "estimate": result, "error": None})
        except Exception as exc:
            with TRACK_LOCK:
                TRACK_JOB.update({"state": "error", "error": str(exc)})

    thread = threading.Thread(target=worker, daemon=True)
    with TRACK_LOCK:
        TRACK_JOB["thread"] = thread
    thread.start()


def _stop_track():
    with TRACK_LOCK:
        event = TRACK_JOB.get("stop_event")
    if event:
        event.set()
    return {"ok": True, "message": "stop_requested"}


def _ml_metrics():
    path = RESEARCH / "ml" / "model-empty-human-v3" / "metrics.json"
    if not path.is_file():
        path = RESEARCH / "ml" / "model-empty-human-v2" / "metrics.json"
    if not path.is_file():
        path = RESEARCH / "ml" / "model-empty-human" / "metrics.json"
    metrics = read_json(path, {}) or {}
    metrics["model_dir"] = str(path.parent.relative_to(RESEARCH)).replace("\\", "/")
    metrics["deployed"] = True
    folds = metrics.get("cv_folds") or []
    if folds:
        hard = min(folds, key=lambda fold: float(fold.get("accuracy", 0) or 0))
        metrics["hard_fold_accuracy"] = hard.get("accuracy")
        confusion = hard.get("confusion") or []
        if len(confusion) >= 2 and len(confusion[1]) >= 2:
            human_total = sum(int(value or 0) for value in confusion[1])
            if human_total:
                metrics["hard_fold_human_recall"] = confusion[1][1] / human_total
    summaries = sorted((ROOT / "analysis" / "mapping").glob("ml-training-*/summary.json"),
                       reverse=True)
    summary = read_json(summaries[0], {}) if summaries else {}
    if summary:
        metrics["rule_baseline"] = summary.get("rule_baseline", {})
        metrics["dataset"] = summary.get("dataset", {})
    if metrics.get("model_version"):
        metrics["conclusion"] = (
            "Model presence v3 (32 frame, 4 sesi, 7.784 frame) berjalan di "
            "firmware 0.9.3 sebagai AI gate aktuator. Validasi blok waktu "
            f"{metrics.get('cv_accuracy_mean', 0) * 100:.2f}% +/- "
            f"{metrics.get('cv_accuracy_std', 0) * 100:.2f}%; fold terberat "
            f"{metrics.get('hard_fold_accuracy', 0) * 100:.2f}% dengan human "
            f"recall {metrics.get('hard_fold_human_recall', 0) * 100:.1f}%. "
            "HLK hanya memberi timing jarak 30-75 cm; rule-only adalah mode "
            "pembanding, bukan jalur utama.")
    elif summary:
        metrics["conclusion"] = summary.get("conclusion")
    return metrics


def _scan_directory(scan_id):
    if not scan_id or Path(scan_id).name != scan_id or "/" in scan_id or "\\" in scan_id:
        raise ValueError("invalid scan id")
    directory = SCANS / scan_id
    if not directory.is_dir():
        raise ValueError("scan not found")
    return directory


def _clean_annotations(payload):
    payload = payload or {}
    labels = payload.get("labels") or {}
    if not isinstance(labels, dict):
        raise ValueError("labels must be an object")
    clean_labels = {str(key)[:200]: str(value)[:24]
                    for key, value in labels.items() if value}
    size_overrides = payload.get("size_overrides") or {}
    if not isinstance(size_overrides, dict):
        raise ValueError("size_overrides must be an object")
    clean_sizes = {}
    for key, entry in list(size_overrides.items())[:100]:
        if not isinstance(entry, dict):
            continue
        clean_entry = {}
        for field, lower, upper in (("length_m", 0.05, 10.0),
                                    ("width_m", 0.05, 10.0),
                                    ("z_bottom_m", 0.0, 4.0),
                                    ("z_top_m", 0.05, 4.0)):
            if field not in entry:
                continue
            try:
                clean_entry[field] = round(
                    max(lower, min(upper, float(entry[field]))), 3)
            except (TypeError, ValueError):
                continue
        if clean_entry:
            clean_sizes[str(key)[:200]] = clean_entry
    hidden = payload.get("hidden") or []
    if not isinstance(hidden, list):
        raise ValueError("hidden must be a list")
    clean_hidden = [str(item)[:200] for item in hidden][:500]
    removed = payload.get("removed") or []
    if not isinstance(removed, list):
        raise ValueError("removed must be a list")
    clean_removed = [str(item)[:200] for item in removed][:500]
    merges = payload.get("merges") or []
    if not isinstance(merges, list):
        raise ValueError("merges must be a list")
    clean_merges = []
    for pair in merges[:200]:
        if isinstance(pair, (list, tuple)) and len(pair) == 2:
            clean_merges.append([str(pair[0])[:200], str(pair[1])[:200]])
    point_labels = payload.get("point_labels") or {}
    clean_point_labels = {}
    if isinstance(point_labels, dict):
        for label, indices in list(point_labels.items())[:100]:
            if not isinstance(indices, list):
                continue
            clean_indices = []
            for index in indices[:5000]:
                try:
                    clean_indices.append(int(index))
                except (TypeError, ValueError):
                    continue
            clean_point_labels[str(label)[:24]] = clean_indices
    catalog = payload.get("label_catalog") or {}
    clean_catalog = {}
    if isinstance(catalog, dict):
        for label, entry in list(catalog.items())[:100]:
            if isinstance(entry, dict):
                clean_catalog[str(label)[:24]] = {
                    "color": str(entry.get("color", ""))[:24]
                }
            else:
                clean_catalog[str(label)[:24]] = {"color": ""}
    manual_boxes = []
    for item in (payload.get("manual_boxes") or [])[:100]:
        if not isinstance(item, dict):
            continue
        try:
            length = max(0.05, min(10.0, float(item.get("length_m", 0.1))))
            width = max(0.05, min(10.0, float(item.get("width_m", 0.1))))
            cx = max(-20.0, min(20.0, float(item.get("cx_m", 0.0))))
            cy = max(-20.0, min(20.0, float(item.get("cy_m", 0.0))))
            angle = float(item.get("angle_deg", 0.0))
            z_bottom = max(0.0, min(4.0, float(item.get("z_bottom_m", 0.0))))
            z_top = max(z_bottom + 0.01, min(4.0, float(item.get("z_top_m", 0.5))))
        except (TypeError, ValueError):
            continue
        manual_boxes.append({
            "id": str(item.get("id") or f"manual:{len(manual_boxes)}")[:200],
            "label": str(item.get("label", "object"))[:24],
            "cx_m": round(cx, 3),
            "cy_m": round(cy, 3),
            "angle_deg": round(angle, 1),
            "length_m": round(length, 3),
            "width_m": round(width, 3),
            "z_bottom_m": round(z_bottom, 3),
            "z_top_m": round(z_top, 3),
            "source": "prior" if item.get("source") == "prior" else "manual",
        })
    room_outline = []
    for point in (payload.get("room_outline") or [])[:64]:
        if isinstance(point, (list, tuple)) and len(point) == 2:
            try:
                room_outline.append([max(-20.0, min(20.0, float(point[0]))),
                                     max(-20.0, min(20.0, float(point[1])))])
            except (TypeError, ValueError):
                continue
    room = payload.get("room") or {}
    clean_room = {}
    if isinstance(room, dict):
        for key in ("width_m", "depth_m", "bathroom_m2", "desk_niche_m2",
                    "bedroom_m2", "total_m2", "reference_scale", "yaw_scale",
                    "map_rotation_deg", "mirror_y", "mirror_center_m",
                    "snap_wall_objects", "eps_m"):
            if key in room:
                try:
                    clean_room[key] = round(float(room[key]), 3)
                except (TypeError, ValueError):
                    pass
        if "source" in room:
            clean_room["source"] = str(room["source"])[:40]
        if "area_source" in room:
            clean_room["area_source"] = str(room["area_source"])[:40]
        origin = room.get("sensor_origin_m")
        if isinstance(origin, (list, tuple)) and len(origin) >= 2:
            try:
                values = [round(float(origin[index]), 3)
                          for index in range(min(3, len(origin)))]
                clean_room["sensor_origin_m"] = values
            except (TypeError, ValueError):
                pass
    return {
        "labels": clean_labels,
        "size_overrides": clean_sizes,
        "hidden": clean_hidden,
        "removed": clean_removed,
        "merges": clean_merges,
        "point_labels": clean_point_labels,
        "label_catalog": clean_catalog,
        "manual_boxes": manual_boxes,
        "room_outline": room_outline,
        "room": clean_room,
    }


def _load_annotations(scan_id):
    return _clean_annotations(read_json(_scan_directory(scan_id) / "annotations.json", {}) or {})


def _save_annotations(scan_id, payload):
    annotations = _clean_annotations(payload)
    write_json(_scan_directory(scan_id) / "annotations.json", annotations)
    return annotations


def _mirror_defaults(annotations):
    """Return (mirror_y, center_m) for the hand-authored prior frame.

    Mirroring is the default because the physical yaw axis is opposite the
    prior/2D view. The centre comes from the prior room outline unless the
    annotation explicitly stores one.
    """
    room = annotations.get("room") or {}
    raw_mirror = room.get("mirror_y", 1.0)
    try:
        mirror_y = bool(float(raw_mirror))
    except (TypeError, ValueError):
        mirror_y = True
    center = room.get("mirror_center_m")
    try:
        center = float(center)
    except (TypeError, ValueError):
        center = None
    if center is None:
        ys = [float(point[1]) for point in (annotations.get("room_outline") or [])
              if isinstance(point, (list, tuple)) and len(point) >= 2]
        center = (min(ys) + max(ys)) / 2.0 if ys else 0.0
    return mirror_y, center


def _snap_default(annotations):
    room = annotations.get("room") or {}
    try:
        return bool(float(room.get("snap_wall_objects", 1.0)))
    except (TypeError, ValueError):
        return True


def _presence_from_status(status):
    sensors = status.get("sensors") or {}
    hlk = dict(sensors.get("hlk") or {})
    last = (status.get("hlk") or {}).get("last_reading") or {}
    for key in ("moving_energy", "stationary_energy",
                "moving_distance_cm", "stationary_distance_cm"):
        if hlk.get(key) is None and last.get(key) is not None:
            hlk[key] = last[key]
    tof = sensors.get("vl53l1x") or {}
    hc = sensors.get("hc_sr04") or {}
    ranges = []
    for sensor in (tof, hc):
        value = sensor.get("distance_cal_cm")
        if value is None:
            value = sensor.get("distance_cm")
        try:
            value = float(value)
        except (TypeError, ValueError):
            continue
        if 20.0 <= value <= 600.0:
            ranges.append(value)
    max_range_cm = max(ranges) if ranges else None
    scan_mode = bool((status.get("scan") or {}).get("mode"))
    with PRESENCE_LOCK:
        presence = PRESENCE.update(hlk, scanning=scan_mode,
                                   max_range_cm=max_range_cm)
    return {"presence": presence,
            "hlk_alert": status.get("hlk_alert"),
            "scan_mode": scan_mode,
            "mode": status.get("mode")}


def _list_scans():
    items = []
    if not SCANS.exists():
        return items
    for directory in sorted(SCANS.iterdir(), reverse=True):
        metadata = read_json(directory / "metadata.json")
        if isinstance(metadata, dict):
            items.append({
                "scan_id": metadata.get("scan_id", directory.name),
                "points": metadata.get("points", 0),
                "valid_points": metadata.get("valid_points", 0),
                "tof_points": metadata.get("tof_points", 0),
                "hc_points": metadata.get("hc_points", 0),
                "error": metadata.get("error"),
                "started_utc": metadata.get("started_utc"),
                "finished_utc": metadata.get("finished_utc"),
                "config": metadata.get("config", {}),
            })
    return items


def _sensor_height_m(scan_id):
    metadata = read_json(_scan_directory(scan_id) / "metadata.json", {}) or {}
    try:
        height_mm = float(metadata.get("sensor_height_mm", 770))
    except (TypeError, ValueError):
        height_mm = 770.0
    return round(max(0.20, min(3.0, height_mm / 1000.0)), 3)


def _points(scan_id):
    directory = _scan_directory(scan_id)
    path = directory / "points.csv"
    if not path.is_file():
        raise ValueError("scan not found")
    rows = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            converted = {}
            for key, value in row.items():
                if value == "":
                    converted[key] = None
                else:
                    try:
                        converted[key] = float(value)
                    except ValueError:
                        converted[key] = value
            rows.append(converted)
    return rows


def _start_scan(config: dict):
    if config.get("confirm_power") is not True:
        raise ValueError("power confirmation required: fix and measure the servo/5V rail before scanning")
    with ML_LOCK:
        if ML_JOB["state"] == "running":
            raise RuntimeError("dataset recording running; stop it before scanning")
    with JOB_LOCK:
        if JOB["state"] == "running":
            raise RuntimeError("scan already running")
        stop_event = threading.Event()
        JOB.update({"state": "running", "scan_id": None, "points": 0,
                    "total": 0, "error": None, "progress": {},
                    "stop_event": stop_event})
    scan_config = ScanConfig(
        yaw_step_deg=int(config.get("yaw_step_deg", 5)),
        tilt_step_us=int(config.get("tilt_step_us", 25)),
        dwell_ms=max(100, min(2000, int(config.get("dwell_ms", 400)))),
        samples=max(1, min(10, int(config.get("samples", 5)))),
        sample_interval_ms=max(50, min(1000, int(config.get("sample_interval_ms", 250)))),
        yaw_limit_deg=int(config.get("yaw_limit_deg", 45)),
        tilt_min_us=int(config.get("tilt_min_us", 500)),
        tilt_max_us=int(config.get("tilt_max_us", 950)),
        stepper_step_deg=int(config.get("stepper_step_deg", config.get("yaw_step_deg", 5))),
        servo_step_delay_s=max(0.05, min(0.5, float(config.get("servo_step_delay_s", 0.1)))),
        column_cooldown_s=max(0.0, min(5.0, float(config.get("column_cooldown_s", 0.5)))),
        release_stepper_during_sweep=bool(config.get("release_stepper_during_sweep", True)),
        label=str(config.get("label", ""))[:80],
    )
    scan_config.validate()

    def progress(value):
        with JOB_LOCK:
            JOB["progress"] = value
            if value.get("scan_id"):
                JOB["scan_id"] = value["scan_id"]
            JOB["points"] = value.get("points", JOB["points"])
            JOB["total"] = value.get("total", JOB["total"])

    def worker():
        try:
            result = run_scan(EspClient(), scan_config, progress=progress, stop_event=stop_event)
            with JOB_LOCK:
                JOB.update({"state": "done", "scan_id": result["scan_id"],
                            "points": result["points"], "total": result["points"],
                            "progress": {"phase": "done", **result}})
        except Exception as exc:
            with JOB_LOCK:
                JOB.update({"state": "error", "error": str(exc),
                            "progress": {"phase": "error", "error": str(exc)}})

    thread = threading.Thread(target=worker, daemon=True)
    with JOB_LOCK:
        JOB["thread"] = thread
    thread.start()


class Handler(BaseHTTPRequestHandler):
    server_version = "AIoTRoomMapping/1.0"

    def log_message(self, fmt, *args):
        return

    def _send(self, status, body, content_type="application/json"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        try:
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError, OSError):
            return

    def _body(self):
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0 or length > 1024 * 1024:
            raise ValueError("invalid body size")
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def _static(self, path):
        relative = unquote(path.lstrip("/")) or "index.html"
        if relative == "static":
            relative = "static/index.html"
        target = (STATIC / relative).resolve()
        if STATIC.resolve() not in target.parents and target != STATIC.resolve():
            raise ValueError("invalid static path")
        if not target.is_file():
            raise FileNotFoundError(relative)
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in (
                "application/javascript", "application/json"):
            content_type += "; charset=utf-8"
        self._send(200, target.read_bytes(), content_type)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            if path in ("/", "/index.html"):
                return self._static("index.html")
            if path.startswith("/static/"):
                return self._static(path[len("/static/"):])
            if path == "/api/mapping/health":
                try:
                    status = EspClient().status(timeout=4.0)
                    presence = _presence_from_status(status)
                    esp = {
                        "version": status.get("version"),
                        "mode": status.get("mode"),
                        "ip": status.get("wifi", {}).get("ip"),
                        "sensors": status.get("sensors"),
                        "actuators": status.get("actuators"),
                        "scan": status.get("scan"),
                        "hlk_alert": status.get("hlk_alert"),
                        "ml_alert": status.get("ml_alert"),
                        "hlk": status.get("hlk"),
                        "ml": status.get("ml"),
                    }
                    return self._send(200, {"ok": True, "esp": esp,
                                            "presence": presence["presence"],
                                            "scans": _list_scans(),
                                            "ml_metrics": _ml_metrics(),
                                            "track": _public_track(),
                                            "calibration": read_json(CALIBRATION, {}) or {}})
                except Exception as exc:
                    with PRESENCE_LOCK:
                        presence = PRESENCE.snapshot()
                    return self._send(200, {"ok": False, "error": str(exc),
                                            "presence": presence,
                                            "scans": _list_scans(),
                                            "ml_metrics": _ml_metrics(),
                                            "calibration": read_json(CALIBRATION, {}) or {}})
            if path == "/api/mapping/presence":
                try:
                    status = EspClient().status(timeout=4.0)
                    payload = _presence_from_status(status)
                    return self._send(200, {"ok": True, **payload})
                except Exception as exc:
                    with PRESENCE_LOCK:
                        presence = PRESENCE.snapshot()
                    return self._send(200, {"ok": False, "error": str(exc),
                                            "presence": presence})
            if path == "/api/mapping/status":
                return self._send(200, {"ok": True, "status": EspClient().status()})
            if path == "/api/mapping/scans":
                return self._send(200, {"ok": True, "scans": _list_scans()})
            if path == "/api/mapping/dataset":
                index_path = RESEARCH / "dataset" / "index.csv"
                runs = []
                if index_path.is_file():
                    with index_path.open("r", encoding="utf-8", newline="") as handle:
                        runs = list(csv.DictReader(handle))
                return self._send(200, {"ok": True, "runs": runs[-100:]})
            if path.startswith("/api/mapping/scans/") and path.endswith("/points"):
                scan_id = path[len("/api/mapping/scans/"):-len("/points")].strip("/")
                return self._send(200, {"ok": True, "scan_id": scan_id,
                                        "points": _points(scan_id)})
            if path.startswith("/api/mapping/scans/") and path.endswith("/reconstruct"):
                scan_id = path[len("/api/mapping/scans/"):-len("/reconstruct")].strip("/")
                params = parse_qs(parsed.query)
                try:
                    yaw_scale = float(params.get("yaw_scale", ["0.76"])[0])
                except (TypeError, ValueError):
                    yaw_scale = 0.76
                yaw_scale = max(0.50, min(1.00, yaw_scale))
                try:
                    map_rotation = float(params.get("map_rotation", ["10.7"])[0])
                except (TypeError, ValueError):
                    map_rotation = 10.7
                map_rotation = max(-45.0, min(45.0, map_rotation))
                annotations = _load_annotations(scan_id)
                mirror_default, center_default = _mirror_defaults(annotations)
                mirror_raw = params.get("mirror_y",
                                        ["1" if mirror_default else "0"])[0]
                mirror_y = str(mirror_raw).lower() not in ("0", "false", "off", "no")
                try:
                    mirror_center = float(params.get("mirror_center",
                                                     [str(center_default)])[0])
                except (TypeError, ValueError):
                    mirror_center = center_default
                snap_wall = _snap_default(annotations)
                snap_raw = params.get("snap_objects",
                                      ["1" if snap_wall else "0"])[0]
                snap_wall = str(snap_raw).lower() not in (
                    "0", "false", "off", "no")
                reconstruction = reconstruct_points(
                    _points(scan_id), yaw_scale=yaw_scale,
                    map_rotation_deg=map_rotation, annotations=annotations,
                    mirror_y=mirror_y, mirror_center_m=mirror_center,
                    snap_wall_objects=snap_wall, add_anchors=True)
                reconstruction["sensor_height_m"] = _sensor_height_m(scan_id)
                return self._send(200, {"ok": True, "scan_id": scan_id,
                                        "annotations": reconstruction.get("annotations", annotations),
                                        "reconstruction": reconstruction})
            if path.startswith("/api/mapping/scans/") and path.endswith("/annotations"):
                scan_id = path[len("/api/mapping/scans/"):-len("/annotations")].strip("/")
                return self._send(200, {"ok": True, "scan_id": scan_id,
                                        "annotations": _load_annotations(scan_id)})
            if path == "/api/mapping/scan/status":
                return self._send(200, {"ok": True, "job": _public_job()})
            if path == "/api/mapping/ml/status":
                return self._send(200, {"ok": True, "job": _public_ml()})
            if path == "/api/mapping/track/status":
                return self._send(200, {"ok": True, "track": _public_track()})
            if path == "/api/mapping/calibration":
                return self._send(200, {"ok": True,
                                        "calibration": read_json(CALIBRATION, {}) or {}})
            return self._send(404, {"ok": False, "error": "not_found"})
        except FileNotFoundError:
            return self._send(404, {"ok": False, "error": "not_found"})
        except Exception as exc:
            return self._send(500, {"ok": False, "error": str(exc)})

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            body = self._body()
            if path == "/api/mapping/command":
                command = str(body.get("command", ""))
                if not command:
                    raise ValueError("command required")
                return self._send(200, {"ok": True, "result": EspClient().command(command)})
            if path.startswith("/api/mapping/scans/") and path.endswith("/annotations"):
                scan_id = path[len("/api/mapping/scans/"):-len("/annotations")].strip("/")
                try:
                    yaw_scale = float(body.get("yaw_scale", 0.76))
                except (TypeError, ValueError):
                    yaw_scale = 0.76
                yaw_scale = max(0.50, min(1.00, yaw_scale))
                try:
                    map_rotation = float(body.get("map_rotation", 10.7))
                except (TypeError, ValueError):
                    map_rotation = 10.7
                map_rotation = max(-45.0, min(45.0, map_rotation))
                payload = body.get("annotations", body)
                if isinstance(payload, dict):
                    room = payload.setdefault("room", {})
                    if "mirror_y" in body:
                        room["mirror_y"] = body["mirror_y"]
                    if "mirror_center_m" in body:
                        room["mirror_center_m"] = body["mirror_center_m"]
                    if "snap_wall_objects" in body:
                        room["snap_wall_objects"] = body["snap_wall_objects"]
                annotations = _save_annotations(scan_id, payload)
                mirror_y, mirror_center = _mirror_defaults(annotations)
                snap_wall = _snap_default(annotations)
                reconstruction = reconstruct_points(
                    _points(scan_id), yaw_scale=yaw_scale,
                    map_rotation_deg=map_rotation, annotations=annotations,
                    mirror_y=mirror_y, mirror_center_m=mirror_center,
                    snap_wall_objects=snap_wall, add_anchors=True)
                reconstruction["sensor_height_m"] = _sensor_height_m(scan_id)
                return self._send(200, {"ok": True, "scan_id": scan_id,
                                        "annotations": reconstruction.get("annotations", annotations),
                                        "reconstruction": reconstruction})
            if path.startswith("/api/mapping/scans/") and path.endswith("/auto-align"):
                scan_id = path[len("/api/mapping/scans/"):-len("/auto-align")].strip("/")
                _scan_directory(scan_id)
                annotations = _load_annotations(scan_id)
                try:
                    yaw_scale = float(body.get("yaw_scale", 1.0))
                except (TypeError, ValueError):
                    yaw_scale = 1.0
                yaw_scale = max(0.50, min(1.10, yaw_scale))
                mirror_y, mirror_center = _mirror_defaults(annotations)
                if "mirror_y" in body:
                    mirror_y = str(body["mirror_y"]).lower() not in (
                        "0", "false", "off", "no")
                if "mirror_center_m" in body:
                    try:
                        mirror_center = float(body["mirror_center_m"])
                    except (TypeError, ValueError):
                        pass
                try:
                    search_min = max(-15.0, min(0.0, float(body.get("search_min", -5.0))))
                    search_max = min(15.0, max(0.0, float(body.get("search_max", 5.0))))
                except (TypeError, ValueError):
                    search_min, search_max = -5.0, 5.0
                result = auto_align_rotation(
                    _points(scan_id), yaw_scale=yaw_scale,
                    annotations=annotations, mirror_y=mirror_y,
                    mirror_center_m=mirror_center,
                    search_min=search_min, search_max=search_max)
                return self._send(200, {"ok": True, "scan_id": scan_id, **result})
            if path.startswith("/api/mapping/scans/") and path.endswith("/scene"):
                scan_id = path[len("/api/mapping/scans/"):-len("/scene")].strip("/")
                _scan_directory(scan_id)
                try:
                    yaw_scale = float(body.get("yaw_scale", 1.0))
                except (TypeError, ValueError):
                    yaw_scale = 1.0
                yaw_scale = max(0.50, min(1.00, yaw_scale))
                try:
                    map_rotation = float(body.get("map_rotation", 0.0))
                except (TypeError, ValueError):
                    map_rotation = 0.0
                map_rotation = max(-45.0, min(45.0, map_rotation))
                mirror_y = None
                if "mirror_y" in body:
                    mirror_y = str(body["mirror_y"]).lower() not in (
                        "0", "false", "off", "no")
                mirror_center = None
                if "mirror_center_m" in body:
                    try:
                        mirror_center = float(body["mirror_center_m"])
                    except (TypeError, ValueError):
                        mirror_center = None
                snap_objects = None
                if "snap_wall_objects" in body:
                    snap_objects = str(body["snap_wall_objects"]).lower() not in (
                        "0", "false", "off", "no")
                result = export_scene(scan_id, yaw_scale=yaw_scale,
                                      map_rotation_deg=map_rotation,
                                      mirror_y=mirror_y,
                                      mirror_center_m=mirror_center,
                                      snap_wall_objects=snap_objects)
                return self._send(200, result)
            if path.startswith("/api/mapping/scans/") and path.endswith("/export"):
                scan_id = path[len("/api/mapping/scans/"):-len("/export")].strip("/")
                _scan_directory(scan_id)
                result = export_run(
                    scan_id,
                    clean=bool(body.get("clean", False)),
                    run_label=str(body.get("run_label", ""))[:120],
                    notes=str(body.get("notes", ""))[:500],
                )
                return self._send(200, result)
            if path == "/api/mapping/presence/reset":
                with PRESENCE_LOCK:
                    PRESENCE.reset()
                return self._send(200, {"ok": True, "presence": PRESENCE.snapshot()})
            if path == "/api/mapping/scan/start":
                _start_scan(body)
                return self._send(202, {"ok": True, "job": _public_job()})
            if path == "/api/mapping/track/start":
                _start_track(body)
                return self._send(202, {"ok": True, "track": _public_track()})
            if path == "/api/mapping/track/stop":
                return self._send(200, _stop_track())
            if path == "/api/mapping/scan/stop":
                with JOB_LOCK:
                    event = JOB.get("stop_event")
                if event:
                    event.set()
                return self._send(200, {"ok": True, "message": "stop_requested"})
            if path == "/api/mapping/ml/start":
                _start_ml(body.get("label", "unlabeled"))
                return self._send(202, {"ok": True, "job": _public_ml()})
            if path == "/api/mapping/ml/stop":
                return self._send(200, _stop_ml())
            if path == "/api/mapping/calibration/capture":
                actual_cm = float(body["actual_cm"])
                samples = max(1, min(30, int(body.get("samples", 10))))
                label = str(body.get("label", ""))[:80]
                record = capture(EspClient(), actual_cm, samples, label)
                return self._send(200, {"ok": True, "record": record,
                                        "calibration": read_json(CALIBRATION, {}) or {}})
            return self._send(404, {"ok": False, "error": "not_found"})
        except Exception as exc:
            return self._send(400, {"ok": False, "error": str(exc)})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    RESEARCH.mkdir(parents=True, exist_ok=True)
    SCANS.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Mapping dashboard: http://{args.host}:{args.port}/")
    print("ESP32 credentials are read from tools/ops/device.local.json; never served to the browser.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
