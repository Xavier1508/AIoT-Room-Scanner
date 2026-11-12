#!/usr/bin/env python3
"""Bounded yaw sweep for a measured human bearing.

The LD2410C has no angle. The arm (and the HLK with it) is rotated in small
yaw steps; at each step ToF/HC are compared with the static scan background.
A return closer than the mapped surface is a candidate human. The final track
is a normal human-sized box at the measured bearing/distance, not a radial
marker at the parked yaw.
"""
from __future__ import annotations

import csv
import math
import time
from dataclasses import dataclass
from pathlib import Path

from common import (CALIBRATION, SCANS, median, read_json, tilt_from_pulse,
                    utc_iso)
from esp_client import EspClient
from reconstruct import reconstruct_points

OCCUPIABLE = {"bed"}
SOLID_SKIP = {"mount", "ceiling"}
MIN_RANGE_CM = 25.0
MAX_RANGE_CM = 450.0
MAX_BACKGROUND_CM = 600.0


def _box_corners(box):
    angle = math.radians(float(box.get("angle_deg", 0.0) or 0.0))
    ca, sa = math.cos(angle), math.sin(angle)
    cx, cy = float(box.get("cx_m", 0.0) or 0.0), float(box.get("cy_m", 0.0) or 0.0)
    hl = max(0.02, float(box.get("length_m", 0.1) or 0.1)) / 2.0
    hw = max(0.02, float(box.get("width_m", 0.1) or 0.1)) / 2.0
    return [
        (cx + u * ca - v * sa, cy + u * sa + v * ca)
        for u, v in ((-hl, -hw), (hl, -hw), (hl, hw), (-hl, hw))
    ]


def _point_in_polygon(x, y, polygon):
    if not polygon or len(polygon) < 3:
        return True
    inside = False
    for index, (x0, y0) in enumerate(polygon):
        x1, y1 = polygon[(index + 1) % len(polygon)]
        if (y0 > y) != (y1 > y):
            crossing = (x1 - x0) * (y - y0) / ((y1 - y0) or 1e-9) + x0
            if x < crossing:
                inside = not inside
    return inside


def _ray_box_t(box, ox, oy, dx, dy):
    angle = math.radians(float(box.get("angle_deg", 0.0) or 0.0))
    ca, sa = math.cos(angle), math.sin(angle)
    cx, cy = float(box.get("cx_m", 0.0) or 0.0), float(box.get("cy_m", 0.0) or 0.0)
    lx, ly = ox - cx, oy - cy
    ox_local = lx * ca + ly * sa
    oy_local = -lx * sa + ly * ca
    dx_local = dx * ca + dy * sa
    dy_local = -dx * sa + dy * ca
    hl = max(0.02, float(box.get("length_m", 0.1) or 0.1)) / 2.0
    hw = max(0.02, float(box.get("width_m", 0.1) or 0.1)) / 2.0
    tmin, tmax = -1e9, 1e9
    for origin, direction, lower, upper in (
            (ox_local, dx_local, -hl, hl),
            (oy_local, dy_local, -hw, hw)):
        if abs(direction) < 1e-9:
            if origin < lower or origin > upper:
                return None
            continue
        t1 = (lower - origin) / direction
        t2 = (upper - origin) / direction
        if t1 > t2:
            t1, t2 = t2, t1
        tmin = max(tmin, t1)
        tmax = min(tmax, t2)
        if tmin > tmax:
            return None
    if tmax < 0.0:
        return None
    if tmin < 0.0:
        # The origin is inside this box (mount/partition); skip it.
        return None
    return tmin


class BackgroundMap:
    def __init__(self, scan_id, boxes, polygon, origin, sensor_z,
                 map_rotation_deg, mirror_y, calibration):
        self.scan_id = scan_id
        self.boxes = boxes
        self.polygon = polygon
        self.origin = origin
        self.sensor_z = sensor_z
        self.map_rotation_deg = map_rotation_deg
        self.mirror_y = mirror_y
        self.calibration = calibration

    def display_yaw_deg(self, scan_yaw_deg):
        rotated = float(scan_yaw_deg) + self.map_rotation_deg
        return -rotated if self.mirror_y else rotated

    def inside_room(self, x, y):
        return _point_in_polygon(x, y, self.polygon)

    def solid_at(self, x, y, z):
        for box in self.boxes:
            label = str(box.get("label") or "object")
            if label in SOLID_SKIP or label in OCCUPIABLE:
                continue
            z0 = float(box.get("z_bottom_m", 0.0) or 0.0)
            z1 = float(box.get("z_top_m", 0.0) or 0.0)
            if z < z0 - 0.05 or z > z1 + 0.05:
                continue
            angle = math.radians(float(box.get("angle_deg", 0.0) or 0.0))
            ca, sa = math.cos(angle), math.sin(angle)
            lx = (x - float(box.get("cx_m", 0.0) or 0.0))
            ly = (y - float(box.get("cy_m", 0.0) or 0.0))
            u = lx * ca + ly * sa
            v = -lx * sa + ly * ca
            if (abs(u) <= abs(float(box.get("length_m", 0.0) or 0.0)) / 2.0 + 0.02
                    and abs(v) <= abs(float(box.get("width_m", 0.0) or 0.0)) / 2.0 + 0.02):
                return label
        return None

    def raycast_cm(self, scan_yaw_deg, tilt_us):
        yaw = math.radians(self.display_yaw_deg(scan_yaw_deg))
        dx, dy = math.cos(yaw), math.sin(yaw)
        tilt = math.radians(tilt_from_pulse(tilt_us, self.calibration))
        tangent = math.tan(tilt)
        ox, oy = self.origin
        best = MAX_BACKGROUND_CM
        for box in self.boxes:
            label = str(box.get("label") or "")
            if label in SOLID_SKIP:
                continue
            t = _ray_box_t(box, ox, oy, dx, dy)
            if t is None or t <= 0.15:
                continue
            z = self.sensor_z + t * tangent
            z0 = float(box.get("z_bottom_m", 0.0) or 0.0)
            z1 = float(box.get("z_top_m", 0.0) or 0.0)
            if z0 - 0.06 <= z <= z1 + 0.06:
                best = min(best, t * 100.0)
        return round(best, 1)

    def snapshot(self):
        return {
            "scan_id": self.scan_id,
            "origin_m": [round(self.origin[0], 3), round(self.origin[1], 3)],
            "sensor_z_m": round(self.sensor_z, 3),
            "map_rotation_deg": round(self.map_rotation_deg, 2),
            "mirror_y": self.mirror_y,
            "boxes": len(self.boxes),
            "polygon": [[round(x, 3), round(y, 3)] for x, y in self.polygon],
        }


_BACKGROUND_CACHE = {}


def load_background(scan_id=None):
    if scan_id and scan_id in _BACKGROUND_CACHE:
        return _BACKGROUND_CACHE[scan_id]
    candidates = []
    if scan_id:
        candidates.append(scan_id)
    if SCANS.is_dir():
        candidates.extend(directory.name for directory in sorted(SCANS.iterdir(), reverse=True))
    selected = None
    for candidate in candidates:
        directory = SCANS / candidate
        if (directory / "points.csv").is_file():
            selected = candidate
            break
    if not selected:
        raise RuntimeError("No scan points.csv found for tracking background.")
    directory = SCANS / selected
    annotations = read_json(directory / "annotations.json", {}) or {}
    room = annotations.get("room") or {}
    rows = list(csv.DictReader((directory / "points.csv").open(encoding="utf-8")))
    result = reconstruct_points(
        rows,
        yaw_scale=float(room.get("yaw_scale", 1.0) or 1.0),
        map_rotation_deg=float(room.get("map_rotation_deg", 0.0) or 0.0),
        annotations=annotations,
        mirror_y=bool(float(room.get("mirror_y", 1.0) or 1.0)),
        mirror_center_m=float(room.get("mirror_center_m", 0.0) or 0.0),
        snap_wall_objects=bool(float(room.get("snap_wall_objects", 1.0) or 1.0)),
        add_anchors=True,
    )
    boxes = [box for box in (result.get("boxes") or [])
             if str(box.get("label") or "") not in SOLID_SKIP]
    origin = room.get("sensor_origin_m")
    if isinstance(origin, (list, tuple)) and len(origin) >= 2:
        sensor_x, sensor_y = float(origin[0]), float(origin[1])
    else:
        partition = next((box for box in boxes
                          if str(box.get("label")) == "partition"
                          and str(box.get("source")) == "prior"), None)
        if partition:
            sensor_x = float(partition.get("cx_m", 0.0))
            sensor_y = float(partition.get("cy_m", 0.0))
        else:
            mirror_center = float(room.get("mirror_center_m", 0.0) or 0.0)
            sensor_x = 0.0
            sensor_y = 2.0 * mirror_center if bool(float(room.get("mirror_y", 1.0) or 1.0)) else 0.0
    wall_points = []
    for box in boxes:
        if str(box.get("label")) in ("wall", "wall_edge"):
            wall_points.extend(_box_corners(box))
    if wall_points:
        xs = [point[0] for point in wall_points]
        ys = [point[1] for point in wall_points]
        pad = 0.12
        polygon = [(min(xs) - pad, min(ys) - pad), (max(xs) + pad, min(ys) - pad),
                   (max(xs) + pad, max(ys) + pad), (min(xs) - pad, max(ys) + pad)]
    else:
        width = float(room.get("width_m", 2.7) or 2.7)
        depth = float(room.get("depth_m", 2.5) or 2.5)
        polygon = [(sensor_x - width / 2, sensor_y - depth / 2),
                   (sensor_x + width / 2, sensor_y - depth / 2),
                   (sensor_x + width / 2, sensor_y + depth / 2),
                   (sensor_x - width / 2, sensor_y + depth / 2)]
    calibration = read_json(CALIBRATION, {}) or {}
    sensor_z = float(calibration.get("sensor_height_mm", 770) or 770) / 1000.0
    background = BackgroundMap(
        selected, boxes, polygon, (sensor_x, sensor_y), sensor_z,
        float(room.get("map_rotation_deg", 0.0) or 0.0),
        bool(float(room.get("mirror_y", 1.0) or 1.0)),
        calibration,
    )
    _BACKGROUND_CACHE[selected] = background
    return background


def _sample_distance(status):
    sensors = status.get("sensors") or {}
    tof = sensors.get("vl53l1x") or {}
    hc = sensors.get("hc_sr04") or {}
    for source, sensor in (("tof", tof), ("hc", hc)):
        value = sensor.get("distance_cal_cm")
        if value is None:
            value = sensor.get("distance_cm")
        try:
            value = float(value)
        except (TypeError, ValueError):
            continue
        if sensor.get("valid") and MIN_RANGE_CM <= value <= MAX_RANGE_CM:
            return round(value, 1), source
    return None, ""


def _sample_hlk(status):
    sensors = status.get("sensors") or {}
    hlk = sensors.get("hlk") or {}
    last = (status.get("hlk") or {}).get("last_reading") or {}
    distance = hlk.get("distance_cm")
    energy = hlk.get("energy")
    if distance in (None, 0) and last.get("detection_distance_cm") is not None:
        distance = last.get("detection_distance_cm")
    if energy in (None, 0) and last.get("stationary_energy") is not None:
        energy = max(float(last.get("stationary_energy") or 0),
                     float(last.get("moving_energy") or 0))
    try:
        return float(distance) if distance is not None else None, float(energy or 0)
    except (TypeError, ValueError):
        return None, 0.0


def estimate_track(samples, background, threshold_cm=15.0):
    candidates = []
    for sample in samples:
        distance = sample.get("range_cm")
        baseline = sample.get("background_cm")
        if distance is None or baseline is None:
            continue
        delta = float(baseline) - float(distance)
        sample["delta_cm"] = round(delta, 1)
        hlk_cm = sample.get("hlk_cm")
        hlk_energy = float(sample.get("hlk_energy") or 0)
        hlk_ok = (hlk_cm is not None and hlk_energy >= 40
                  and abs(float(hlk_cm) - float(distance)) <= 60.0)
        sample["hlk_match"] = bool(hlk_ok)
        if delta >= threshold_cm and hlk_ok and MIN_RANGE_CM <= float(distance) <= MAX_RANGE_CM:
            candidates.append(sample)
    hlk_samples = [sample for sample in samples
                   if (sample.get("hlk_energy") or 0) >= 40
                   and sample.get("hlk_cm") is not None
                   and 30 <= float(sample.get("hlk_cm") or 0) <= 600]
    if not candidates:
        state = "radar" if hlk_samples else "empty"
        return {
            "state": state, "confirmed": False, "bearing_deg": None,
            "distance_cm": None, "x_m": None, "y_m": None,
            "height_m": 1.7, "z_bottom_m": 0.0, "confidence": 0.0,
            "reason": "hlk_only" if hlk_samples else "no_target",
            "candidates": 0,
        }
    weights = []
    for sample in candidates:
        weight = max(0.1, min(1.0, float(sample["delta_cm"]) / 80.0))
        weight *= 1.0 + min(1.0, float(sample.get("hlk_energy") or 0) / 180.0) * 0.35
        weights.append(weight)
    total = sum(weights) or 1.0
    display_angles = [background.display_yaw_deg(sample["yaw_deg"]) for sample in candidates]
    bearing = sum(angle * weight for angle, weight in zip(display_angles, weights)) / total
    distance = median([float(sample["range_cm"]) for sample in candidates])
    yaw = math.radians(bearing)
    x = background.origin[0] + (distance / 100.0) * math.cos(yaw)
    y = background.origin[1] + (distance / 100.0) * math.sin(yaw)
    tilt = math.radians(tilt_from_pulse(candidates[0].get("tilt_us", 800),
                                        background.calibration))
    z = background.sensor_z + (distance / 100.0) * math.tan(tilt)
    inside = background.inside_room(x, y)
    solid = background.solid_at(x, y, z)
    confirmed = len(candidates) >= 2 and inside and solid is None
    reason = "confirmed" if confirmed else (
        "outside_room" if not inside else f"inside_{solid}" if solid else "single_sample")
    confidence = 0.0
    if confirmed:
        confidence = min(0.99, 0.45 + 0.003 * sum(float(s["delta_cm"]) for s in candidates)
                         + 0.0015 * sum(float(s.get("hlk_energy") or 0) for s in candidates)
                         + 0.05 * len(candidates))
    return {
        "state": "confirmed" if confirmed else "radar",
        "confirmed": confirmed,
        "bearing_deg": round(bearing, 1),
        "scan_yaw_deg": round(median([float(s["yaw_deg"]) for s in candidates]), 1),
        "distance_cm": round(distance, 1),
        "x_m": round(x, 3),
        "y_m": round(y, 3),
        "height_m": 1.7,
        "z_bottom_m": 0.0,
        "confidence": round(confidence, 3),
        "reason": reason,
        "candidates": len(candidates),
    }


class TrackSmoother:
    def __init__(self, stale_s=3.0):
        self.stale_s = max(1.0, float(stale_s))
        self.last = None
        self.last_seen = 0.0
        self.velocity = (0.0, 0.0)

    def update(self, estimate, now):
        if estimate.get("state") == "confirmed" and estimate.get("x_m") is not None:
            x, y = float(estimate["x_m"]), float(estimate["y_m"])
            if self.last:
                dt = max(0.2, float(now) - self.last_seen)
                vx = (x - self.last["x_m"]) / dt
                vy = (y - self.last["y_m"]) / dt
                self.velocity = (0.55 * self.velocity[0] + 0.45 * vx,
                                 0.55 * self.velocity[1] + 0.45 * vy)
                x = self.last["x_m"] + 0.68 * (x - self.last["x_m"])
                y = self.last["y_m"] + 0.68 * (y - self.last["y_m"])
            track = dict(estimate)
            track.update({"x_m": round(x, 3), "y_m": round(y, 3),
                          "state": "confirmed", "age_s": 0.0})
            self.last = track
            self.last_seen = float(now)
            return track
        if self.last:
            age = max(0.0, float(now) - self.last_seen)
            track = dict(self.last)
            track["age_s"] = round(age, 1)
            if age > self.stale_s:
                track["state"] = "stale"
                track["confirmed"] = False
                track["reason"] = "stale"
            else:
                track["state"] = "predicted"
                track["confirmed"] = False
                track["x_m"] = round(track["x_m"] + self.velocity[0] * age, 3)
                track["y_m"] = round(track["y_m"] + self.velocity[1] * age, 3)
            return track
        return estimate


@dataclass
class TrackingConfig:
    scan_id: str = ""
    yaw_limit_deg: int = 60
    coarse_step_deg: int = 10
    fine_step_deg: int = 5
    tilt_us: int = 800
    samples: int = 2
    dwell_ms: int = 150
    sample_interval_ms: int = 100
    servo_delay_s: float = 0.1
    interval_s: float = 1.0
    threshold_cm: float = 15.0


def _targets(limit_deg, step_deg):
    count = int(round(limit_deg * 2 / step_deg))
    return [(-limit_deg + index * step_deg) for index in range(count + 1)]


def _sample(client, target_deg, background, config, progress, stop_event):
    if stop_event is not None and stop_event.is_set():
        raise InterruptedError("tracking stopped")
    state = client.move_stepper_to(
        int(round(target_deg * 4096 / 360 / 57)) * 57,
        settle_s=0.25, step_deg=config.coarse_step_deg)
    time.sleep(max(0.0, config.dwell_ms) / 1000.0)
    statuses = []
    for index in range(max(1, config.samples)):
        statuses.append(client.status())
        if index + 1 < max(1, config.samples):
            time.sleep(max(0.02, config.sample_interval_ms) / 1000.0)
    status = statuses[-1]
    scan_yaw = float((status.get("scan") or {}).get("yaw_deg_nominal", target_deg) or target_deg)
    distance, source = _sample_distance(status)
    hlk_cm, hlk_energy = _sample_hlk(status)
    background_cm = background.raycast_cm(scan_yaw, config.tilt_us)
    sample = {
        "yaw_deg": round(scan_yaw, 1),
        "tilt_us": config.tilt_us,
        "range_cm": distance,
        "source": source,
        "background_cm": background_cm,
        "hlk_cm": round(hlk_cm, 1) if hlk_cm is not None else None,
        "hlk_energy": int(hlk_energy),
    }
    if progress:
        progress({"phase": "sampling", "target_deg": target_deg,
                  "sample": sample, "background": background.snapshot()})
    return sample


def run_tracking_sweep(client, config, progress=None, stop_event=None):
    background = load_background(config.scan_id or None)
    client.ensure_sensors()
    client.command("ml_alert_off")
    client.command("hlk_alert_off")
    current = client.status()
    steps = int(current["actuators"]["relative_half_steps"])
    if steps % 57 != 0:
        raise RuntimeError("Stepper reference is not aligned to 5-degree units.")
    client.command("park_servo")
    client.servo_to(config.tilt_us, step_delay_s=config.servo_delay_s)
    time.sleep(0.25)
    samples = []
    try:
        targets = _targets(config.yaw_limit_deg, config.coarse_step_deg)
        for index, target in enumerate(targets):
            if progress:
                progress({"phase": "sweeping", "index": index + 1,
                          "total": len(targets), "target_deg": target,
                          "estimate": estimate_track(samples, background, config.threshold_cm)})
            samples.append(_sample(client, target, background, config, progress, stop_event))
        estimate = estimate_track(samples, background, config.threshold_cm)
        best = None
        if estimate.get("scan_yaw_deg") is not None:
            best = float(estimate["scan_yaw_deg"])
        if best is not None:
            fine_targets = []
            for delta in (-2 * config.fine_step_deg, -config.fine_step_deg,
                          config.fine_step_deg, 2 * config.fine_step_deg):
                target = best + delta
                if -config.yaw_limit_deg <= target <= config.yaw_limit_deg:
                    fine_targets.append(target)
            for target in fine_targets:
                samples.append(_sample(client, target, background, config, progress, stop_event))
        estimate = estimate_track(samples, background, config.threshold_cm)
        return {"estimate": estimate, "samples": samples,
                "background": background.snapshot()}
    finally:
        try:
            client.move_stepper_to(0, settle_s=0.2, step_deg=config.coarse_step_deg)
            client.command("park_stepper")
        finally:
            try:
                client.command("release_servo")
            except Exception:
                pass
            try:
                client.command("release_stepper")
            except Exception:
                pass


def run_tracking_loop(client, config, progress=None, stop_event=None):
    smoother = TrackSmoother()
    last = None
    try:
        while stop_event is None or not stop_event.is_set():
            result = run_tracking_sweep(client, config, progress, stop_event)
            last = smoother.update(result["estimate"], time.time())
            if progress:
                progress({"phase": "tracking", "estimate": last,
                          "samples": result["samples"], "background": result["background"]})
            until = time.monotonic() + max(0.5, config.interval_s)
            while time.monotonic() < until:
                if stop_event is not None and stop_event.is_set():
                    break
                time.sleep(0.1)
    except InterruptedError:
        pass
    finally:
        try:
            client.move_stepper_to(0, settle_s=0.2, step_deg=config.coarse_step_deg)
            client.command("park_stepper")
            client.command("release_servo")
            client.command("release_stepper")
        except Exception:
            pass
    return last
