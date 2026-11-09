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
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from calibrate import capture
from common import CALIBRATION, RESEARCH, SCANS, read_json, write_json
from esp_client import EspClient
from scan import ScanConfig, run_scan

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


def _public_job():
    with JOB_LOCK:
        return {key: JOB[key] for key in
                ("state", "scan_id", "points", "total", "error", "progress")}


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


def _points(scan_id):
    if not scan_id or Path(scan_id).name != scan_id or "/" in scan_id or "\\" in scan_id:
        raise ValueError("invalid scan id")
    directory = SCANS / scan_id
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
                    status = EspClient().status(timeout=2.0)
                    esp = {
                        "version": status.get("version"),
                        "mode": status.get("mode"),
                        "ip": status.get("wifi", {}).get("ip"),
                        "sensors": status.get("sensors"),
                        "actuators": status.get("actuators"),
                        "scan": status.get("scan"),
                        "hlk_alert": status.get("hlk_alert"),
                    }
                    return self._send(200, {"ok": True, "esp": esp,
                                            "scans": _list_scans(),
                                            "calibration": read_json(CALIBRATION, {}) or {}})
                except Exception as exc:
                    return self._send(200, {"ok": False, "error": str(exc),
                                            "scans": _list_scans(),
                                            "calibration": read_json(CALIBRATION, {}) or {}})
            if path == "/api/mapping/status":
                return self._send(200, {"ok": True, "status": EspClient().status()})
            if path == "/api/mapping/scans":
                return self._send(200, {"ok": True, "scans": _list_scans()})
            if path.startswith("/api/mapping/scans/") and path.endswith("/points"):
                scan_id = path[len("/api/mapping/scans/"):-len("/points")].strip("/")
                return self._send(200, {"ok": True, "scan_id": scan_id,
                                        "points": _points(scan_id)})
            if path == "/api/mapping/scan/status":
                return self._send(200, {"ok": True, "job": _public_job()})
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
            if path == "/api/mapping/scan/start":
                _start_scan(body)
                return self._send(202, {"ok": True, "job": _public_job()})
            if path == "/api/mapping/scan/stop":
                with JOB_LOCK:
                    event = JOB.get("stop_event")
                if event:
                    event.set()
                return self._send(200, {"ok": True, "message": "stop_requested"})
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
