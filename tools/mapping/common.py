"""Shared paths and small dependency-free helpers for the mapping tools."""
from __future__ import annotations

import json
import math
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESEARCH = ROOT / "research" / "mapping"
SCANS = RESEARCH / "scans"
CALIBRATION = RESEARCH / "calibration.json"


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def median(values):
    values = [float(v) for v in values if v is not None]
    return statistics.median(values) if values else None


def as_float(value, default=None):
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def as_int(value, default=None):
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def clamp(value, low, high):
    return max(low, min(high, value))


def polar_to_xyz(range_mm, yaw_deg, tilt_deg, height_mm=0.0):
    """Return millimetres in a right-handed room frame.

    yaw 0 points forward; positive yaw turns right. tilt 0 is horizontal,
    positive tilt looks upward. The sign convention must be confirmed by the
    calibration target before trusting the point cloud.
    """
    r = float(range_mm)
    yaw = math.radians(yaw_deg)
    tilt = math.radians(tilt_deg)
    horizontal = r * math.cos(tilt)
    return (
        horizontal * math.cos(yaw),
        horizontal * math.sin(yaw),
        float(height_mm) + r * math.sin(tilt),
    )


def tilt_from_pulse(pulse_us: int, calibration: dict | None = None) -> float:
    """Provisional pulse->tilt curve.

    The PC calibration file can store a list of (pulse_us, tilt_deg) points.
    Until that exists, use a symmetric 10 us/degree approximation around 725 us.
    This is explicitly provisional, not a measured servo curve.
    """
    if calibration:
        points = calibration.get("servo_curve") or []
        if len(points) >= 2:
            points = sorted((float(p["pulse_us"]), float(p["tilt_deg"])) for p in points)
            if pulse_us <= points[0][0]:
                return points[0][1]
            if pulse_us >= points[-1][0]:
                return points[-1][1]
            for (p0, t0), (p1, t1) in zip(points, points[1:]):
                if p0 <= pulse_us <= p1:
                    ratio = (pulse_us - p0) / (p1 - p0) if p1 != p0 else 0.0
                    return t0 + ratio * (t1 - t0)
    return (725.0 - float(pulse_us)) * 0.1


def sample_status(client, count: int, interval_s: float = 0.25):
    samples = []
    for index in range(max(1, count)):
        samples.append(client.status())
        if index + 1 < count:
            time.sleep(interval_s)
    return samples
