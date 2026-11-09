"""Small LAN client for the ESP32 diagnostic API.

Reuses the existing tools/ops/device.py Lan implementation so credentials stay
in tools/ops/device.local.json (gitignored) and are never exposed to a browser.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "ops"))

from device import Lan  # noqa: E402


class EspClient:
    def __init__(self) -> None:
        self.lan = Lan()

    def status(self, timeout: float = 8.0) -> dict:
        code, value = self.lan.call("/api/status", timeout=timeout)
        if code != 200 or "version" not in value:
            raise ValueError(f"Device status unavailable (HTTP {code}).")
        return value

    def command(self, name: str) -> dict:
        return self.lan.command(name)

    def ensure_sensors(self, timeout_s: float = 12.0) -> dict:
        state = self.status()
        sensors = state.get("sensors", {})
        if not sensors.get("enabled"):
            self.command("sensors_start")
            until = time.monotonic() + timeout_s
            while time.monotonic() < until:
                state = self.status()
                if state.get("sensors", {}).get("state") == "running":
                    return state
                time.sleep(0.3)
            raise TimeoutError("Sensors did not enter running state.")
        return state

    def wait_for(self, predicate, timeout_s: float = 12.0, interval_s: float = 0.15) -> dict:
        until = time.monotonic() + timeout_s
        last = None
        while time.monotonic() < until:
            last = self.status()
            if predicate(last):
                return last
            time.sleep(interval_s)
        raise TimeoutError("Timed out waiting for device state." if last is None else
                           "Timed out waiting for device state: " + str(last.get("mode")))

    def move_stepper_to(self, target_half_steps: int, timeout_s: float = 20.0,
                        settle_s: float = 0.35) -> dict:
        """Move using only 5-degree nudges; target must be reachable in 57-step units."""
        state = self.status()
        current = int(state["actuators"]["relative_half_steps"])
        while current != target_half_steps:
            delta = target_half_steps - current
            if delta > 0:
                result = self.command("stepper_right_5")
            else:
                result = self.command("stepper_left_5")
            if not result.get("ok"):
                raise RuntimeError("Stepper nudge rejected: " + str(result.get("message")))
            current = int(self.wait_for(
                lambda s: bool(s["actuators"].get("stepper_holding")) and
                int(s["actuators"]["relative_half_steps"]) == current + (57 if delta > 0 else -57),
                timeout_s=timeout_s)["actuators"]["relative_half_steps"])
        if settle_s:
            time.sleep(settle_s)
        return self.status()

    def servo_to(self, target_us: int, timeout_s: float = 8.0,
                 step_delay_s: float = 0.04) -> dict:
        """Move in 25 us steps with a delay so the rail is not hit by a fast ramp."""
        state = self.status()
        current = int(state["actuators"]["servo_target_us"])
        while current != target_us:
            if target_us > current:
                result = self.command("servo_up_25")
            else:
                result = self.command("servo_down_25")
            if not result.get("ok"):
                raise RuntimeError("Servo nudge rejected: " + str(result.get("message")))
            current = int(self.wait_for(
                lambda s: int(s["actuators"]["servo_target_us"]) ==
                current + (25 if target_us > current else -25),
                timeout_s=timeout_s)["actuators"]["servo_target_us"])
            if step_delay_s:
                time.sleep(step_delay_s)
        return self.status()
