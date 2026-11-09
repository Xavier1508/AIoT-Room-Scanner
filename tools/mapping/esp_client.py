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

    def status(self, timeout: float = 12.0) -> dict:
        code, value = self.lan.call("/api/status", timeout=timeout)
        if code != 200 or "version" not in value:
            raise ValueError(f"Device status unavailable (HTTP {code}).")
        return value

    def command(self, name: str, timeout_s: float = 10.0) -> dict:
        return self.lan.command(name, timeout_s=timeout_s)

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
                        settle_s: float = 0.35, step_deg: int = 5) -> dict:
        """Move to a 57-half-step boundary, using 10-degree nudges when aligned."""
        if step_deg not in (5, 10):
            raise ValueError("stepper step must be 5 or 10 degrees")
        if target_half_steps % 57 != 0:
            raise ValueError(f"target {target_half_steps} is not aligned to 5-degree steps")
        state = self.status()
        current = int(state["actuators"]["relative_half_steps"])
        if current % 57 != 0:
            raise ValueError(f"current position {current} is not aligned to 5-degree steps")
        # Use 10-degree nudges only when both ends align; otherwise use 5-degree
        # nudges so the +/-45 degree endpoint (513 half-steps) is reachable.
        if step_deg == 10 and current % 114 == 0 and target_half_steps % 114 == 0:
            step_half, command_step = 114, 10
        else:
            step_half, command_step = 57, 5
        while current != target_half_steps:
            delta = target_half_steps - current
            expected = current + (step_half if delta > 0 else -step_half)
            name = (f"stepper_right_{command_step}" if delta > 0 else f"stepper_left_{command_step}")
            try:
                result = self.command(name)
            except TimeoutError:
                # The command may have completed after the observation window.
                # Check the resulting state; never resend a movement blindly.
                state = self.wait_for(
                    lambda s, expected=expected: bool(s["actuators"].get("stepper_holding")) and
                    int(s["actuators"]["relative_half_steps"]) == expected,
                    timeout_s=timeout_s)
                current = int(state["actuators"]["relative_half_steps"])
                continue
            if not result.get("ok"):
                raise RuntimeError("Stepper nudge rejected: " + str(result.get("message")))
            current = int(self.wait_for(
                lambda s, expected=expected: bool(s["actuators"].get("stepper_holding")) and
                int(s["actuators"]["relative_half_steps"]) == expected,
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
            expected = current + (25 if target_us > current else -25)
            name = "servo_up_25" if target_us > current else "servo_down_25"
            try:
                result = self.command(name)
            except TimeoutError:
                state = self.wait_for(
                    lambda s, expected=expected: int(s["actuators"]["servo_target_us"]) == expected,
                    timeout_s=timeout_s)
                current = int(state["actuators"]["servo_target_us"])
                continue
            if not result.get("ok"):
                if result.get("message") == "expired_no_action":
                    state = self.status()
                    observed = int(state["actuators"]["servo_target_us"])
                    if observed == expected:
                        current = expected
                        continue
                    if observed == current:
                        result = self.command(name)
                if not result.get("ok"):
                    raise RuntimeError("Servo nudge rejected: " + str(result.get("message")))
            current = int(self.wait_for(
                lambda s, expected=expected: int(s["actuators"]["servo_target_us"]) == expected,
                timeout_s=timeout_s)["actuators"]["servo_target_us"])
            if step_delay_s:
                time.sleep(step_delay_s)
        return self.status()
