#!/usr/bin/env python3
"""Measured human tracking for a range-only HLK radar.

The LD2410C has no angle. The arm rotates the sensor cluster in 5/10 degree
steps; at each step ToF/HC are compared with the *measured* static scan
background for that yaw and tilt. A return closer than the scan surface is a
candidate. Adjacent candidates are clustered before a bearing is computed, so
a wall return and a real target at another angle can never average into one
false position.

After the first confirmed bearing the arm parks on that bearing. The lock loop
keeps sampling ToF/HC without rotating, so the box follows the person moving
closer/farther. If the beam loses the person, a short local sweep reacquires
the bearing, then a full sweep is the last resort.
"""
from __future__ import annotations

import csv
import math
import time
from dataclasses import dataclass

from common import (CALIBRATION, SCANS, median, read_json, tilt_from_pulse)
from reconstruct import reconstruct_points

OCCUPIABLE = {"bed"}
SOLID_SKIP = {"mount", "ceiling"}
MIN_RANGE_CM = 25.0
MAX_RANGE_CM = 450.0
MAX_BACKGROUND_CM = 600.0
HUMAN_HEIGHT_M = 1.7


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


class ScanRangeMap:
    """Static range lookup from the measured scan rows.

    A ray-cast from approximate boxes can be 10-30 cm away from the real wall.
    That was enough to confirm a wall as a person. The scan CSV contains the
    actual ToF/HC range for every yaw and servo pulse, so use that directly.
    """

    def __init__(self, scan_id, rows):
        self.scan_id = scan_id
        self.rows = []
        for row in rows:
            try:
                distance_cm = float(row.get("range_mm") or 0.0) / 10.0
                yaw_deg = float(row.get("yaw_deg") or 0.0)
                servo_us = int(float(row.get("servo_us") or 0))
            except (TypeError, ValueError):
                continue
            source = str(row.get("range_source") or "")
            if source not in ("tof", "hc"):
                continue
            if not (MIN_RANGE_CM <= distance_cm <= MAX_BACKGROUND_CM):
                continue
            self.rows.append((yaw_deg, servo_us, distance_cm, source))

    def __bool__(self):
        return bool(self.rows)

    def range_cm(self, scan_yaw_deg, tilt_us):
        if not self.rows:
            return None
        exact = [row for row in self.rows
                 if row[1] == int(tilt_us) and abs(row[0] - float(scan_yaw_deg)) <= 0.8]
        if exact:
            return round(median([row[2] for row in exact]), 1)
        near = [row for row in self.rows
                if abs(row[1] - int(tilt_us)) <= 50
                and abs(row[0] - float(scan_yaw_deg)) <= 2.6]
        if not near:
            return None
        servo_delta = min(abs(row[1] - int(tilt_us)) for row in near)
        near = [row for row in near if abs(row[1] - int(tilt_us)) == servo_delta]
        yaw_delta = min(abs(row[0] - float(scan_yaw_deg)) for row in near)
        near = [row for row in near if abs(row[0] - float(scan_yaw_deg)) == yaw_delta]
        return round(median([row[2] for row in near]), 1)

    def snapshot(self):
        return {"scan_id": self.scan_id, "cells": len(self.rows)}


class BackgroundMap:
    def __init__(self, scan_id, boxes, polygon, origin, sensor_z,
                 map_rotation_deg, mirror_y, calibration, scan_range=None):
        self.scan_id = scan_id
        self.boxes = boxes
        self.polygon = polygon
        self.origin = origin
        self.sensor_z = sensor_z
        self.map_rotation_deg = map_rotation_deg
        self.mirror_y = mirror_y
        self.calibration = calibration
        self.scan_range = scan_range

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
        """Box ray-cast fallback used when the scan has no matching row."""
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

    def background_cm(self, scan_yaw_deg, tilt_us):
        if self.scan_range:
            measured = self.scan_range.range_cm(scan_yaw_deg, tilt_us)
            if measured is not None:
                return measured
        return self.raycast_cm(scan_yaw_deg, tilt_us)

    def snapshot(self):
        return {
            "scan_id": self.scan_id,
            "origin_m": [round(self.origin[0], 3), round(self.origin[1], 3)],
            "sensor_z_m": round(self.sensor_z, 3),
            "map_rotation_deg": round(self.map_rotation_deg, 2),
            "mirror_y": self.mirror_y,
            "boxes": len(self.boxes),
            "scan_cells": len(self.scan_range.rows) if self.scan_range else 0,
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
        scan_range=ScanRangeMap(selected, rows),
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


def _polar(background, scan_yaw_deg, distance_cm, tilt_us):
    bearing = background.display_yaw_deg(scan_yaw_deg)
    yaw = math.radians(bearing)
    x = background.origin[0] + (float(distance_cm) / 100.0) * math.cos(yaw)
    y = background.origin[1] + (float(distance_cm) / 100.0) * math.sin(yaw)
    tilt = math.radians(tilt_from_pulse(tilt_us, background.calibration))
    z = background.sensor_z + (float(distance_cm) / 100.0) * math.tan(tilt)
    return round(bearing, 1), x, y, z


def _cluster_candidates(candidates, max_gap_deg=11.0):
    ordered = sorted(candidates, key=lambda sample: float(sample["yaw_deg"]))
    clusters = []
    for sample in ordered:
        if (clusters
                and abs(float(sample["yaw_deg"]) - float(clusters[-1][-1]["yaw_deg"]))
                <= max_gap_deg):
            clusters[-1].append(sample)
        else:
            clusters.append([sample])
    return clusters


def _cluster_estimate(cluster, background):
    weights = []
    for sample in cluster:
        weight = max(0.1, min(1.0, float(sample["delta_cm"]) / 80.0))
        weight *= 1.0 + min(1.0, float(sample.get("hlk_energy") or 0) / 180.0) * 0.35
        weights.append(weight)
    total = sum(weights) or 1.0
    display_angles = [background.display_yaw_deg(sample["yaw_deg"]) for sample in cluster]
    bearing = sum(angle * weight for angle, weight in zip(display_angles, weights)) / total
    distance = median([float(sample["range_cm"]) for sample in cluster])
    scan_yaw = median([float(sample["yaw_deg"]) for sample in cluster])
    tilt_us = int(cluster[0].get("tilt_us", 800) or 800)
    measured_bearing, x, y, z = _polar(background, scan_yaw, distance, tilt_us)
    inside = background.inside_room(x, y)
    solid = background.solid_at(x, y, z)
    span = max(float(sample["yaw_deg"]) for sample in cluster) - min(
        float(sample["yaw_deg"]) for sample in cluster)
    spread = max(float(sample["range_cm"]) for sample in cluster) - min(
        float(sample["range_cm"]) for sample in cluster)
    tof_count = sum(1 for sample in cluster
                    if str(sample.get("source") or "tof") == "tof")
    confirmed = (len(cluster) >= 2 and span >= 4.0 and tof_count >= 1
                 and spread <= 55.0 and inside and solid is None)
    if confirmed:
        reason = "confirmed"
    elif not inside:
        reason = "outside_room"
    elif solid:
        reason = f"inside_{solid}"
    elif len(cluster) < 2:
        reason = "single_sample"
    elif tof_count < 1:
        reason = "hc_only"
    elif span < 4.0:
        reason = "too_narrow"
    else:
        reason = "distance_spread"
    confidence = 0.0
    if confirmed:
        confidence = min(0.99, 0.48 + 0.0025 * sum(float(s["delta_cm"]) for s in cluster)
                         + 0.0012 * sum(float(s.get("hlk_energy") or 0) for s in cluster)
                         + 0.05 * len(cluster))
    return {
        "state": "confirmed" if confirmed else "radar",
        "confirmed": confirmed,
        "bearing_deg": round(measured_bearing, 1),
        "scan_yaw_deg": round(scan_yaw, 1),
        "distance_cm": round(distance, 1),
        "x_m": round(x, 3),
        "y_m": round(y, 3),
        "height_m": HUMAN_HEIGHT_M,
        "z_bottom_m": 0.0,
        "confidence": round(confidence, 3),
        "reason": reason,
        "candidates": len(cluster),
        "tof_count": tof_count,
        "span_deg": round(span, 1),
        "spread_cm": round(spread, 1),
        "tilt_us": tilt_us,
        "radar_distance_cm": round(distance, 1),
    }


def _candidate_samples(samples, threshold_cm):
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
    return candidates


def _hlk_samples(samples):
    return [sample for sample in samples
            if (sample.get("hlk_energy") or 0) >= 40
            and sample.get("hlk_cm") is not None
            and 30 <= float(sample.get("hlk_cm") or 0) <= 600]


def estimate_track(samples, background, threshold_cm=20.0):
    candidates = _candidate_samples(samples, threshold_cm)
    hlk_samples = _hlk_samples(samples)
    if not candidates:
        state = "radar" if hlk_samples else "empty"
        hlk_distances = [float(sample["hlk_cm"]) for sample in hlk_samples
                         if sample.get("hlk_cm") is not None]
        radar_distance = round(median(hlk_distances), 1) if hlk_distances else None
        last_sample = samples[-1] if samples else {}
        return {
            "state": state, "confirmed": False, "bearing_deg": None,
            "distance_cm": None, "x_m": None, "y_m": None,
            "height_m": HUMAN_HEIGHT_M, "z_bottom_m": 0.0, "confidence": 0.0,
            "reason": "hlk_only" if hlk_samples else "no_target",
            "candidates": 0, "clusters": 0,
            "radar_distance_cm": radar_distance,
            "scan_yaw_deg": last_sample.get("yaw_deg"),
            "tilt_us": int(last_sample.get("tilt_us", 725) or 725),
        }
    clusters = _cluster_candidates(candidates)
    estimates = [_cluster_estimate(cluster, background) for cluster in clusters]
    confirmed = [estimate for estimate in estimates if estimate["confirmed"]]
    if confirmed:
        best = max(confirmed, key=lambda item: (item["candidates"],
                                                item["confidence"]))
    else:
        best = max(estimates, key=lambda item: (item["candidates"],
                                                item["confidence"]))
    best["clusters"] = len(clusters)
    best["candidates_total"] = len(candidates)
    return best


class TrackSmoother:
    def __init__(self, stale_s=3.0, expire_s=40.0, predict_s=1.5):
        self.stale_s = max(0.5, float(stale_s))
        self.expire_s = max(self.stale_s, float(expire_s))
        self.predict_s = max(0.2, float(predict_s))
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
            if age > self.expire_s:
                return estimate
            track = dict(self.last)
            track["age_s"] = round(age, 1)
            if age <= self.predict_s:
                track["state"] = "predicted"
                track["confirmed"] = False
                track["x_m"] = round(track["x_m"] + self.velocity[0] * age, 3)
                track["y_m"] = round(track["y_m"] + self.velocity[1] * age, 3)
            else:
                track["state"] = "stale"
                track["confirmed"] = False
                track["reason"] = "stale"
            return track
        return estimate


@dataclass
class TrackingConfig:
    scan_id: str = ""
    yaw_limit_deg: int = 60
    coarse_step_deg: int = 10
    fine_step_deg: int = 5
    tilt_us: int = 725
    samples: int = 1
    dwell_ms: int = 100
    sample_interval_ms: int = 100
    servo_delay_s: float = 0.1
    interval_s: float = 1.0
    threshold_cm: float = 20.0
    lock_threshold_cm: float = 18.0
    lock_sample_ms: int = 200
    lock_lost_s: float = 2.0
    lock_verify_s: float = 1.0
    local_limit_deg: int = 40
    near_field_tilt_us: int = 800
    near_field_hlk_cm: float = 100.0
    near_field_max_cm: float = 150.0
    expire_s: float = 40.0


def _targets(center_deg, span_deg, step_deg, arm_limit_deg=60.0,
             order="center", reverse=False):
    targets = []
    seen = set()

    def add(value):
        value = round(float(value), 1)
        if value < -arm_limit_deg - 1e-6 or value > arm_limit_deg + 1e-6:
            return
        key = int(round(value))
        if key in seen:
            return
        seen.add(key)
        targets.append(value)

    if order == "sequential":
        start = float(center_deg) - float(span_deg)
        end = float(center_deg) + float(span_deg)
        value = start
        while value <= end + 1e-6:
            add(value)
            value += float(step_deg)
        if reverse:
            targets.reverse()
        return targets
    add(center_deg)
    distance = int(step_deg)
    while distance <= int(span_deg):
        add(float(center_deg) - distance)
        add(float(center_deg) + distance)
        distance += int(step_deg)
    return targets


def _prepare_tracking(client, config, on_status=None):
    client.ensure_sensors()
    client.command("ml_alert_off")
    client.command("hlk_alert_off")
    current = client.status()
    if on_status:
        on_status(current)
    steps = int(current["actuators"]["relative_half_steps"])
    if steps % 57 != 0:
        raise RuntimeError("Stepper reference is not aligned to 5-degree units.")
    client.command("park_servo")
    client.servo_to(config.tilt_us, step_delay_s=config.servo_delay_s)
    time.sleep(0.25)


def _park_tracking(client, config):
    try:
        try:
            client.move_stepper_to(0, settle_s=0.2, step_deg=config.coarse_step_deg)
            client.command("park_stepper")
        except Exception:
            pass
    finally:
        for command in ("release_servo", "release_stepper"):
            try:
                client.command(command)
            except Exception:
                pass


def _sample(client, target_deg, background, config, step_deg, on_status=None):
    half_steps = int(round(float(target_deg) * 4096.0 / 360.0 / 57.0)) * 57
    client.move_stepper_to(half_steps, settle_s=0.15, step_deg=step_deg,
                           fast_wait=True)
    time.sleep(max(0.0, config.dwell_ms) / 1000.0)
    statuses = []
    for index in range(max(1, config.samples)):
        statuses.append(client.status())
        if index + 1 < max(1, config.samples):
            time.sleep(max(0.02, config.sample_interval_ms) / 1000.0)
    status = statuses[-1]
    if on_status:
        on_status(status)
    scan_yaw = float((status.get("scan") or {}).get("yaw_deg_nominal", target_deg) or target_deg)
    distance, source = _sample_distance(status)
    hlk_cm, hlk_energy = _sample_hlk(status)
    tilt_us = int(config.tilt_us)
    background_cm = background.background_cm(scan_yaw, tilt_us)
    delta = (background_cm - distance) if distance is not None and background_cm is not None else None
    near_field = (hlk_cm is not None
                  and float(hlk_cm) <= float(config.near_field_hlk_cm)
                  and (distance is None or delta is None or delta < config.threshold_cm))
    if near_field:
        try:
            client.servo_to(config.near_field_tilt_us, step_delay_s=0.05)
            time.sleep(0.08)
            near_status = client.status()
            if on_status:
                on_status(near_status)
            near_distance, near_source = _sample_distance(near_status)
            near_yaw = float((near_status.get("scan") or {}).get("yaw_deg_nominal", scan_yaw)
                             or scan_yaw)
            near_background = background.background_cm(near_yaw, config.near_field_tilt_us)
            near_delta = ((near_background - near_distance)
                          if near_distance is not None and near_background is not None else None)
            if (near_distance is not None and near_source == "tof"
                    and near_delta is not None
                    and near_delta >= config.threshold_cm
                    and near_distance <= config.near_field_max_cm):
                scan_yaw = near_yaw
                distance = near_distance
                source = near_source
                background_cm = near_background
                tilt_us = int(config.near_field_tilt_us)
                hlk_cm, hlk_energy = _sample_hlk(near_status)
        except Exception:
            pass
        finally:
            try:
                client.servo_to(config.tilt_us, step_delay_s=0.05)
            except Exception:
                pass
    return {
        "yaw_deg": round(scan_yaw, 1),
        "tilt_us": tilt_us,
        "range_cm": distance,
        "source": source,
        "background_cm": background_cm,
        "hlk_cm": round(hlk_cm, 1) if hlk_cm is not None else None,
        "hlk_energy": int(hlk_energy),
    }


def _emit(progress, phase, estimate, samples=None, background=None, final=False):
    if not progress:
        return
    value = {"phase": phase, "estimate": estimate}
    if samples is not None:
        value["samples"] = samples
    if background is not None:
        value["background"] = background
    if final:
        value["final"] = True
    progress(value)


def run_tracking_sweep(client, config, progress=None, stop_event=None, background=None,
                       center_deg=0.0, span_deg=None, step_deg=None, local=False,
                       prepare=True, reverse=False, targets=None,
                       initial_samples=None, early_stop_confirmed=False,
                       on_status=None):
    if background is None:
        background = load_background(config.scan_id or None)
    if prepare:
        _prepare_tracking(client, config, on_status=on_status)
    try:
        client.servo_to(config.tilt_us, step_delay_s=config.servo_delay_s)
    except Exception:
        pass
    span = config.yaw_limit_deg if span_deg is None else min(config.yaw_limit_deg, span_deg)
    step = int(config.coarse_step_deg if step_deg is None else step_deg)
    if targets is None:
        targets = _targets(center_deg, span, step, config.yaw_limit_deg,
                           order="center" if local else "sequential",
                           reverse=reverse)
    else:
        targets = list(targets)
    samples = list(initial_samples or [])
    try:
        for index, target in enumerate(targets):
            if stop_event is not None and stop_event.is_set():
                raise InterruptedError("tracking stopped")
            samples.append(_sample(client, target, background, config, step,
                                   on_status=on_status))
            estimate = estimate_track(samples, background, config.threshold_cm)
            if progress:
                progress({"phase": "sweeping", "index": index + 1,
                          "total": len(targets), "target_deg": target,
                          "sample": samples[-1], "estimate": estimate})
            if early_stop_confirmed and estimate.get("confirmed"):
                break
        estimate = estimate_track(samples, background, config.threshold_cm)
        if not local and step > config.fine_step_deg:
            candidates = _candidate_samples(samples, config.threshold_cm)
            clusters = _cluster_candidates(candidates)
            clusters.sort(key=lambda cluster: (
                len(cluster),
                max(float(sample["delta_cm"]) for sample in cluster)), reverse=True)
            centers = []
            for cluster in clusters[:2]:
                center = median([float(sample["yaw_deg"]) for sample in cluster])
                if all(abs(center - other) > config.fine_step_deg for other in centers):
                    centers.append(center)
            seen = {int(round(float(sample["yaw_deg"]))) for sample in samples}
            fine_targets = []
            for center in centers:
                for delta in (-2 * config.fine_step_deg, -config.fine_step_deg,
                              config.fine_step_deg, 2 * config.fine_step_deg):
                    target = float(center) + delta
                    if not (-config.yaw_limit_deg <= target <= config.yaw_limit_deg):
                        continue
                    key = int(round(target))
                    if key in seen:
                        continue
                    seen.add(key)
                    fine_targets.append(target)
            for target in fine_targets:
                if stop_event is not None and stop_event.is_set():
                    raise InterruptedError("tracking stopped")
                samples.append(_sample(client, target, background, config,
                                       config.fine_step_deg, on_status=on_status))
            estimate = estimate_track(samples, background, config.threshold_cm)
        _emit(progress, "tracking", estimate, samples, background.snapshot(), final=True)
        return {"estimate": estimate, "samples": samples,
                "background": background.snapshot()}
    finally:
        if prepare:
            _park_tracking(client, config)


def _locked_estimate(background, scan_yaw, distance_cm, delta_cm, source,
                     hlk_cm, hlk_energy, config, tilt_us=None):
    tilt = int(tilt_us or config.tilt_us)
    bearing, x, y, z = _polar(background, scan_yaw, distance_cm, tilt)
    if not background.inside_room(x, y):
        return None
    if background.solid_at(x, y, z):
        return None
    confidence = min(0.99, 0.62 + min(0.22, float(delta_cm) / 220.0)
                     + min(0.12, float(hlk_energy) / 900.0))
    return {
        "state": "confirmed", "confirmed": True,
        "bearing_deg": bearing,
        "scan_yaw_deg": round(float(scan_yaw), 1),
        "distance_cm": round(float(distance_cm), 1),
        "x_m": round(x, 3), "y_m": round(y, 3),
        "height_m": HUMAN_HEIGHT_M, "z_bottom_m": 0.0,
        "confidence": round(confidence, 3),
        "reason": "locked", "candidates": 1, "source": "lock",
        "tof_source": source, "delta_cm": round(float(delta_cm), 1),
        "hlk_cm": round(float(hlk_cm), 1) if hlk_cm is not None else None,
        "hlk_energy": int(hlk_energy),
        "tilt_us": tilt,
    }


def run_locked_tracking(client, config, background, scan_yaw_deg, smoother,
                        progress=None, stop_event=None, verify_s=None,
                        tilt_us=None, on_status=None):
    tilt = int(tilt_us or config.tilt_us)
    target = int(round(float(scan_yaw_deg) / 5.0)) * 5
    target = max(-config.yaw_limit_deg, min(config.yaw_limit_deg, target))
    client.move_stepper_to(
        int(round(target * 4096.0 / 360.0 / 57.0)) * 57,
        settle_s=0.15, step_deg=config.fine_step_deg, fast_wait=True)
    try:
        client.servo_to(tilt, step_delay_s=0.05)
    except Exception:
        pass
    time.sleep(max(0.0, config.dwell_ms) / 1000.0)
    history = []
    lost_since = None
    valid_since = None
    last_track = None
    while stop_event is None or not stop_event.is_set():
        status = client.status()
        if on_status:
            on_status(status)
        actual_yaw = float((status.get("scan") or {}).get("yaw_deg_nominal", target)
                           or target)
        distance, source = _sample_distance(status)
        hlk_cm, hlk_energy = _sample_hlk(status)
        baseline = background.background_cm(actual_yaw, tilt)
        delta = None
        if distance is not None and baseline is not None:
            delta = float(baseline) - float(distance)
            history.append((float(distance), float(delta), float(source != "tof"),
                            float(hlk_energy)))
            history = history[-3:]
        tof_history = [item for item in history if item[2] == 0.0]
        valid = False
        estimate = None
        if tof_history:
            distance_med = median([item[0] for item in tof_history])
            delta_med = median([item[1] for item in tof_history])
            energy_max = max(item[3] for item in history)
            if (delta_med >= config.lock_threshold_cm
                    and MIN_RANGE_CM <= distance_med <= MAX_RANGE_CM):
                estimate = _locked_estimate(
                    background, actual_yaw, distance_med, delta_med, "tof",
                    hlk_cm, energy_max, config, tilt_us=tilt)
                valid = estimate is not None
        if valid:
            lost_since = None
            now = time.monotonic()
            if valid_since is None:
                valid_since = now
            last_track = smoother.update(estimate, time.time())
            _emit(progress, "locked", last_track,
                  background=background.snapshot())
            if verify_s is not None and now - valid_since >= max(0.2, verify_s):
                return {"estimate": last_track, "lost": False, "verified": True}
        else:
            valid_since = None
            last_track = smoother.update({"state": "radar", "confirmed": False},
                                         time.time())
            _emit(progress, "locked", last_track,
                  background=background.snapshot())
            now = time.monotonic()
            if lost_since is None:
                lost_since = now
            elif now - lost_since >= max(0.5, config.lock_lost_s):
                return {"estimate": last_track, "lost": True}
        time.sleep(max(0.05, config.lock_sample_ms) / 1000.0)
    return {"estimate": last_track, "lost": False}


def _wait_interval(seconds, stop_event):
    until = time.monotonic() + max(0.2, float(seconds))
    while time.monotonic() < until:
        if stop_event is not None and stop_event.is_set():
            raise InterruptedError("tracking stopped")
        time.sleep(0.1)


def _provisional_candidate(estimate):
    """A single strong ToF return that deserves a short stationary lock test."""
    return (estimate.get("state") == "radar"
            and estimate.get("reason") == "single_sample"
            and int(estimate.get("candidates") or 0) >= 1
            and int(estimate.get("tof_count") or 0) >= 1
            and estimate.get("scan_yaw_deg") is not None)



def _verify_lock(client, config, background, estimate, smoother, progress,
                 stop_event, on_status):
    if not _provisional_candidate(estimate):
        return None
    verify_smoother = TrackSmoother(stale_s=3.0, expire_s=config.expire_s)
    verified = run_locked_tracking(
        client, config, background, float(estimate["scan_yaw_deg"]),
        verify_smoother, None, stop_event,
        verify_s=config.lock_verify_s,
        tilt_us=estimate.get("tilt_us"), on_status=on_status)
    candidate = verified.get("estimate")
    if (verified.get("verified") and candidate
            and candidate.get("state") == "confirmed"):
        track = smoother.update(candidate, time.time())
        _emit(progress, "tracking", track, final=True)
        return track
    return None


def run_tracking_loop(client, config, progress=None, stop_event=None, on_status=None):
    background = load_background(config.scan_id or None)
    smoother = TrackSmoother(stale_s=3.0, expire_s=config.expire_s)
    last = None
    last_yaw = None
    last_tilt = int(config.tilt_us)
    sweep_reverse = False
    _prepare_tracking(client, config, on_status=on_status)
    try:
        # 1. Fast probe at 0 deg. The demo operator usually stands near the
        # centre, so this can lock in 2-3 s instead of waiting for -60..0.
        probe = _sample(client, 0.0, background, config, config.fine_step_deg,
                        on_status=on_status)
        probe_estimate = estimate_track([probe], background, config.threshold_cm)
        _emit(progress, "probe", probe_estimate, [probe],
              background.snapshot(), final=True)
        track = _verify_lock(client, config, background, probe_estimate,
                             smoother, progress, stop_event, on_status)
        if track:
            last = track
            last_yaw = float(last["scan_yaw_deg"])
            last_tilt = int(last.get("tilt_us") or config.tilt_us)

        # 2. Local +/-20 deg acquisition at 5 deg, then an outer +/-40 ring at
        # 10 deg. A centre/near target is found in a few positions; the outer
        # ring only runs if the local pass did not confirm.
        local = None
        if last_yaw is None:
            local_targets = [-5.0, 5.0, -10.0, 10.0,
                             -15.0, 15.0, -20.0, 20.0]
            local = run_tracking_sweep(
                client, config, progress, stop_event, background=background,
                targets=local_targets, initial_samples=[probe],
                step_deg=5, local=True, prepare=False,
                early_stop_confirmed=True, on_status=on_status)
            last = smoother.update(local["estimate"], time.time())
            _emit(progress, "tracking", last, local["samples"],
                  local["background"], final=True)
            if last.get("state") == "confirmed":
                last_yaw = float(last["scan_yaw_deg"])
                last_tilt = int(last.get("tilt_us") or config.tilt_us)
            else:
                track = _verify_lock(client, config, background, last,
                                     smoother, progress, stop_event, on_status)
                if track:
                    last = track
                    last_yaw = float(last["scan_yaw_deg"])
                    last_tilt = int(last.get("tilt_us") or config.tilt_us)
        if last_yaw is None:
            outer_targets = [-30.0, 30.0, -40.0, 40.0]
            outer = run_tracking_sweep(
                client, config, progress, stop_event, background=background,
                targets=outer_targets,
                initial_samples=(local["samples"] if local else [probe]),
                step_deg=10, local=True, prepare=False,
                early_stop_confirmed=True, on_status=on_status)
            last = smoother.update(outer["estimate"], time.time())
            _emit(progress, "tracking", last, outer["samples"],
                  outer["background"], final=True)
            if last.get("state") == "confirmed":
                last_yaw = float(last["scan_yaw_deg"])
                last_tilt = int(last.get("tilt_us") or config.tilt_us)
            else:
                track = _verify_lock(client, config, background, last,
                                     smoother, progress, stop_event, on_status)
                if track:
                    last = track
                    last_yaw = float(last["scan_yaw_deg"])
                    last_tilt = int(last.get("tilt_us") or config.tilt_us)
            if last_yaw is None and outer["samples"]:
                sweep_reverse = float(outer["samples"][-1]["yaw_deg"]) > 0

        # 3. Lock and reacquire.
        while stop_event is None or not stop_event.is_set():
            if last_yaw is not None:
                locked = run_locked_tracking(
                    client, config, background, last_yaw, smoother,
                    progress, stop_event, tilt_us=last_tilt,
                    on_status=on_status)
                last = locked.get("estimate")
                if not locked.get("lost"):
                    if last and last.get("scan_yaw_deg") is not None:
                        last_yaw = float(last["scan_yaw_deg"])
                        last_tilt = int(last.get("tilt_us") or last_tilt)
                    continue
                _emit(progress, "reacquire", last, final=True)
                local = run_tracking_sweep(
                    client, config, progress, stop_event, background=background,
                    center_deg=last_yaw, span_deg=20,
                    step_deg=config.fine_step_deg, local=True, prepare=False,
                    early_stop_confirmed=True, on_status=on_status)
                last = smoother.update(local["estimate"], time.time())
                _emit(progress, "tracking", last, local["samples"],
                      local["background"], final=True)
                if last.get("state") == "confirmed":
                    last_yaw = float(last["scan_yaw_deg"])
                    last_tilt = int(last.get("tilt_us") or last_tilt)
                    continue
                track = _verify_lock(client, config, background, last,
                                     smoother, progress, stop_event, on_status)
                if track:
                    last = track
                    last_yaw = float(last["scan_yaw_deg"])
                    last_tilt = int(last.get("tilt_us") or config.tilt_us)
                    continue
                last_yaw = None
                if local["samples"]:
                    sweep_reverse = float(local["samples"][-1]["yaw_deg"]) > 0

            full = run_tracking_sweep(
                client, config, progress, stop_event, background=background,
                center_deg=0.0, span_deg=config.yaw_limit_deg,
                step_deg=config.coarse_step_deg, local=False, prepare=False,
                reverse=sweep_reverse, on_status=on_status)
            sweep_reverse = not sweep_reverse
            last = smoother.update(full["estimate"], time.time())
            _emit(progress, "tracking", last, full["samples"],
                  full["background"], final=True)
            if last.get("state") == "confirmed":
                last_yaw = float(last["scan_yaw_deg"])
                last_tilt = int(last.get("tilt_us") or config.tilt_us)
                continue
            track = _verify_lock(client, config, background, last,
                                 smoother, progress, stop_event, on_status)
            if track:
                last = track
                last_yaw = float(last["scan_yaw_deg"])
                last_tilt = int(last.get("tilt_us") or config.tilt_us)
                continue
            last_yaw = None
            _wait_interval(config.interval_s, stop_event)
    except InterruptedError:
        pass
    finally:
        _park_tracking(client, config)
    return last
